# 与现有 NATS / Tailscale 配置对齐（参考 worker-orchestrator）

本项目 ocbridge 的默认配置将参考你现有的原型工程：`~/ops/worker-orchestrator`。

## 1) 已知现网 NATS

来自：`/home/duoglas/ops/worker-orchestrator/.env`

- NATS_URL = `nats://100.95.183.80:4222`

> 这通常是 VPS 的 Tailscale IP（100.x）。

## 2) 现有 subject（旧原型）

- TASK_SUBJECT = `op.task.home`
- RESULT_SUBJECT = `op.result.controller`

## 3) ocbridge（新方案）subject 映射建议

为了平滑迁移与减少改动，建议：

- **保留旧 subject 作为兼容层**（可选）：
  - `op.task.home` -> 等价于 `oc.task.dispatch.coding`（或你指定 capability）
  - `op.result.controller` -> 等价于 `oc.task.result`

- **新方案正式 subject（推荐）**：
  - OpenClaw -> Worker：`oc.task.dispatch.<capability>`
  - Worker -> OpenClaw：`oc.task.result`
  - Worker -> OpenClaw：`oc.task.event.<task_id>`
  - Worker -> OpenClaw：`oc.worker.heartbeat`
  - OpenCode -> OpenClaw：`oc.task.submit`

> 落地方式：
> - 第一阶段：ocbridge 支持同时订阅旧/新 subject（兼容迁移）
> - 第二阶段：切到全新 subject + NATS ACL 强制权限

## 4) OpenCode serve 配置

来自现有 `.env`：
- OPENCODE_SERVE_HOST = `127.0.0.1`
- OPENCODE_SERVE_PORT = `4096`
- OPENCODE_SERVE_START_TIMEOUT = `20`

ocbridge 当前也默认：
- `OPENCODE_SERVE_HOST=127.0.0.1`
- `OPENCODE_SERVE_PORT=4096`

## 5) Tailnet 访问策略建议

- NATS 4222 端口仅绑定到 VPS 的 Tailscale IP
- Worker 机器无需开放 opencode serve 端口到网络（本机 loopback 即可）
- 你若需要远程干预某台 worker，可用 `tailscale ssh` 或在该机本地打开 opencode TUI/web

## 6) 开工前检查清单

1. `tailscale status` 确认 worker 能直连 `100.95.183.80`
2. `nc -vz 100.95.183.80 4222` 确认端口通
3. worker 本机 `opencode serve` 可起：`curl -s http://127.0.0.1:4096/`（能连通即可）

