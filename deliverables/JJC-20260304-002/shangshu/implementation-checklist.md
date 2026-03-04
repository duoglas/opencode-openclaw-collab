# JJC-20260304-002 · 统一实施清单（按 M1/M2 拆分）

## ✅ M1 冻结纪要（皇上已批）
- 冻结版本号：**M1-FREEZE-v1.0**
- 生效时间：**2026-03-04 16:57 (Asia/Shanghai)**
- 冻结范围（五项，作为后续实现/联调唯一口径）：
  1) **Subject/映射**：`openclaw.dispatch.v1`、`openclaw.result.v1`、`opencode.event.v1.*`、`bridge.control.v1.*`、`bridge.dlq.dispatch.v1`；旧→新：`op.task.home→openclaw.dispatch.v1`，`op.result.controller→openclaw.result.v1`
  2) **ACL/鉴权**：以 `acl-matrix.md` 为唯一事实源；显式 deny OpenCode publish `*.dispatch`；`bridge.control.v1.*` 仅 bridge-service 与 sre-ops 可访问；默认拒绝最小权限放行；认证采用 **NKey/JWT**（TLS/mTLS 由兵部按基线执行）
  3) **JetStream 参数**：Stream `BRIDGE_DISPATCH_V1`（subjects: dispatch/result/dlq；retention=limits；max_age=72h可配）；Consumer `bridge-dispatch-worker`（pull/explicit ack；ack_wait=30s；max_deliver=6）
  4) **幂等语义**：`dedup_key = hash(x-msg-id + target + action)`；去重窗口默认24h（可配1h~72h）；跨实例一致性存储采用 JetStream KV（首选）
  5) **重试/DLQ**：超过重试阈值写 `bridge.dlq.dispatch.v1` 并附失败原因与重试轨迹；不可重试错误包含：签名非法/过期/越权/版本不支持（其余按可重试处理并受 max_deliver 限制）

## ⏱ 执行期回传机制（每 10 分钟一次，皇上最新指示）
- 频率：**每 10 分钟**（无变化也必须回传一句 **“无变化”**）
- 回传方式：工/兵/刑 → 尚书省汇总 → 更新看板 `progress`
- 回传模板（建议复制粘贴，四段即可）：
  - **进展**：一句话说明刚完成/正在做什么（或：无变化）
  - **风险**：新增风险/风险变化（或：无变化）
  - **阻塞**：需要他部/资源/拍板支持（或：无变化）
  - **下一步**：未来 10–30 分钟将做的动作（或：无变化）

> 目标：把五部“实施交付”汇总成可执行 Checklist，并用于推进 **M1 冻结** 与 **M2 联调**。

## 0. 依据（修订版为唯一口径）
- 中书修订总体方案：`/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/revised-overall-plan.md`
- ACL 矩阵：`/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/acl-matrix.md`
- 迁移与回滚：`/home/duoglas/.openclaw/workspace-zhongshu/deliverables/JJC-20260304-002/migration-and-rollback.md`

## 1. 五部实施交付（已收齐）
- 工部：`/home/duoglas/.openclaw/workspace-gongbu/deliverables/JJC-20260304-002/gongbu_impl.md`
- 兵部：`/home/duoglas/.openclaw/workspace-bingbu/deliverables/JJC-20260304-002/bingbu_secops.md`
- 刑部：`/home/duoglas/.openclaw/workspace-xingbu/deliverables/JJC-20260304-002/xingbu_tests.md`
- 礼部：`/home/duoglas/.openclaw/workspace-libu/deliverables/JJC-20260304-002/libu_runbook.md`
- 户部：`/home/duoglas/.openclaw/workspace-hubu/deliverables/JJC-20260304-002/hubu_slo_cost.md`

---

## 2) M1 冻结清单（Freeze Checklist）
> M1 输出：冻结纪要 + 配置基线 + 验收口径（刑部 Gate）。

### 2.1 Subject / 契约（修订版）
- [ ] 冻结 subject：
  - `openclaw.dispatch.v1`（统一下发）
  - `openclaw.result.v1`（统一回执）
  - `opencode.event.v1.*`（OpenCode 业务事件）
  - `bridge.control.v1.*`（控制面）
  - `bridge.dlq.dispatch.v1`（dispatch DLQ）
  - （可选）`audit.dispatch.v1`（审计）
- [ ] 冻结旧→新映射：
  - `op.task.home` → `openclaw.dispatch.v1`
  - `op.result.controller` → `openclaw.result.v1`
- [ ] 冻结 dispatch body 最小字段（建议）：`dispatch_id,target,action,payload,priority`

### 2.2 Header + 签名校验顺序（修订版必改项）
- [ ] Header 必填字段冻结：
  - `x-msg-id`（UUIDv7）
  - `x-trace-id`
  - `x-signature`（ed25519）
  - `x-signer`
  - `x-version`（1.0）
  - `x-expire-at`（RFC3339 UTC）
  - `x-issued-at`（RFC3339 UTC）
- [ ] 冻结校验顺序：版本兼容→过期→签名→ACL/主体→幂等→入队执行

### 2.3 JetStream / KV / DLQ 参数冻结（修订版）
- [ ] Stream 冻结：`BRIDGE_DISPATCH_V1`
  - subjects：`openclaw.dispatch.v1`, `openclaw.result.v1`, `bridge.dlq.dispatch.v1`
  - retention：limits
  - max_age：72h（可配）
- [ ] Consumer 冻结：`bridge-dispatch-worker`
  - pull / explicit ack
  - ack_wait：30s
  - max_deliver：6（初始+5重试）
- [ ] DLQ subject 冻结：`bridge.dlq.dispatch.v1`（需带失败原因 + 重试轨迹）
- [ ] 幂等去重冻结：
  - dedup_key = hash(`x-msg-id + target + action`)
  - 去重窗口：24h（可配置 1h~72h）
  - 存储：JetStream KV（首选）

> 注：工部交付中存在另一套“bridge.*.*.v1 + BRIDGE_MAIN/RETRY/DLQ + event_id 幂等”方案；本项目 M1 以修订版为唯一口径，需在实现时对齐上述冻结项。

### 2.4 ACL / 身份（以 acl-matrix.md 为唯一事实源）
- [ ] 角色/主体命名冻结（至少包含）：
  - `openclaw-dispatcher`, `openclaw-worker`, `opencode-producer`, `bridge-service`, `sre-ops`, `audit-reader`
- [ ] 强制规则冻结：
  - **OpenCode 显式 deny publish `*.dispatch`**
  - `bridge.control.v1.*` 仅 bridge-service + sre-ops 可访问
  - 默认拒绝（deny by default），按 subject 级最小权限放行
- [ ] 认证方式冻结：NKey/JWT（及是否强制 client mTLS）

### 2.5 迁移/回滚开关与门槛冻结（修订版）
- [ ] 双写开关：`BRIDGE_DUAL_WRITE`（迁移期 true）
- [ ] 主路径切换：`BRIDGE_USE_V1`（切到新 subject）
- [ ] 回执切换：`BRIDGE_RESULT_USE_V1`
- [ ] 切换门槛冻结（必须全部满足）：
  - 24h 成功率 ≥ 99%
  - P95 < 200ms
  - 越权事件 = 0
  - DLQ 比率 < 0.1%
- [ ] 回滚触发与动作冻结：5 分钟内完成（详见 migration-and-rollback.md）

### 2.6 可观测字段与指标冻结（用于 M2 联调）
- [ ] 日志/审计字段最小集：who/when/subject/x-trace-id/result/reason
- [ ] 关键指标最小集：成功率、P95、重试率、DLQ rate/backlog、越权拒绝率
- [ ] 贯穿字段：trace_id 必须可关联（至少 x-trace-id）

---

## 3) M2 最小链路联调清单（Integration Checklist）
> M2 输出：最小闭环跑通 + 可观测 + 可回滚演练一次 + 刑部用例跑通样例。

### ✅ M2 联调三步法（可执行）
1) **NATS/JetStream 环境就绪（兵部主责）**：认证(NKey/JWT+TLS)、ACL按矩阵上线、creds发放、JetStream资源初始化可用
2) **bridge 最小链路跑通（工部主责）**：dispatch→bridge→worker→result 回路跑通；幂等/重试/DLQ 路径可观测
3) **刑部验收用例跑通（刑部主责）**：MIG（迁移兼容）与 SEC（越权）用例执行记录齐全并达门槛；输出签核结论

### 3.1 环境与凭证（兵部）
- [ ] dev/stage NATS（含 JetStream）可用
- [ ] 认证启用：NKey/JWT（及 TLS）
- [ ] ACL 按矩阵上线（含 OpenCode deny dispatch 的实测用例）
- [ ] creds/证书下发（OpenClaw/OpenCode/bridge/ops），轮换 runbook 可执行

### 3.2 最小 E2E 回路（工部主责，兵部配合）
- [ ] OpenClaw dispatcher 发布 `openclaw.dispatch.v1`（含完整 header）
- [ ] bridge-service 消费并完成：校验→幂等→入队→执行/转发→回执
- [ ] OpenClaw worker 消费指令并发布 `openclaw.result.v1`
- [ ] bridge-service 订阅/处理回执（必要时汇聚为上游可消费的反馈事件——如需）
- [ ] 失败路径：
  - 不可重试错误（签名非法/过期/越权/版本不支持）直接写 DLQ
  - 可重试错误按 max_deliver/退避策略重试，超限写 DLQ

### 3.3 测试与验收（刑部 Gate）
- [ ] MIG-001~004（双写一致、切流、回滚、切流后稳定观察）具备可执行记录
- [ ] SEC-OVR-001：OpenCode 越权 publish dispatch 100% 拒绝 + 审计字段齐全
- [ ] 回滚演练：触发条件→执行回滚脚本→恢复旧链路（≤5分钟）

### 3.4 文档与运行保障（礼部/户部）
- [ ] 发布手册覆盖阶段 A-D + 关键开关含义
- [ ] 故障排查：以 trace_id / x-msg-id 定位链路
- [ ] 回滚预案：5分钟动作清单 + 沟通模板
- [ ] 看板：能展示成功率/P95/重试/DLQ/越权拒绝，并用于切流门槛判定

---

## 4) 里程碑与负责人（按尚书省排期基线）
- **M1 冻结截止**：2026-03-05 18:00
- **M2 联调窗口建议**：2026-03-07 14:00–18:00

详见：`/home/duoglas/.openclaw/workspace-shangshu/deliverables/JJC-20260304-002/raci-m1m2.md`
