# JJC-20260304-002 · 工部实现方案（M1冻结 + M2最小链路）

## 1. 目标与范围
按修订方案推进以下五项实施内容：
1) bridge 骨架
2) subject / 契约
3) JetStream（Stream / Consumer / KV / DLQ）
4) 幂等机制
5) 重试机制

本文输出：**M1 冻结项**与**M2 最小链路实现计划**，用于六部协同落地与验收。

---

## 2. M1 冻结项（Frozen for M1）

> 原则：M1 只冻结“最小可运行 + 可观测 + 可回放”的基础能力，不引入复杂治理能力。

### 2.1 Bridge 骨架冻结
- 固定模块分层：
  - `adapter/inbound`：接入上游事件
  - `bridge/core`：路由、校验、幂等、重试编排
  - `adapter/outbound`：下游投递
  - `infra/nats`：JetStream 连接与资源初始化
  - `infra/store`：幂等 KV / retry 元数据
- 固定生命周期：`init -> subscribe -> handle -> ack/nak -> metrics`
- 固定错误分类：
  - `ContractError`（契约不合法）
  - `TransientError`（可重试）
  - `PermanentError`（不可重试，进DLQ）

### 2.2 Subject 与契约冻结
- Subject 命名规范冻结：
  - 业务主干：`bridge.<domain>.<event>.v1`
  - 重试队列：`bridge.retry.<domain>.<event>.v1`
  - 死信队列：`bridge.dlq.<domain>.<event>.v1`
- 契约字段冻结（统一 Envelope）：
  - `event_id`（全局唯一）
  - `event_type`
  - `occurred_at`（RFC3339）
  - `source`
  - `trace_id`
  - `payload`（业务字段）
  - `meta.retry_count`（默认0）
  - `meta.schema_version`（默认1）
- 校验策略冻结：
  - 入站必须通过 schema 校验；失败直接入 DLQ（原因：`contract_invalid`）

### 2.3 JetStream 资源冻结
- Stream 冻结：
  - `BRIDGE_MAIN`：绑定 `bridge.*.*.v1`
  - `BRIDGE_RETRY`：绑定 `bridge.retry.*.*.v1`
  - `BRIDGE_DLQ`：绑定 `bridge.dlq.*.*.v1`
- Consumer 冻结：
  - `C_MAIN_WORKER`（pull / durable）
  - `C_RETRY_WORKER`（pull / durable）
- KV 冻结：
  - `KV_IDEMPOTENCY`（key=`event_id`，value=处理状态+过期时间）
  - `KV_RETRY_META`（key=`event_id`，value=retry次数/下次重试时间）
- 保留策略冻结：
  - MAIN/RETRY：按时间窗口保留（默认7天）
  - DLQ：按容量 + 时间双阈值（默认30天）

### 2.4 幂等与重试冻结
- 幂等键冻结：`event_id`
- 幂等状态冻结：`processing | done | failed_permanent`
- 重试策略冻结（M1 统一策略）：
  - 最多 `3` 次
  - 固定退避：`30s -> 120s -> 300s`
  - 超限进入 DLQ，标记 `retry_exhausted`
- ACK 语义冻结：
  - 成功：ACK
  - 可重试错误：NAK + delay（或转入 RETRY stream）
  - 不可重试错误：ACK 主消息并发布 DLQ 事件

### 2.5 可观测与验收冻结
- 指标冻结：
  - `bridge_events_total{status}`
  - `bridge_retry_total`
  - `bridge_dlq_total{reason}`
  - `bridge_consume_latency_ms`
- 日志字段冻结：`event_id, trace_id, subject, retry_count, error_code`
- M1 验收口径冻结：
  1) 正常消息可从 MAIN 完整处理并 ACK
  2) 可重试错误按既定节奏重试，最终成功或入 DLQ
  3) 契约错误直接入 DLQ
  4) 相同 `event_id` 重放不重复执行业务副作用

---

## 3. M2 最小链路实现计划（可执行）

> 目标：打通一条“上游事件 -> Bridge -> 下游处理 -> ACK/RETRY/DLQ”的最小闭环。

### 3.1 里程碑与交付

#### 里程碑 A：资源与骨架落地（D1-D2）
- 交付物：
  - Bridge 项目目录与模块骨架
  - JetStream 三类 Stream + 两类 Consumer + 两个 KV 初始化脚本
  - Subject 常量与契约定义文件
- 验证：
  - 本地/测试环境可一键创建资源
  - consumer 可订阅并拉取测试消息

#### 里程碑 B：主链路处理（D3-D4）
- 交付物：
  - `main_handler`：消费、校验、幂等检查、业务处理、ACK
  - 幂等写入流程：`processing -> done`
  - 基础指标与结构化日志
- 验证：
  - 正常消息端到端成功
  - 重复消息被去重

#### 里程碑 C：重试与死信（D5-D6）
- 交付物：
  - `retry_handler`：按 retry_count 与 backoff 执行重试
  - 错误分流：TransientError 进重试链路，PermanentError/契约错误进 DLQ
  - DLQ message 附带失败原因与原始上下文
- 验证：
  - 人工注入可重试错误，观察 3 次重试后成功/入DLQ
  - 人工注入不可重试错误，直接入DLQ

#### 里程碑 D：联调与冻结评审（D7）
- 交付物：
  - 最小链路联调记录
  - M1 冻结项核对清单（通过/不通过）
  - M2 下一步优化 backlog（不阻塞上线）
- 验证：
  - 六部共同验收通过（按 M1 口径）

### 3.2 M2 最小链路实现清单（工程任务）
1. `bridge/core/router`：subject -> handler 映射
2. `bridge/core/contract`：schema 校验与版本路由
3. `bridge/core/idempotency`：KV 原子写/读封装
4. `bridge/core/retry`：重试次数、退避策略、状态持久化
5. `infra/nats/bootstrap`：Stream/Consumer/KV 自动创建
6. `infra/nats/publisher`：主流/重试流/DLQ 发布器
7. `adapter/outbound/example`：最小下游调用（可替换）
8. `observability`：metrics + structured logs + trace_id 透传

### 3.3 风险与控制
- 风险1：KV 并发竞争导致重复处理
  - 控制：基于 event_id 的 compare-and-set / 锁定窗口
- 风险2：重试风暴
  - 控制：固定退避 + consumer 并发上限 + DLQ 熔断
- 风险3：契约演进破坏兼容
  - 控制：schema_version + 向后兼容检查 + 灰度 subject

### 3.4 M2 完成定义（DoD）
满足以下全部即视为 M2 最小链路完成：
- E2E：单条业务事件可达下游并 ACK
- 异常：可重试/不可重试路径均可观测
- 幂等：重放 10 次仅生效 1 次
- 运维：可查询 DLQ、可回放、可统计重试

---

## 4. 后续（M3+，不纳入本次冻结）
- 指数退避与抖动（jitter）
- 多租户/多业务域隔离
- 自动回放工具与DLQ批处理
- 契约注册中心与自动兼容性检查
- 动态并发与流控

---

## 5. 结论
本文件已冻结 M1 基线，并给出 M2 最小闭环实施路线。建议按 D1-D7 节奏推进，确保先闭环再扩展，避免过早引入复杂度。
