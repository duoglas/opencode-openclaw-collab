# JJC-20260304-002 · 实施拆解与排期（尚书省汇总）

> 基准：2026-03-04（今日）起，按“契约冻结(M1) → 最小链路(M2) → 迁移演练/安全增强(M3) → 灰度发布(M4)”推进。
> 说明：下述日期为建议档期，可由中书省按资源微调；每一里程碑以刑部验收门槛为准入条件。

## M1（契约/ACL/JetStream配置冻结）
- **T+0.5天（03-04 EOD）**：冻结 subject/ACL/JetStream 关键参数（以修订总体方案为准）
  - subject：`openclaw.dispatch.v1` / `openclaw.result.v1` / `opencode.event.v1.*` / `bridge.control.v1.*` / `bridge.dlq.dispatch.v1`
  - JetStream：Stream `BRIDGE_DISPATCH_V1`；Consumer `bridge-dispatch-worker`（pull/explicit ack/ackwait30s/maxdeliver6）
  - ACL：显式 deny OpenCode publish `*.dispatch`
- **T+1天（03-05）**：完成签名Header字段与校验顺序接口冻结（x-msg-id/x-trace-id/x-signature/x-signer/x-version/x-expire-at/x-issued-at）

## M2（最小链路打通 + 幂等/重试/DLQ）
- **T+2天（03-06）**：
  - 工部：bridge骨架跑通 dispatch→worker→result 回路；幂等去重（JetStream KV）；DLQ写入
  - 兵部：dev/stage 环境 NATS 认证+ACL 落地，发放三方凭证
- **T+3天（03-07）**：刑部组织 E2E 联调（成功/失败可重试/入DLQ/断链恢复），户部接入指标采集

## M3（迁移演练 + 安全/越权测试必过）
- **T+5天（03-09）**：进入双写期演练（BRIDGE_DUAL_WRITE=true），完成 MIG-001~004
- **T+6天（03-10）**：完成越权测试 SEC-OVR-001（OpenCode 发布 dispatch 100% 拒绝并审计），并完成一次“切流→回滚”演练

## M4（灰度发布、回滚演练、正式切换）
- **T+8天（03-12）**：灰度切流（BRIDGE_USE_V1=true），保持旧链路热备 24h
- **T+9天（03-13）**：满足门槛后关闭双写（BRIDGE_DUAL_WRITE=false），进入收敛期

## 验收门槛（刑部签核口径）
- 连续24h成功率 ≥ 99%
- P95 < 200ms（在约定负载）
- 越权事件 = 0
- DLQ 比率 < 0.1%

## 关键依赖
- NATS/JetStream 集群可用（含认证/ACL）
- OpenClaw dispatcher/worker 与 bridge 的签名/审计字段贯穿
- 旧主题双写与回滚开关（BRIDGE_DUAL_WRITE / BRIDGE_USE_V1 / BRIDGE_RESULT_USE_V1）
