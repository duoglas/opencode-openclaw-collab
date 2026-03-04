# JetStream Bootstrap (现场执行记录)

时间：2026-03-04 21:55~21:56
执行机：OpenClaw host（100.114.215.115）
目标 NATS：`nats://100.95.183.80:4222`

## 0) 前置：绕过代理访问监控接口（8222）
本机存在 HTTP(S) 代理环境变量，访问 tailscale IP 需要显式 `--noproxy "*"`：
```bash
curl -i --noproxy "*" http://100.95.183.80:8222/jsz | head
```

## 1) 安装 nats CLI（无 root）
- 从 natscli v0.3.1 的 .deb 解包并安装到 `~/.local/bin/nats`

## 2) JetStream/Stream/Consumer/KV 创建结果
### 2.1 account info
```bash
nats --server nats://100.95.183.80:4222 account info
```
- JetStream OK
- Streams/Consumers 初始均为 0

### 2.2 streams
已创建：
- `BRIDGE_DISPATCH_V1` subjects=`openclaw.dispatch.v1` max_age=72h storage=file
- `BRIDGE_RESULT_V1` subjects=`openclaw.result.v1` max_age=72h storage=file
- `BRIDGE_DLQ_V1` subjects=`bridge.dlq.dispatch.v1` max_age=168h storage=file

验证：
```bash
nats --server nats://100.95.183.80:4222 stream ls
```

### 2.3 consumers
已创建：
- `BRIDGE_DISPATCH_V1` → `bridge-dispatch-worker`（pull, ack explicit, wait=30s, max_deliver=6, filter=openclaw.dispatch.v1）
- `BRIDGE_RESULT_V1` → `bridge-result-sink`（pull, ack explicit, wait=30s, max_deliver=6, filter=openclaw.result.v1）
- `BRIDGE_DLQ_V1` → `bridge-dlq-sink`（pull, ack explicit, wait=30s, max_deliver=1, filter=bridge.dlq.dispatch.v1）

> 备注：创建 consumer 时偶发 i/o timeout，重试后成功。

### 2.4 KV
已创建：
- `BRIDGE_DEDUP_V1` ttl=24h history=5 storage=file

验证：
```bash
nats --server nats://100.95.183.80:4222 kv ls
```

## 3) 下一步
- 进入 M2 Step2：最小链路联调（dispatch→worker→result）
- ACL 红线（OpenCode 禁发 `*.dispatch`）仍需启用 NATS JWT/NKey account+ACL 后才能做硬证据。
