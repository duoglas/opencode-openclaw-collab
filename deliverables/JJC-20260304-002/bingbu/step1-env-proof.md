# JJC-20260304-002 · M2 Step1 环境就绪（现场硬证据）

> 口径：M1-FREEZE-v1.0（皇上已准）
> 时间：2026-03-04 17:52 Asia/Shanghai

## 环境参数（来自 worker-orchestrator/.env）
- NATS_URL: `nats://100.95.183.80:4222`
- 旧 Subject（兼容验证用）:
  - TASK_SUBJECT: `op.task.home`
  - RESULT_SUBJECT: `op.result.controller`
- Worker Node:
  - NODE_ID: `worker-home`
  - RUN_TIMEOUT: `300`

证据文件：`/home/duoglas/ops/worker-orchestrator/.env`

---

## 证据1：TCP 端口连通（4222）
命令：
```bash
nc -vz -w 3 100.95.183.80 4222
```
真实输出：
```
Connection to 100.95.183.80 4222 port [tcp/*] succeeded!
```

---

## 证据2：Worker 已连接并监听任务 Subject（旧 subject）
命令：
```bash
systemctl --user status opencode-worker.service --no-pager
```
关键输出（节选）：
- `Active: active (running)`
- `[worker] listening on op.task.home via nats://100.95.183.80:4222`

---

## 证据3：端到端闭环（Controller→NATS→Worker→Result subject）
> 使用仓库自带 controller 的 builtin healthcheck prompt 验证消息闭环可用。

命令：
```bash
cd /home/duoglas/ops/worker-orchestrator
./run_controller.sh openai/gpt-5.2 "请只输出 ALIVE_OK 和当前主机名。" 30
```
真实输出（节选）：
```json
{
  "task_id": "3348eb94-782a-4f50-bd75-7034bcd796e0",
  "node": "worker-home",
  "exit_code": 0,
  "stdout": "ALIVE_OK\nduoglas-VMware-Virtual-Platform\n",
  "stderr": "",
  "duration_sec": 0.0,
  "schema_version": "v1"
}
```

---

## 尚缺硬证据（待补齐，影响进入 M2 Step2）
1) **JetStream 可用性**：当前 NATS python client 未在全局环境可直接调用，建议在 worker-orchestrator venv 内补一条 `js.account_info()` 证据，或用 nats CLI 证明 JS 启用。
2) **ACL 红线（OpenCode 禁发 `*.dispatch`）**：需要在目标 NATS 上启用 JWT/ACL 后，提供一条“以 OpenCode 身份 publish dispatch 被拒绝”的真实输出（错误码/日志）。
3) **新 subject（openclaw.dispatch.v1 / openclaw.result.v1 等）创建**：需在启用 JetStream 后给出 stream/consumer/KV 创建证据。

> 结论：连通性与旧 subject 的 worker 闭环已证实；JetStream/ACL/新 subject 证据需要兵部在具备 creds/CLI 的环境继续采证。
