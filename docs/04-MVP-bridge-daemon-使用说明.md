# ocbridge MVP 使用说明（Bridge Daemon，M1-FREEZE-v1.0）

本说明用于在 OpenCode Worker 机器上启动 NATS Bridge Daemon：
- 订阅 OpenClaw 下发的 `openclaw.dispatch.v1`（兼容订阅 `op.task.home`）
- 执行 `opencode run --attach <local serve url>`
- 回传结果到 `openclaw.result.v1`（兼容双写 `op.result.controller`）
- 本地落盘 SQLite inbox

> 说明：当前是 Step2 最小链路闭环版本。

---

## 1) 安装

```bash
git clone https://github.com/duoglas/opencode-openclaw-collab.git
cd opencode-openclaw-collab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

确保该机已安装 opencode：
```bash
opencode --version
```

---

## 2) 配置（环境变量示例）

建议写入 `~/.config/ocbridge/env`：

```bash
export NATS_URL='nats://100.95.183.80:4222'
export OC_NODE_ID='homepc-1' # 优先于 NODE_ID
export NODE_ID='homepc-1'
export CAPABILITY='coding' # coding/doc/qa/ops
export CHAT_TO_PREFIX='oc.chat.to.'
export CHAT_FROM_PREFIX='oc.chat.from.'

# M1-FREEZE-v1.0 新subject + 旧subject兼容
export DISPATCH_SUBJECTS='openclaw.dispatch.v1,op.task.home'
export RESULT_SUBJECTS='openclaw.result.v1,op.result.controller'

# 旧单subject兼容参数（可留空）
export DISPATCH_SUBJECT=''
export RESULT_SUBJECT=''

export EVENTS_PREFIX='oc.task.event'
export HEARTBEAT_SUBJECT='oc.worker.heartbeat'
export RUN_TIMEOUT='900'
export OPENCODE_SERVE_HOST='127.0.0.1'
export OPENCODE_SERVE_PORT='4096'
export OCBRIDGE_DB="$HOME/.local/share/ocbridge/bridge.db"
```

---

## 3) 启动 bridge 进程

```bash
source ~/.config/ocbridge/env
cd ~/opencode-openclaw-collab
source .venv/bin/activate
python -m ocbridge.bridge_daemon
```

启动后行为：
- 自动确保本机 `opencode serve` 在 `127.0.0.1:4096` 可用
- 订阅 `openclaw.dispatch.v1` 与 `op.task.home`
- 订阅 `oc.chat.to.<node_id>`（由 `CHAT_TO_PREFIX + node_id` 生成）
- 结果双写到 `openclaw.result.v1` 与 `op.result.controller`
- `/oc-reply` 发布到 `CHAT_FROM_PREFIX + node_id`（默认 `oc.chat.from.<node_id>`）
- 每 60 秒发送 `oc.worker.heartbeat`

---

## 4) dispatch → worker → result 端到端跑通步骤

### Step A：启动结果监听（控制端）

```bash
# 新subject
nats sub openclaw.result.v1 --server "$NATS_URL"
# 旧subject（兼容验证）
nats sub op.result.controller --server "$NATS_URL"
```

### Step B：启动 bridge（worker 侧）

```bash
python -m ocbridge.bridge_daemon
```

### Step C：发送 dispatch 消息

```bash
nats pub openclaw.dispatch.v1 '{
  "schema":"oc.task.dispatch.v1",
  "task_id":"TASK-DEMO-001",
  "capability":"coding",
  "prompt":"Say hello from ocbridge minimal chain",
  "model":"openai/gpt-5.3-codex",
  "workdir":"",
  "timeout_sec":120,
  "dedupe_key":"",
  "requires_approval":false,
  "created_at":0,
  "reply_subject":"openclaw.result.v1"
}' --server "$NATS_URL"
```

### Step D：验收

- 在 `openclaw.result.v1` 与 `op.result.controller` 都能收到同一 task_id 的结果消息。
- 本地 DB 可查消息轨迹：

```bash
sqlite3 "$OCBRIDGE_DB" "select direction,subject,task_id,datetime(ts,'unixepoch') from messages order by id desc limit 20;"
```

---

## 5) 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

当前覆盖：
- 新旧 subject 解析与去重
- 结果双写行为
- 默认 subject 冻结值存在性

---

## 6) TUI 路由A：无人值守（auto）与有人值守（manual）

> 目标：同一套命令支持两种运行模式。`auto` 自动执行，`manual` 先入队等待人工认领。

### 6.1 模式说明

- `auto`（无人值守）
  - 收到 `oc.chat.to.<node_id>` / 任务消息后，节点可自动进入执行流程。
  - 适合夜间批处理、固定任务类型。
- `manual`（有人值守）
  - 新任务先进入 pending，需人工 `/oc-claim` + `/oc-run`。
  - 适合高风险改动、需要人工确认的任务。

### 6.2 命令速查（最小必备）

- `/oc-mode [auto|manual]`
  - 查看或切换本节点模式。
- `/oc-pending`
  - 查看待处理任务列表（pending queue）。
- `/oc-claim <task_id>`
  - 在 manual 模式认领任务。
- `/oc-run <task_id>`
  - 启动任务执行（触发本地 worker）。
- `/oc-reply <task_id> <text>`
  - 向控制端回发消息，发布到 `oc.chat.from.<node_id>`。

### 6.3 典型流程

- Auto：`/oc-mode auto` → 收到任务/聊天 → 自动执行 → 必要时 `/oc-reply` 补充。
- Manual：`/oc-mode manual` → `/oc-pending` 查队列 → `/oc-claim <task_id>` → `/oc-run <task_id>` → `/oc-reply <task_id> <text>`。

### 6.4 端到端示例（`oc.chat.to.<node>` → `oc.chat.from.<node>`）

1) 控制端发给节点：

```bash
nats pub "oc.chat.to.homepc-1" '{
  "schema":"oc.chat.v1",
  "thread":{"task_id":"TASK-DEMO-CHAT-001"},
  "from":"openclaw",
  "to":"node:homepc-1",
  "text":"请处理 TASK-DEMO-CHAT-001，并反馈执行计划",
  "ts":1730000000
}' --server "$NATS_URL"
```

2) 节点侧（TUI）：

```text
/oc-mode manual
/oc-pending
/oc-claim TASK-DEMO-CHAT-001
/oc-run TASK-DEMO-CHAT-001
/oc-reply TASK-DEMO-CHAT-001 已开始执行，预计 15 分钟内回传结果。
```

3) 控制端监听回包：

```bash
nats sub "oc.chat.from.homepc-1" --server "$NATS_URL"
```

看到 `oc.chat.from.homepc-1` 收到上述回复，即闭环完成。
