# JJC-20260304-002 · M2 最小链路联调 Next Steps（执行清单）

## A. 环境准备（兵部主责，工部配合）
1. 启动 NATS（建议 JetStream 开启，便于 DLQ/重放）
2. 启用认证：NKey/JWT（按 M1 决议）
3. 下发三方凭证：OpenCode / OpenClaw / bridge
4. 配置 ACL：允许各自 subject 范围 + 必要的回执/控制面

产出：
- NATS 连接信息、凭证发放方式、ACL 配置片段

## B. 最小链路实现（工部主责）
1. bridge：
- 订阅 OpenCode 指令 subject
- 转发至 OpenClaw 指令 subject
- 订阅 OpenClaw 回执 subject
- 回写至 OpenCode 回执 subject
2. 幂等/重试：先做“幂等键透传 + 最小重试（固定次数）”，DLQ 可先落 JetStream stream

产出：
- 可跑通的 Demo：一条任务命令 + 一条执行回执

## C. 联调验收（刑部主责，户部配合）
1. E2E 用例：成功、失败可重试、失败入 DLQ、断链恢复
2. 压测：约定负载下统计 P95 < 200ms
3. 指标与日志：trace_id 贯穿，关键指标可采集

产出：
- 联调报告 + 指标截图/原始数据

## D. 文档（礼部主责）
1. 记录契约冻结版本与变更流程
2. 发布/回滚步骤（按 M4 模板逐步完善）

产出：
- 联调运行手册（最小版）
