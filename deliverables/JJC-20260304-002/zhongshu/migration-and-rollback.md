# JJC-20260304-002 迁移与回滚方案

## 1. 目标
将旧 subject 平滑迁移至 `*.v1` 新体系，保障业务连续性、可回滚、可审计。

## 2. 迁移对象（明确一一映射）
- 旧主题A：`op.task.home` → 新主题：`openclaw.dispatch.v1`
- 旧主题B：`op.result.controller` → 新主题：`openclaw.result.v1`
- 控制与治理主题统一迁入：`bridge.control.v1.*` / `bridge.dlq.dispatch.v1`

## 3. 阶段化迁移
### 阶段A：准备期
- 冻结旧主题新增变更。
- 发布 ACL 新矩阵（但不切流）。
- 建立双写开关：`BRIDGE_DUAL_WRITE=true`。

### 阶段B：双写期
- OpenClaw dispatcher 对每条 dispatch 执行“新后旧”双写：
  1) publish `openclaw.dispatch.v1`
  2) publish `op.task.home`
- OpenClaw worker 执行后结果双写：
  1) publish `openclaw.result.v1`
  2) publish `op.result.controller`
- Bridge 对新链路全量观测（成功率、延迟、DLQ、越权）。
- 执行迁移兼容测试：消息一致性、顺序、幂等。

### 阶段C：切流期
- 满足切换门槛后，将消费主路径切到新主题：`BRIDGE_USE_V1=true`。
- 保持旧链路热备 24h（只写不读或低频抽样读）。

### 阶段D：收敛期
- 关闭旧主题双写：`BRIDGE_DUAL_WRITE=false`。
- 回收旧 ACL 与旧 consumer。

## 4. 切换门槛（必须全部满足）
1) 连续24h成功率 >= 99%
2) P95 延迟 < 200ms
3) 越权事件 = 0
4) DLQ 比率 < 0.1%
5) 迁移兼容测试全通过

## 5. 回滚策略
### 5.1 触发条件（任一满足）
- 成功率跌破 98.5% 持续 10 分钟
- P95 > 300ms 持续 10 分钟
- 出现批量越权误拒绝
- DLQ 激增超过阈值（例如 >1%）

### 5.2 回滚动作（5分钟内）
1. 设置 `BRIDGE_USE_V1=false`，主路径切回旧主题。
2. 保留新链路写入但停止消费（便于事后分析）。
3. 通知值班群与审计系统，记录 `trace_id` 级故障事件。
4. 进入故障复盘并输出修复计划。

## 6. 改造清单与灰度开关（门下省补充要求）
### 6.1 生产方改造清单
- OpenClaw dispatcher：新增 `openclaw.dispatch.v1` 发布器；保留 `op.task.home` 双写能力。
- OpenClaw worker：新增 `openclaw.result.v1` 发布器；保留 `op.result.controller` 双写能力。

### 6.2 消费方改造清单
- Bridge consumer：新增订阅 `openclaw.dispatch.v1` 与 `openclaw.result.v1`。
- 旧链路消费者：迁移期继续订阅 `op.task.home` / `op.result.controller`，收敛期下线。

### 6.3 灰度开关
- `BRIDGE_DUAL_WRITE`：控制是否双写（默认 true 于迁移期）。
- `BRIDGE_USE_V1`：控制是否以新主题为主消费路径。
- `BRIDGE_RESULT_USE_V1`：控制结果回执主路径切换。

### 6.4 验证用例ID
- `MIG-001`：`op.task.home` 与 `openclaw.dispatch.v1` 双写一致性
- `MIG-002`：`op.result.controller` 与 `openclaw.result.v1` 回执一致性
- `MIG-003`：切流后仅新主题消费，无丢单
- `MIG-004`：回滚后旧主题恢复消费，无断链
- `SEC-OVR-001`：OpenCode 越权发布 dispatch 被拒绝并审计

## 7. 演练要求
- 上线前至少完成 2 次“切流->回滚”演练。
- 演练报告包含：时序、指标曲线、问题清单、改进项。

## 8. 验收新增项（门下省要求）
- 迁移兼容测试：旧新并存、双写一致、切流无丢单。
- 越权测试：OpenCode 发布 dispatch 应 100% 拒绝并产生日志。
