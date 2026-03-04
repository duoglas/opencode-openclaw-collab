# JJC-20260304-002 安全与治理 / 部署方案（兵部）

## 1. 鉴权选择与配置片段（NKey + JWT）

### 1.1 选择结论
- **控制面**：使用 `Operator -> Account -> User` 的 JWT 信任链（`nsc` 签发），实现租户隔离与吊销能力。
- **数据面连接身份**：客户端使用 **NKey Challenge-Response**，避免静态密码落盘。
- **发布/订阅权限**：放在 User JWT 的 `pub.allow / sub.allow` 与服务端 ACL 双重约束。

### 1.2 服务端核心配置片段（nats-server）
```hcl
operator: "/etc/nats/op.jwt"
resolver: MEMORY
resolver_preload: {
  # 账户JWT预加载（示意）
  AAAAA...: "/etc/nats/accounts/prod.jwt"
}

jetstream {
  store_dir: "/var/lib/nats/js"
  max_mem_store: 8Gb
  max_file_store: 2Tb
}

# TLS 建议强制开启
tls {
  cert_file: "/etc/nats/tls/tls.crt"
  key_file: "/etc/nats/tls/tls.key"
  ca_file: "/etc/nats/tls/ca.crt"
  verify: true
}
```

### 1.3 用户侧（NKey）接入示意
```bash
# 客户端通过NKey seed签名challenge，不传明文密码
export NKEY_SEED="SUAXXX..."
nats --server nats://nats-vip:4222 --user nkey-user --nkey "$NKEY_SEED" pub core.events "ok"
```

### 1.4 JWT 权限示意（User claims）
```json
{
  "sub": "U...USER",
  "iss": "A...ACCOUNT",
  "nats": {
    "pub": { "allow": ["core.events.*", "jobs.submit"] },
    "sub": { "allow": ["core.replies.*", "jobs.result.*"] },
    "data": -1,
    "payload": 1048576,
    "subs": 200
  },
  "exp": 1767225600
}
```

---

## 2. Subject ACL 示例

建议采用“**命名空间 + 动作**”模型，按服务账号拆分。

```hcl
# 账户内导出/导入（示意）
accounts: {
  APP: {
    users: [
      { user: "svc-api", permissions: {
          publish: ["app.cmd.create", "app.cmd.update", "audit.log"],
          subscribe: ["app.evt.*", "app.reply.svc-api.>"]
      }},
      { user: "svc-worker", permissions: {
          publish: ["app.evt.processed", "app.reply.>", "dlq.app.>"],
          subscribe: ["app.cmd.*", "jobs.>"]
      }}
    ]
  }
}
```

治理要点：
- 禁止业务用户订阅 `>` 与 `_INBOX.>`（仅系统组件可用）。
- 回复主题建议限定到 `app.reply.<service>.>`，避免跨服务窃听。
- 管理/观测主题（如 `audit.*`）单独账号或只读导出。

---

## 3. 速率限制策略

采用三层限流，避免单点策略失效：

1. **入口层（API Gateway/Ingress）**
   - 按 `tenant + client_id`：如 `200 req/s`，突发 `400`。
   - 超限返回 `429`，并附 `Retry-After`。

2. **消息层（发布侧）**
   - SDK 本地 token bucket（例如 `100 msg/s`，burst `200`）。
   - 发布失败进入重试队列，指数退避 `100ms -> 3s`。

3. **消费层（JetStream Consumer）**
   - `max_ack_pending` 控制并发处理数（例如 500）。
   - `ack_wait` + `max_deliver` 防止无限重投。

建议基线：
- 高优先级主题（`app.cmd.*`）保底配额；
- 低优先级（`analytics.*`）可被快速限流/丢弃；
- 限流指标入监控：`rate_limited_total`, `publish_reject_total`, `consumer_lag`。

---

## 4. HA 部署拓扑图（ASCII）

```text
                   +-----------------------------+
                   |   L4 VIP / LB (4222/8222)  |
                   +--------------+--------------+
                                  |
                 +----------------+----------------+
                 |                                 |
         +-------v-------+                 +-------v-------+
         | NATS Node A   |<----route----->| NATS Node B   |
         | az1           |<----route----->| az2           |
         | JetStream R1  |                 | JetStream R2  |
         +-------+-------+                 +-------+-------+
                 ^                                 ^
                 |            route                |
                 +---------------+-----------------+
                                 |
                         +-------v-------+
                         | NATS Node C   |
                         | az3           |
                         | JetStream R3  |
                         +-------+-------+
                                 |
                     +-----------+------------+
                     |  Shared Observability  |
                     | Prometheus/Grafana/Log |
                     +------------------------+

Clients/Services -> VIP -> 3节点NATS集群（跨AZ）
```

部署建议：
- 至少 **3 节点跨 AZ**，JetStream 流副本 `replicas=3`。
- 客户端配置多个 server URL，启用自动重连。
- 控制平面（JWT/NKey 密钥）放 KMS/HSM，禁入镜像与代码库。

---

## 5. 故障模式与降级策略

1. **单节点故障**
   - 现象：连接抖动、部分消费者重平衡。
   - 策略：客户端自动重连；消费幂等（业务键去重）；告警阈值触发扩容。

2. **分区/跨AZ链路抖动**
   - 现象：延迟升高、ack超时增多。
   - 策略：提高 `ack_wait`，临时降低非核心主题配额；核心命令流优先级提升。

3. **下游依赖（DB/外部API）故障**
   - 现象：消费堆积、重试风暴。
   - 策略：熔断 + 指数退避；将不可即时处理任务转入延迟队列；超过阈值转 DLQ。

4. **控制面异常（JWT签发/密钥服务短时不可用）**
   - 现象：新连接授权失败。
   - 策略：延长已有 token 有效窗口（短期）；启用只读/降级服务；恢复后轮换密钥。

---

## 6. DLQ（死信队列）实现建议

### 6.1 触发规则
- 同一消息达到 `max_deliver`（如 5~10 次）仍失败 -> 进入 DLQ。
- 可重试与不可重试错误分级：
  - 不可重试（参数错误、数据约束冲突）直接入 DLQ；
  - 可重试（超时、依赖暂不可用）走退避重试。

### 6.2 主题与消息格式
- DLQ 主题命名：`dlq.<domain>.<consumer>`，如 `dlq.app.worker-a`。
- 建议附带元数据：
  - `original_subject`
  - `first_seen_at`
  - `deliver_count`
  - `last_error_code`
  - `trace_id / tenant_id`

### 6.3 运维闭环
- 建立 DLQ 重放工具（按条件筛选 + 灰度重放）。
- 每日巡检 DLQ 堆积与TOP错误码。
- 设置 SLO：`DLQ backlog < X`、`24h 内处理率 > 99%`。

---

## 7. 落地清单（建议）

- [ ] 建立 Operator/Account/User JWT 签发流程与轮换制度
- [ ] 完成 subject ACL 基线模板并固化到 IaC
- [ ] 三层限流参数接入配置中心
- [ ] 跨 AZ 三节点 + JetStream R=3 上线
- [ ] 故障演练（节点故障、分区、下游超时）
- [ ] DLQ 入队、告警、重放工具上线
