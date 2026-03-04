# JJC-20260304-002 修订版总体方案（中书省）

## 0. 修订背景
依据门下省“需改”回执，已对原方案进行强制修订，逐条落实 10 条必改项。目标不变：建设 OpenCode 与 OpenClaw 的 NATS 协同桥，但明确“调度权单边收敛、鉴权与审计可追溯、迁移可回滚”。

## 1. 边界与权责（必改1）
- **唯一调度发布方**：仅 OpenClaw 可发布 `*.dispatch` 指令。
- **OpenCode 禁止发布**任何 `*.dispatch`（ACL 显式 deny）。
- OpenCode 仅可发布业务事件（如 `opencode.event.*`）与状态回传，不具备调度下发权限。

## 2. Dispatch 契约（必改3）
### 2.1 Subject
- `openclaw.dispatch.v1`（统一下发）

### 2.2 Header（必填）
- `x-msg-id`：全局唯一消息ID（UUIDv7）
- `x-trace-id`：链路追踪ID
- `x-signature`：`ed25519` 签名（签名对象=canonical(header+body)）
- `x-signer`：签名主体（service account）
- `x-version`：契约版本，当前 `1.0`
- `x-expire-at`：UTC RFC3339 过期时间
- `x-issued-at`：UTC RFC3339 下发时间

### 2.3 Body（建议）
```json
{
  "dispatch_id": "dsp_...",
  "target": "openclaw.worker.<id>",
  "action": "run_task",
  "payload": {},
  "priority": "normal"
}
```

### 2.4 校验顺序
1) 版本兼容校验 2) 过期时间校验 3) 签名校验 4) ACL/主体校验 5) 幂等校验 6) 入队执行。

## 3. 幂等与一致性（必改4）
- 去重键：`dedup_key = hash(x-msg-id + target + action)`。
- 去重窗口：默认 24h（可配置 1h~72h）。
- 跨实例一致性：采用 **JetStream KV**（首选）保存去重状态；若跨区域部署则切换外部存储（Redis/Etcd）保证强一致策略。
- 状态：`processing`/`done`/`failed`，并记录首次写入时间与最后更新时间。

## 4. 重试与DLQ（必改5）
- 退避策略：指数退避 + 抖动（1s,2s,4s,8s,16s，jitter 20%）。
- 最大次数：5 次（可配）。
- 不可重试错误码：`4001(签名非法)`、`4003(过期)`、`4007(越权)`、`4010(契约版本不支持)`。
- 可重试错误：网络瞬断、下游超时、503/429。
- 超过阈值写入 DLQ：`bridge.dlq.dispatch.v1`，附失败原因与重试轨迹。

## 5. JetStream 规范（必改6）
- Stream：`BRIDGE_DISPATCH_V1`
  - subjects: `openclaw.dispatch.v1`, `openclaw.result.v1`, `bridge.dlq.dispatch.v1`
  - retention: limits（生产默认）
  - max_age: 72h（可配）
- Consumer：
  - `bridge-dispatch-worker`（pull/explicit ack）
  - ack policy: explicit
  - ack wait: 30s
  - max deliver: 6（初始+5重试）
  - replay: instant
- 保留策略：生产按容量与合规要求设置 `max_msgs/max_bytes`，DLQ 单独 stream 并延长保留。

## 6. ACL 与最小权限（必改2）
- ACL 细化到 subject 级（详见《acl-matrix.md》）。
- `bridge.control.*` 仅 Bridge 与 SRE 角色可 publish/subscribe，业务侧全部 deny。

## 7. 旧 subject 迁移与回滚（必改7）
- 迁移方式：**双写 + 双读观测 + 开关切流**。
- 显式旧主题映射（门下省指定）：
  - `op.task.home` → `openclaw.dispatch.v1`
  - `op.result.controller` → `openclaw.result.v1`
- 双写顺序（防止回执断链）：
  1) 先写新主题（记录trace与ack）
  2) 再写旧主题（兼容存量消费者）
  3) 任一失败进入补偿队列并写审计
- 切换条件：新链路 24h 内成功率≥99%、P95<200ms、越权告警=0、DLQ率低于阈值。
- 回滚开关：`BRIDGE_USE_V1=false` 即刻退回旧主题（详见《migration-and-rollback.md》）。
- 改造清单（生产/消费双方）：
  - 生产方：OpenClaw dispatcher 增加新主题发布与签名头，保留旧主题双写开关
  - 消费方：Bridge consumer 与 OpenClaw worker 订阅 `openclaw.dispatch.v1`；结果统一发布 `openclaw.result.v1`
  - OpenCode：仅保留结果/事件订阅发布能力，禁止任何 dispatch 发布

## 8. 审计（必改8）
- 每次下发记录：`who(主体)`、`when`、`subject`、`x-trace-id`、`result`、`reason`。
- 审计日志保留期：
  - 在线 90 天
  - 归档 365 天（可按合规要求延长）

## 9. 限流与熔断（必改9）
- 限流：按主体+subject 维度（例：100 req/s，突发200）。
- 熔断：5s窗口错误率>30%触发半开；恢复阈值连续3窗口<5%。
- 降级路径：
  1) 停止新 dispatch 下发
  2) 保留状态回传通道
  3) 输出人工处置告警并进入只读保障模式

## 10. 验收补充（必改10）
新增两类必须通过测试：
1) **迁移兼容测试**：旧新 subject 并存期间的双写一致性、切换前后无丢单。
2) **越权测试**：OpenCode 发布 `*.dispatch` 必须被拒绝并写审计。

## 11. 实施里程碑（修订后）
- M1：契约/ACL/JetStream 配置冻结
- M2：最小链路联调 + 幂等/重试打通
- M3：迁移演练 + 安全/越权测试
- M4：灰度发布、回滚演练、正式切换

## 12. 产出物
- 本文件：`revised-overall-plan.md`
- ACL矩阵：`acl-matrix.md`
- 迁移与回滚：`migration-and-rollback.md`
