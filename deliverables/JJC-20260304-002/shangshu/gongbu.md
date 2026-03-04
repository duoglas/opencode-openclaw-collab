# JJC-20260304-002 工部工程交付草案（M1/M2）

> 范围：仅输出方案草案与关键伪代码，不涉及代码仓库真实实现。

## 0. 目标与里程碑

### M1（最小可用链路）
- 打通 `OpenCode -> bridge -> OpenClaw` 单向消息通路。
- 落地统一消息包络（envelope）与基础幂等（去重表 + TTL）。
- 支持有限重试（指数退避）与失败落盘（DLQ subject）。

### M2（双向可靠交付）
- 增加 `OpenClaw -> bridge -> OpenCode` 回执/事件回流。
- 引入状态机（RECEIVED/PROCESSING/SUCCEEDED/FAILED/DLQ）与可观测指标。
- 引入可配置重试策略（按错误分类）与人工重放接口。

---

## 1) NATS subject 与消息 schema（JSON 示例）

## 1.1 Subject 规划

建议命名：`{domain}.{source}.{target}.{event}.{version}`

- OpenCode 发往 OpenClaw：
  - `jjc.opencode.openclaw.task.request.v1`
  - `jjc.opencode.openclaw.task.cancel.v1`
- OpenClaw 发往 OpenCode：
  - `jjc.openclaw.opencode.task.result.v1`
  - `jjc.openclaw.opencode.task.progress.v1`
- 统一错误/死信：
  - `jjc.bridge.dlq.v1`
  - `jjc.bridge.retry.exhausted.v1`

## 1.2 通用消息包络（Envelope）

```json
{
  "message_id": "msg_01HPYQ8W6PK3YQ9CX8D8Y3Y9G7",
  "idempotency_key": "JJC-20260304-002:task_7788:request",
  "trace_id": "tr_2f3d3dc2f9d24e9a",
  "correlation_id": "corr_task_7788",
  "event_type": "task.request",
  "event_version": "v1",
  "source": "opencode",
  "target": "openclaw",
  "occurred_at": "2026-03-04T09:30:00Z",
  "ttl_sec": 900,
  "attempt": 1,
  "payload": {}
}
```

## 1.3 示例：task.request

Subject: `jjc.opencode.openclaw.task.request.v1`

```json
{
  "message_id": "msg_01HPYQ8W6PK3YQ9CX8D8Y3Y9G7",
  "idempotency_key": "JJC-20260304-002:task_7788:request",
  "trace_id": "tr_2f3d3dc2f9d24e9a",
  "correlation_id": "corr_task_7788",
  "event_type": "task.request",
  "event_version": "v1",
  "source": "opencode",
  "target": "openclaw",
  "occurred_at": "2026-03-04T09:30:00Z",
  "ttl_sec": 900,
  "attempt": 1,
  "payload": {
    "task_id": "task_7788",
    "project_id": "proj_alpha",
    "instruction": "generate M1 draft",
    "priority": "high",
    "operator": "gongbu"
  }
}
```

## 1.4 示例：task.result

Subject: `jjc.openclaw.opencode.task.result.v1`

```json
{
  "message_id": "msg_01HPYQG2M9A6NNB9GG18W8FQK4",
  "idempotency_key": "JJC-20260304-002:task_7788:result",
  "trace_id": "tr_2f3d3dc2f9d24e9a",
  "correlation_id": "corr_task_7788",
  "event_type": "task.result",
  "event_version": "v1",
  "source": "openclaw",
  "target": "opencode",
  "occurred_at": "2026-03-04T09:31:25Z",
  "ttl_sec": 900,
  "attempt": 1,
  "payload": {
    "task_id": "task_7788",
    "status": "SUCCEEDED",
    "output_uri": "s3://jjc/results/task_7788.json",
    "summary": "Draft generated"
  }
}
```

---

## 2) bridge 服务架构与关键接口

## 2.1 模块结构（建议）

```text
bridge/
  cmd/
    bridge-main
  internal/
    nats/
      publisher
      subscriber
    contract/
      envelope
      schemas
    router/
      subject-router
    idempotency/
      key-store
    retry/
      retry-policy
      scheduler
    dlq/
      dlq-publisher
    adapters/
      opencode-adapter
      openclaw-adapter
    observability/
      logger
      metrics
      tracing
```

## 2.2 核心职责
- **Router**：按 subject/event_type 路由至对应适配器。
- **Contract Validator**：校验 envelope + payload schema。
- **Idempotency Guard**：判重、记录处理状态、保护重复消费。
- **Retry Scheduler**：按策略延迟重投或转 DLQ。
- **DLQ Publisher**：发送失败上下文，供人工/批处理重放。

## 2.3 关键接口（抽象）

```text
Publish(subject, envelope) -> error
Handle(subject, envelope) -> HandleResult{status, retryable, reason}
CheckAndLock(idempotencyKey, ttlSec) -> {fresh|duplicate|inflight}
MarkDone(idempotencyKey, resultMeta) -> error
ScheduleRetry(envelope, nextAttempt, delayMs, reason) -> error
SendDLQ(envelope, reason, finalAttempt) -> error
```

---

## 3) OpenCode 侧适配器接口

## 3.1 输入/输出
- 输入：OpenCode 任务意图（task.request / task.cancel）。
- 输出：标准化 envelope 发布到 NATS。

## 3.2 接口建议

```text
BuildTaskRequestEnvelope(input) -> Envelope
PublishTaskRequest(input) -> {messageId, correlationId}
PublishTaskCancel(input) -> {messageId, correlationId}
OnTaskResult(envelope) -> AckResult
OnTaskProgress(envelope) -> AckResult
```

## 3.3 适配职责
- OpenCode 内部模型 -> 公共 contract 字段映射。
- 生成 `idempotency_key` 与 `correlation_id`。
- 接收结果/进度事件并回写 OpenCode 本地状态。

---

## 4) OpenClaw 侧适配器接口

## 4.1 输入/输出
- 输入：NATS 上的 task.request/task.cancel。
- 输出：task.progress/task.result 到 NATS。

## 4.2 接口建议

```text
OnTaskRequest(envelope) -> HandleResult
OnTaskCancel(envelope) -> HandleResult
PublishTaskProgress(taskId, progress, detail) -> error
PublishTaskResult(taskId, status, outputUri, summary) -> error
```

## 4.3 适配职责
- 公共 contract -> OpenClaw 执行命令映射。
- 执行状态映射为 `PROCESSING/SUCCEEDED/FAILED`。
- 异常归类：`RETRYABLE` 与 `NON_RETRYABLE`。

---

## 5) 幂等键 / 重试 / backoff / DLQ 策略

## 5.1 幂等键
- 组成：`{work_order}:{task_id}:{event_type}`（示例：`JJC-20260304-002:task_7788:request`）。
- 存储：Redis/DB 去重表，字段含 `status`, `first_seen_at`, `last_seen_at`, `result_hash`。
- TTL：
  - M1：24h（覆盖日内重投）。
  - M2：可配置 24h~7d，按业务延迟窗口调整。

## 5.2 重试策略
- 仅对 `retryable=true` 错误重试。
- 最大重试：
  - M1：3 次。
  - M2：按事件类型配置（如 request=5，result=8）。

## 5.3 Backoff 建议
- 公式：`delay = min(baseMs * 2^(attempt-1), maxMs) + jitter(0~baseMs*0.2)`
- 默认参数：`baseMs=500`, `maxMs=30000`。
- 示例延迟（近似）：0.5s, 1s, 2s, 4s, 8s ... capped at 30s。

## 5.4 DLQ 策略
- 进入条件：
  1) 非重试错误；
  2) 超过最大重试次数；
  3) 消息过期（`occurred_at + ttl_sec < now`）。
- DLQ 消息包含：原始 envelope、失败原因、最后 attempt、首次/末次失败时间。
- 重放机制（M2）：提供 `ReplayDLQ(message_id)` 管理接口，重放前重新做幂等校验。

## 5.5 关键伪代码

```pseudo
function processMessage(subject, envelope):
  if isExpired(envelope.occurred_at, envelope.ttl_sec):
    sendDLQ(envelope, "expired", envelope.attempt)
    return ACK

  lockState = checkAndLock(envelope.idempotency_key, ttl=24h)
  if lockState == duplicate:
    return ACK
  if lockState == inflight:
    scheduleRetry(envelope, envelope.attempt + 1, shortDelay(), "inflight")
    return ACK

  result = routeAndHandle(subject, envelope)

  if result.status == SUCCEEDED:
    markDone(envelope.idempotency_key, result.meta)
    return ACK

  if result.retryable and envelope.attempt < maxRetry(subject):
    delay = expBackoffWithJitter(baseMs, envelope.attempt)
    scheduleRetry(envelope.withAttempt+1, envelope.attempt + 1, delay, result.reason)
    return ACK

  sendDLQ(envelope, result.reason, envelope.attempt)
  return ACK
```

---

## 6) 风险与开放问题

## 6.1 主要风险
1. **语义不一致风险**：OpenCode/OpenClaw 状态枚举不一致导致错误重试。
2. **重复消费风险**：消费者重启或网络抖动导致 at-least-once 重投。
3. **时钟漂移风险**：TTL 判断依赖时间，跨节点时钟偏差会误判过期。
4. **DLQ 积压风险**：下游长期不可用时 DLQ 快速增长。

## 6.2 缓解措施
- 建立统一状态映射表（契约版本化）。
- 幂等表 + 结果哈希校验，防止重复副作用。
- 强制 NTP 对时与服务端时间源统一。
- DLQ 配额告警、分级重放、失败原因聚类治理。

## 6.3 开放问题（需评审确认）
1. NATS 采用 Core NATS 还是 JetStream（是否要求持久化/回放）？
2. 幂等存储选 Redis 还是关系型 DB（成本/一致性权衡）？
3. M2 阶段是否要求“严格有序”或仅“最终一致”即可？
4. `task.progress` 事件的采样率与频控阈值如何定义？
5. DLQ 重放权限边界：谁可重放、是否需要审批流？
