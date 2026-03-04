# JJC-20260304-002 · 工部 Step2 实施回执（ocbridge 最小链路）

## 1) bridge 进程启动命令与配置示例（含 NATS_URL）

### 配置
```bash
export NATS_URL='nats://100.95.183.80:4222'
export NODE_ID='homepc-1'
export CAPABILITY='coding'
export DISPATCH_SUBJECTS='openclaw.dispatch.v1,op.task.home'
export RESULT_SUBJECTS='openclaw.result.v1,op.result.controller'
export EVENTS_PREFIX='oc.task.event'
export HEARTBEAT_SUBJECT='oc.worker.heartbeat'
export RUN_TIMEOUT='900'
export OPENCODE_SERVE_HOST='127.0.0.1'
export OPENCODE_SERVE_PORT='4096'
export OCBRIDGE_DB="$HOME/.local/share/ocbridge/bridge.db"
```

### 启动
```bash
source ~/.config/ocbridge/env
cd /home/duoglas/.openclaw/workspace-taizi/opencode-openclaw-collab
source .venv/bin/activate
python -m ocbridge.bridge_daemon
```

---

## 2) dispatch → worker → result 端到端跑通步骤

1. 控制端监听结果：
   ```bash
   nats sub openclaw.result.v1 --server "$NATS_URL"
   nats sub op.result.controller --server "$NATS_URL"
   ```
2. worker 启动 bridge：
   ```bash
   python -m ocbridge.bridge_daemon
   ```
3. 发布 dispatch（新subject）：
   ```bash
   nats pub openclaw.dispatch.v1 '{"schema":"oc.task.dispatch.v1","task_id":"TASK-DEMO-001","capability":"coding","prompt":"Say hello from ocbridge minimal chain","model":"openai/gpt-5.3-codex","timeout_sec":120}' --server "$NATS_URL"
   ```
4. 验证结果：
   - `openclaw.result.v1` 收到结果
   - `op.result.controller` 收到同 task_id 结果（双写兼容）
   - SQLite 有收发轨迹：
     ```bash
     sqlite3 "$OCBRIDGE_DB" "select direction,subject,task_id from messages order by id desc limit 20;"
     ```

---

## 3) 代码落盘路径 + PR/commit 信息

### 代码落盘路径
- `ocbridge/bridge_daemon.py`
- `tests/test_bridge_subjects.py`
- `tests/test_e2e_minimal_chain.py`
- `docs/04-MVP-bridge-daemon-使用说明.md`
- `deliverables/JJC-20260304-002/gongbu/step2-ocbridge-minimal-chain.md`

### Commit/PR
- 分支：待推送后回填
- commit：待推送后回填
- PR：待推送后回填（或标注 direct push）

---

## 补充说明
- 已按 M1-FREEZE-v1.0 采用新 subject：`openclaw.dispatch.v1` / `openclaw.result.v1`
- 已实现旧 subject 兼容：`op.task.home`（双读）/ `op.result.controller`（双写）
