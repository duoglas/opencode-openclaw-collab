# RouteA（VPS NATS）Subject 级最小放行策略与 `nsc` 示例

> 目标：对 RouteA 仅放行业务必须的 subject，默认拒绝（implicit deny），并对高风险方向做显式 deny。

## 1) 角色：`opencode_worker`

### 最小权限（必须）

- **允许 publish**：`oc.chat.from.*`
- **允许 subscribe**：`oc.chat.to.<node_id>`（仅本节点单播队列）
- **禁止 publish**：`oc.chat.to.*`（防止 worker 伪造下行/冒充 dispatcher）

### `node_id` 生成与约束

- `node_id` 必须是 **单 token**（不能包含 `.`，否则会多段化 subject）
- 建议只用：`[a-z0-9_-]`

示例（由主机名生成一个安全的 node_id）：

```bash
NODE_ID="$(hostname -s | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9_-' '-')"
echo "$NODE_ID"
# 示例输出：worker-01
```

## 2) 角色：`openclaw_dispatcher` / `bridge_service`（按需最小权限）

### `openclaw_dispatcher`（典型最小集合）

- **允许 publish**：`oc.chat.to.*`（向节点下发）
- **允许 subscribe**：`oc.chat.from.*`（收节点回传）
- 不需要的前缀一律不放行。

### `bridge_service`（仅桥接需要）

- 仅放行其实际桥接路径（例如只转发 `oc.chat.from.*` -> 上游，则只需对 `oc.chat.from.*` 的 sub + 上游目标 pub）。
- 若承担双向桥接，再增加对应方向 subject；不要直接给 `>`。

## 3) `nsc edit user` 命令示例（allow/deny）

> 不同 nsc 版本参数细节可能略有差异（可 `nsc edit user -h` 确认），以下为常用 allow/deny 写法示例。

### 3.1 `opencode_worker`（模板）

```bash
# 先生成/确定 node_id（示例）
NODE_ID="worker-01"

# 仅允许 worker 上行发布；仅允许订阅本节点下行；显式禁止发布任意 oc.chat.to.*
nsc edit user --account CORE opencode_worker \
  --allow-pub "oc.chat.from.*" \
  --allow-sub "oc.chat.to.${NODE_ID}" \
  --deny-pub  "oc.chat.to.*"
```

### 3.2 `openclaw_dispatcher`（模板）

```bash
nsc edit user --account CORE openclaw_dispatcher \
  --allow-pub "oc.chat.to.*" \
  --allow-sub "oc.chat.from.*"
```

### 3.3 `bridge_service`（按需示例）

```bash
# 示例：仅消费 worker 上行并转发，不开放全量权限
nsc edit user --account CORE bridge_service \
  --allow-sub "oc.chat.from.*"

# 若 bridge_service 还需要回写某一类下行，再最小化增加：
# --allow-pub "oc.chat.to.*"
```

## 4) 验证命令（应成功 / 应失败）

> 下面以 `opencode_worker.creds` 验证 publish 权限。

```bash
export NATS_URL="nats://<VPS_NATS_IP>:4222"
export CREDS="/path/to/opencode_worker.creds"

# 应成功：worker 允许向 oc.chat.from.* 发布
nats --server "$NATS_URL" --creds "$CREDS" \
  pub "oc.chat.from.worker-01" '{"ok":true,"case":"allowed"}'

# 应失败：worker 被显式禁止向 oc.chat.to.* 发布
nats --server "$NATS_URL" --creds "$CREDS" \
  pub "oc.chat.to.worker-01" '{"ok":false,"case":"denied"}'
# 期望输出包含 permission violation / permissions error
```

如需同时验证订阅范围（可选）：

```bash
# 应成功：仅订阅本节点
nats --server "$NATS_URL" --creds "$CREDS" sub "oc.chat.to.worker-01"

# 应失败：越权订阅其他节点
nats --server "$NATS_URL" --creds "$CREDS" sub "oc.chat.to.worker-02"
```
