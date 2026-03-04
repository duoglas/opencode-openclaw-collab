# JJC-20260304-002 · 修订版派发汇总（尚书省）

## 输入（中书省修订产出）
- 总体方案：/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/revised-overall-plan.md
- ACL矩阵：/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/acl-matrix.md
- 迁移回滚：/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/migration-and-rollback.md

## 修订关键点（必须落地）
- 调度权单边收敛：仅 OpenClaw 可发布 dispatch；OpenCode 显式 deny publish `*.dispatch`
- 新 subject：`openclaw.dispatch.v1` / `openclaw.result.v1` / `opencode.event.v1.*` / `bridge.control.v1.*` / `bridge.dlq.dispatch.v1`
- Header 必填与校验顺序：版本→过期→签名→ACL/主体→幂等→入队
- JetStream：Stream `BRIDGE_DISPATCH_V1` + Consumer `bridge-dispatch-worker`（pull/explicit ack/ackwait30s/maxdeliver6）
- 迁移：双写+双读观测+开关切流；回滚 5 分钟内完成；越权测试必过

## 六部分工与交付清单（修订版）
- 工部：bridge 实现骨架 + subject/契约落地 + JetStream stream/consumer 配置 + 幂等/重试/DLQ
- 兵部：NKey/JWT/TLS/ACL 落地 + 凭证轮换 + 运维/演练脚本（切流/回滚开关）
- 刑部：测试矩阵与验收门槛（迁移兼容+越权测试必过）
- 礼部：发布手册/故障排查/回滚预案/演练报告模板
- 户部：容量成本模型+SLO口径+观测看板（含越权拒绝、DLQ堆积、重试率等）

## 建议排期（可调整）
见：deliverables/JJC-20260304-002/implementation-schedule.md

## 验收门槛（修订版强化）
- 连续24h成功率≥99%
- P95<200ms
- 越权事件=0（OpenCode 发布 dispatch 100%拒绝并审计）
- DLQ<0.1%

