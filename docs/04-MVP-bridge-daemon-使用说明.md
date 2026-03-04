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
export NODE_ID='homepc-1'
export CAPABILITY='coding' # coding/doc/qa/ops

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
- 结果双写到 `openclaw.result.v1` 与 `op.result.controller`
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
