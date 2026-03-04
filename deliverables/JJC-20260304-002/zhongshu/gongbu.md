# 工部交付（JJC-20260304-002）

## 1. 目标
设计并实现 OpenCode 与 OpenClaw 的 NATS 协同桥核心技术方案，覆盖消息契约、桥接服务与双侧适配器。

## 2. 交付范围
- NATS Subject 规范
  - `opencode.>`：OpenCode 侧事件
  - `openclaw.>`：OpenClaw 侧事件
  - `bridge.control.>`：桥接控制与健康探测
- Bridge 服务模块
  - 连接管理（NATS 连接/重连/心跳）
  - 消息路由（双向转发、主题映射）
  - 幂等控制（message-id 去重窗口）
  - 重试机制（指数退避）
  - DLQ 投递（失败消息沉淀）
- 适配器接口
  - OpenCode Adapter：发布任务事件、订阅执行回执
  - OpenClaw Adapter：订阅任务指令、发布状态与结果

## 3. 建议实现骨架
```text
bridge/
  config/
  router/
  retry/
  idempotency/
  dlq/
  adapters/
    opencode/
    openclaw/
```

## 4. 关键数据契约（纲要）
- Header
  - `trace_id`
  - `message_id`
  - `source`
  - `timestamp`
- Body
  - `type`（command/event/result）
  - `payload`（业务载荷）
  - `meta`（版本、优先级）

## 5. 里程碑建议
- M1：契约文档 + 主题规范
- M2：最小链路可用（命令->执行->回执）
- M3：可靠性增强（重试/幂等/DLQ）
- M4：联调验收 + 发布手册

## 6. 下一步
- 与兵部/刑部联动完成压测基线和故障演练脚本。
- 输出 P95 延迟、成功率、重试命中率观测面板。
