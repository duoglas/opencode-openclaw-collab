# JJC-20260304-002 · M1 架构与契约评审清单（中书省用）

> 目的：在进入 M2 最小链路联调前，冻结 **subject 命名/消息契约/鉴权与治理/可靠性语义/可观测字段** 的最小集合，避免联调反复。

## 0. 评审输入（已齐备）
- 工部：`gongbu.md`（契约/bridge/适配器/幂等重试DLQ/风险）
- 兵部：`bingbu.md`（NKey/JWT、ACL、限流、HA、降级、DLQ）
- 刑部：`xingbu.md`（E2E/压测/验收清单）
- 礼部：`libu.md`（文档结构/发布回滚模板）
- 户部：`hubu.md`（SLO/指标/容量成本/Prom样例）

## 1. 必须冻结的契约（Gate）
1) **Subject 规范**
- `opencode.>` / `openclaw.>` / `bridge.control.>` 是否最终确认？
- 是否需要加版本段：如 `opencode.v1.*`？

2) **消息 Envelope（统一字段）**
- `trace_id` / `span_id` / `request_id` / `idempotency_key` / `ts` / `producer` / `schema_version`
- 错误回执结构：`error.code` / `error.message` / `retryable`

3) **命令/事件分类**
- 哪些是命令（需回执/可重试）？哪些是事件（至少一次/可丢弃）？

4) **幂等语义**
- 幂等键来源（OpenCode 生成？bridge 生成？）
- 幂等窗口与去重存储（内存/Redis/JetStream KV）

5) **重试与 DLQ**
- 重试策略（最大次数、backoff、jitter）
- DLQ subject 命名与落地（JetStream stream / 外部存储）

6) **鉴权与 ACL**
- 采用 NKey 还是 JWT（或组合）
- 证书/密钥发放与轮换策略（最小版本即可）
- ACL 是否按 subject 粒度隔离（OpenCode/OpenClaw/bridge）

7) **可观测**
- 结构化日志字段最小集合
- 指标：成功率、P95、重试率、DLQ堆积、订阅积压
- Trace 贯穿：是否强制 trace_id 必填？

## 2. M2 联调最小链路（需中书省定责/定档期）
- 联调环境：NATS（含认证） + bridge（单副本） + OpenCode adapter（最小发布/订阅） + OpenClaw adapter（最小订阅/回执）
- 端到端链路：OpenCode → NATS → bridge → OpenClaw 执行回执 → bridge → OpenCode

中书省需确认：
- 联调窗口（日期/时段）
- 负责人对接点（OpenCode 侧 1 人 / OpenClaw 侧 1 人 / bridge 侧 1 人）
- 成功判定：
  - E2E 成功率 ≥ 99%
  - P95 < 200ms（在约定负载下）
  - 失败可重试 + DLQ 可观测

## 3. 评审输出（会议纪要模板）
- 决议：subject & schema 冻结（版本号：____）
- 决议：鉴权方案（____）
- 决议：幂等/重试/DLQ 语义（____）
- 联调排期：____
- RACI：____
