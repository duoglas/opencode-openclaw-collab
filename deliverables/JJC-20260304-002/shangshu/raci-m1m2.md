# JJC-20260304-002 · 六部实施分工（RACI）+ M1/M2排期（尚书省）

> 依据修订产出：
> - /home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/revised-overall-plan.md
> - /home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/acl-matrix.md
> - /home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/migration-and-rollback.md

## 1) 角色说明
- 太子（Sponsor）：最终推动/拍板资源与时限
- 中书省（Architect/Decision）：契约/冻结项最终决议、跨团队协调
- 尚书省（Program/Execution）：派发六部、跟踪交付、汇总回传、风险/阻塞升级
- 工部（Dev）：bridge/契约/JetStream/幂等重试DLQ实现
- 兵部（Sec+Ops）：NATS安全与ACL落地、凭证轮换、演练脚本
- 刑部（QA）：测试矩阵、越权/迁移必测、验收门槛签核
- 礼部（Docs）：发布手册/排障/回滚预案/演练报告模板
- 户部（SLO+Cost）：指标口径、SLO、容量成本、看板
- 吏部（RACI落盘）：对接人名册与RACI固化（如需）

## 2) RACI 矩阵（实施阶段：M1/M2）
> 说明：此处以“部门/角色”为责任主体；若需落到个人姓名/agent_id，请太子或中书省补充名单，尚书省可在看板 todo detail 中固化。

| 交付项 | 太子 | 中书省 | 尚书省 | 工部 | 兵部 | 刑部 | 礼部 | 户部 |
|---|---|---|---|---|---|---|---|---|
| 冻结 subject/消息契约 v1（openclaw.dispatch.v1/result.v1 等） | I | A | R | C | C | C | I | C |
| Header字段与校验顺序（版本/过期/签名/ACL/幂等） | I | A | R | R | C | C | I | I |
| JetStream 设计冻结（Stream/Consumer/KV/DLQ） | I | A | R | R | C | C | I | C |
| bridge 骨架实现与最小链路（dispatch→result 回路） | I | C | A | R | C | C | I | C |
| NATS 认证（NKey/JWT/TLS）与 ACL 按矩阵落地 | I | C | A | C | R | C | I | I |
| 迁移双写/切流/回滚开关与脚本（BRIDGE_*） | I | C | A | C | R | C | C | I |
| 测试矩阵 + MIG-001~004 + SEC-OVR-001（越权必过） | I | C | A | C | C | R | I | C |
| SLO口径/指标/看板（成功率、P95、DLQ、越权拒绝） | I | C | A | C | C | C | I | R |
| 发布手册/排障/回滚预案与演练模板 | I | C | A | C | C | C | R | C |

A=Accountable（拍板/最终负责）R=Responsible（主责交付）C=Consulted（必须会签/评审）I=Informed（同步）

## 3) M1/M2 里程碑日期（Asia/Shanghai）
- **M1：契约/ACL/JetStream 冻结**
  - 截止：**2026-03-05（周四）18:00**
  - 产出：冻结纪要（subject、Header字段、JetStream参数、ACL矩阵版本号）

- **M2：最小链路联调打通（含幂等/重试/DLQ）**
  - 联调窗口建议：**2026-03-07（周六）14:00–18:00**（可改）
  - 截止：**2026-03-07（周六）18:00**
  - 产出：联调记录+E2E结果+初版指标看板截图/导出

> 备注：如需更激进排期，可将 M2 提前至 03-06；但要求兵部在 03-06 上午完成认证/ACL/凭证发放。

## 4) 风险与依赖（实施阶段）
### 关键依赖
1. **中书省冻结决议**：M1 冻结项未拍板将导致各部实现反复返工。
2. **NATS/JetStream 环境**：需至少 dev/stage 可用，且启用认证/ACL；否则 M2 联调无法开始。
3. **凭证与主体命名**：openclaw-dispatcher/openclaw-worker/opencode-producer/bridge-service 等账号体系需统一。

### 主要风险（含缓解）
- ACL误配导致误拒或越权放行：以 `acl-matrix.md` 为唯一事实源；刑部 SEC-OVR-001 必过 + 审计告警联动。
- 迁移双写一致性与回执断链：严格执行“新后旧”双写顺序 + 补偿队列 + 失败入DLQ并审计。
- 验收口径不一致：户部需在 M1 冻结 SLO 计算口径；刑部验收以口径为准。
- 性能不达标（P95>200ms）：提前压测，必要时将 DLQ/去重存储与业务路径隔离；调优 consumer 并发与 ack_wait。
