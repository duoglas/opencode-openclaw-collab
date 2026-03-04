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

---

## 证据4：JetStream 当前不可用（现场验证）
> 这是阻塞点：M1-FREEZE-v1.0 要求 JetStream（Stream/Consumer/KV/DLQ），但目标 NATS 当前返回 JetStream ServiceUnavailable。

验证方式：在 worker-orchestrator 的 venv 内使用 nats-py 调用 JetStream API。

命令：
```bash
cd /home/duoglas/ops/worker-orchestrator
source .venv/bin/activate
python - <<'PY'
import asyncio, os
from nats.aio.client import Client as NATS

NATS_URL=os.environ.get('NATS_URL','nats://100.95.183.80:4222')

async def main():
    nc=NATS()
    await nc.connect(servers=[NATS_URL], connect_timeout=3, max_reconnect_attempts=0)
    js=nc.jetstream()
    print('connected', NATS_URL)
    try:
        ai=await js.account_info()
        print('JETSTREAM_OK', ai)
    except Exception as e:
        print('JETSTREAM_ERR', type(e).__name__, str(e)[:200])
    await nc.close()

asyncio.run(main())
PY
```
真实输出：
```
connected nats://100.95.183.80:4222
JETSTREAM_ERR ServiceUnavailableError nats: ServiceUnavailableError: code=None err_code=None description='None'
```

结论：**JetStream 未启用或不可用**，因此无法创建/验证 `BRIDGE_DISPATCH_V1` stream、`bridge-dispatch-worker` consumer、KV 去重与 DLQ。
这也是当前 M2 Step1 迟迟无法“完成”的根因。

---

## 证据5：NATS 服务端版本与基础协议可响应（现场验证）
命令（原生协议握手，证明服务端版本为 NATS 2.10.29）：
```bash
python3 - <<'PY'
import socket
host='100.95.183.80'
port=4222
with socket.create_connection((host,port),timeout=2) as s:
    s.sendall(b"CONNECT {\"verbose\":false,\"pedantic\":false,\"lang\":\"python\",\"version\":\"0.0\",\"protocol\":1}\r\nPING\r\n")
    s.settimeout(2)
    data=s.recv(4096)
print(data.decode('utf-8','ignore'))
PY
```
真实输出（节选）：
```
INFO {"version":"2.10.29", ... "headers":true, ...}
PONG
```
