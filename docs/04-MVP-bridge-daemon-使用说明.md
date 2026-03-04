# ocbridge MVP 使用说明（Bridge Daemon）

本说明用于在每台 OpenCode Worker 机器上启动一个 NATS Bridge Daemon：
- 订阅 OpenClaw 下发的 `oc.task.dispatch.<capability>`
- 执行 `opencode run --attach <local serve url>`
- 上报事件与结果到 NATS
- 本地落盘 inbox（SQLite）供 TUI/命令查看

> 说明：当前是 MVP，只覆盖任务下发->执行->结果回传的闭环。

---

## 1) 安装

```bash
git clone https://github.com/duoglas/opencode-openclaw-collab.git
cd opencode-openclaw-collab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

确保该机已安装 opencode，并能运行：
```bash
opencode --version
```

---

## 2) 配置（环境变量）

建议写入 `~/.config/ocbridge/env`（自行选择位置）：

```bash
export NATS_URL='nats://<tailscale-ip>:4222'
export NODE_ID='homepc-1'
export CAPABILITY='coding' # coding/doc/qa/ops
export DISPATCH_SUBJECT='oc.task.dispatch.coding'
export RESULT_SUBJECT='oc.task.result'
export EVENTS_PREFIX='oc.task.event'
export HEARTBEAT_SUBJECT='oc.worker.heartbeat'
export RUN_TIMEOUT='900'
export OPENCODE_SERVE_HOST='127.0.0.1'
export OPENCODE_SERVE_PORT='4096'
export OCBRIDGE_DB="$HOME/.local/share/ocbridge/bridge.db"
```

---

## 3) 启动

```bash
source ~/.config/ocbridge/env
cd ~/opencode-openclaw-collab
source .venv/bin/activate
python -m ocbridge.bridge_daemon
```

启动后它会：
- 确保本机 `opencode serve` 在 `127.0.0.1:4096` 可用（若不可用则尝试拉起）
- 订阅 `DISPATCH_SUBJECT`
- 每 60 秒发送一次心跳到 `HEARTBEAT_SUBJECT`

---

## 4) 本地收件箱（inbox）

Bridge 会将收发消息落盘在 SQLite：

- `~/.local/share/ocbridge/bridge.db`

后续我们会补：
- `ocbridge cli`：查看最近消息/按 task_id 过滤
- OpenCode TUI 命令：`/oc-inbox` 等

---

## 5) 下一步（开工清单）

- [ ] JetStream ack/retry（确保 Worker 离线消息不丢）
- [ ] 增加 Chat subjects：`oc.chat.to.<node>` / `oc.chat.from.<node>`
- [ ] 增加本地 API（unix socket / localhost HTTP）供 TUI 调用
- [ ] 增加 session_id 绑定与 `/oc-open <task_id>`
