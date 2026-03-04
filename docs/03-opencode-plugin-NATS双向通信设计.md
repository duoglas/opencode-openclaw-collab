# OpenCode Plugin：NATS 双向通信与 TUI 交互设计（草案）

> 目标：在每个 OpenCode 实例内提供“可收发 NATS 信号 + 在 OpenCode TUI 内可见/可干预/可回复”的能力。
> 约束：协同型任务仅 OpenClaw 下发；OpenCode 可本机自发任务；OpenCode 也可通过 OpenClaw 发起协同任务。

---

## 1. 总体设计：Plugin（前台）+ Bridge Daemon（后台）

**推荐采用两进程模型**，避免将长连接/消息循环强行塞进 TUI 插件生命周期里：

- **opencode 插件（前台，TUI 交互层）**
  - 提供一组 `/oc-*` 命令（或 opencode command plugins）
  - 展示 inbox、task 列表、事件流
  - 触发“提交协同任务/回复/取消”等动作

- **NATS Bridge Daemon（后台常驻）**
  - 维持与 NATS 的长连接
  - 订阅指定 subject（任务、事件、聊天）
  - 将消息写入本地 store（SQLite/JSONL）
  - 暴露本地 API（Unix socket/localhost HTTP）供 TUI 命令调用

> 好处：
> - 即使你没打开 TUI，Bridge 也能持续收消息
> - TUI 只负责“查询/展示/发起动作”，实现简单且稳定

---

## 2. Subject 约定（与 OpenClaw 配合）

### 2.1 核心任务流
- `oc.task.dispatch.<capability>`：OpenClaw -> OpenCode Worker（协同任务下发）
- `oc.task.event.<task_id>`：Worker -> OpenClaw（进度事件）
- `oc.task.result`：Worker -> OpenClaw（最终结果）

### 2.2 OpenCode 发起协同任务（经 OpenClaw）
- `oc.task.submit`：OpenCode -> OpenClaw（提交协同任务请求，OpenClaw 决定是否拆分/分派）

### 2.3 双向“聊天/指令补充”（可选但强烈建议）
- `oc.chat.to.<node_id>`：OpenClaw/其他节点 -> 某个 OpenCode 实例
- `oc.chat.from.<node_id>`：该 OpenCode 实例 -> OpenClaw

> 说明：
> - “聊天”不是让 Worker 互相指挥，而是用于：补充信息、追问、请求人类介入、回传短消息。

---

## 3. 消息协议（最小可用）

### 3.1 TaskDispatch（OpenClaw -> Worker）
```json
{
  "schema": "oc.task.dispatch.v1",
  "task_id": "TASK-...",
  "capability": "coding|doc|qa|ops",
  "workdir": "/path/to/repo",
  "model": "openai/gpt-5.3-codex",
  "prompt": "...",
  "dedupe_key": "sha256(...)" ,
  "timeout_sec": 1800,
  "requires_approval": false,
  "controller": {"id": "openclaw", "reply": "oc.task.result"}
}
```

### 3.2 TaskEvent（Worker -> OpenClaw）
```json
{
  "schema": "oc.task.event.v1",
  "task_id": "TASK-...",
  "node_id": "homepc-1",
  "phase": "queued|running|blocked|finished|failed",
  "progress": 0,
  "message": "running tests",
  "ts": 1730000000
}
```

### 3.3 TaskResult（Worker -> OpenClaw）
```json
{
  "schema": "oc.task.result.v1",
  "task_id": "TASK-...",
  "node_id": "homepc-1",
  "exit_code": 0,
  "summary": "...",
  "artifacts": ["/path/a", "..."],
  "stdout_tail": "...",
  "stderr_tail": "...",
  "duration_sec": 12.3
}
```

### 3.4 ChatMessage（双向补充）
```json
{
  "schema": "oc.chat.v1",
  "thread": {"task_id": "TASK-...", "session_id": "opencode-session-..."},
  "from": "openclaw|node:homepc-1",
  "to": "node:homepc-1|openclaw",
  "text": "...",
  "ts": 1730000000
}
```

---

## 4. OpenCode TUI 交互（命令设计）

> 注：若 OpenCode 没有“自定义侧边栏 UI API”，则以 **命令输出 + 可复制链接/attach 提示**为主。

### 4.1 必备命令
- `/oc-status`：显示本节点 bridge 状态（nats连接、订阅、队列长度、最近心跳）
- `/oc-inbox`：列出最近 N 条消息（任务/聊天/事件）
- `/oc-claim <task_id>`：认领任务（可选：若采用 pull/claim 模式）
- `/oc-run <task_id>`：开始执行（触发本地 worker 执行器）
- `/oc-reply <task_id> <text>`：向 OpenClaw 发送补充说明/追问
- `/oc-cancel <task_id>`：请求取消（发 `oc.task.cancel.<task_id>` 或向 OpenClaw 发取消请求）

### 4.2 任务与会话绑定（让“本机可干预”成立）
当执行协同任务时，bridge 应记录：
- `task_id -> opencode_session_id`（或 `workdir + created_at`）
- 并提供命令：`/oc-open <task_id>`
  - 若当前 TUI 支持直接切到 session，则跳转
  - 否则输出：`opencode --continue --session <id>` 的可复制命令

---

## 5. Bridge Daemon 设计

### 5.1 进程职责
- 维护 NATS 连接与订阅
- 将消息落盘（SQLite 推荐：索引好查；JSONL 也可）
- 本地 API：
  - `GET /status`
  - `GET /inbox?limit=50`
  - `POST /publish`（发消息）
  - `POST /ack`（如使用 JetStream）

### 5.2 本地存储（SQLite 示例）
- `messages(id, ts, subject, schema, task_id, direction, payload_json)`
- `tasks(task_id, status, session_id, workdir, capability, updated_at)`

### 5.3 运行方式
- systemd user service：`opencode-nats-bridge.service`
- env：NATS_URL、NODE_ID、CAPABILITIES、NATS_CREDS、SUBJECT_ALLOWLIST

---

## 6. 安全与规则固化

### 6.1 NATS 权限（强制“协同任务只能 OpenClaw 下发”）
- OpenCode 用户：禁止 publish `oc.task.dispatch.*`
- 仅允许 publish `oc.task.submit` / `oc.task.event.*` / `oc.task.result` / `oc.chat.from.*`

### 6.2 Subject Allowlist
Bridge 端再做一层 allowlist，避免误订阅/误发：
- 允许订阅：`oc.task.dispatch.<capability>`、`oc.chat.to.<node_id>`
- 允许发布：`oc.task.event.*`、`oc.task.result`、`oc.task.submit`、`oc.chat.from.<node_id>`

---

## 7. 为什么原型（worker-orchestrator）做不到 & 本设计如何补齐

原型目前是“controller 直发任务 + worker 执行 + 回包”，缺：
- 规则层（只有 OpenClaw 可下发）
- JetStream 可靠队列
- 会话绑定（可干预）
- 双向聊天与追问

本设计通过：
- subject/ACL 强制权限
- bridge 常驻接收 + 落盘
- TUI 命令把消息/任务映射到 session
- chat subject 支持双向补充

---

## 8. MVP 里程碑（建议 2~3 天可出）

1) Bridge：连接 NATS + 订阅 dispatch + 落盘 inbox
2) TUI 命令：`/oc-status` `/oc-inbox` `/oc-reply`
3) Worker 执行：收到 dispatch 后调用 `opencode run --attach <serve_url>` 并发 result/event
4) 会话绑定：记录 session_id，提供 `/oc-open <task_id>` 输出跳转命令

---

## 9. 后续增强
- JetStream ack/retry/dead-letter
- 优先级与并发控制
- 统一 trace_id（跨 OpenClaw/Worker/Telegram）
- 任务产物上传/索引
