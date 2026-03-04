# JJC-20260304-002 · 兵部安全加固落地（NKey/JWT/TLS、ACL、轮换、切流/回滚演练）

> 目标：将消息/调度总线（NATS/NKey/JWT 体系）安全基线按修订方案落地，形成**可执行**的配置模板、ACL 矩阵、凭证轮换流程、切流/回滚演练脚本（可直接改变量后运行）。

---

## 0. 范围与假设

- 适用对象：NATS 2.x（Operator/Account/User JWT + NKey），以及承载业务的 subject 体系。
- 强制要求：
  - **全链路 TLS**（client/cluster/leafnode/websocket 如使用）
  - **强身份**：Operator/Account/User JWT + NKey（禁用匿名/明文 user/pass）
  - **最小权限 ACL**：默认拒绝（implicit deny），仅显式 allow；并对高危 subject 加显式 deny 兜底
  - **显式 deny**：`OpenCode` 角色 **禁止发布** `*.dispatch`
  - **可轮换**：Signing key / User creds / TLS 证书均需可轮换
  - **可演练**：切流/回滚脚本可在预演环境跑通后再上生产

> 注：具体 subject 命名（如 `xxx.dispatch`/`svc.*`）请以实际为准；本文提供模板与“必须实现的约束点”。

---

## 1) NKey/JWT/TLS 基线

### 1.1 NATS Server 配置（示例模板）

> 文件：`/etc/nats/nats-server.conf`（路径按实际调整）

```hcl
# =========
# Network
# =========
port: 4222
http: 8222

# =========
# TLS (Client)
# =========
tls {
  cert_file: "/etc/nats/tls/server.crt"
  key_file:  "/etc/nats/tls/server.key"
  ca_file:   "/etc/nats/tls/ca.crt"
  verify: true          # 要求客户端证书（mTLS），若暂不启用 mTLS 可设 false，但仍建议尽快开启
  timeout: 2
}

# =========
# TLS (Cluster) - 如使用
# =========
cluster {
  name: "core"
  listen: "0.0.0.0:6222"
  tls {
    cert_file: "/etc/nats/tls/cluster.crt"
    key_file:  "/etc/nats/tls/cluster.key"
    ca_file:   "/etc/nats/tls/ca.crt"
    verify: true
  }
}

# =========
# Operator JWT (NKey/JWT)
# =========
operator: "/etc/nats/jwt/operator.jwt"
resolver: {
  type: full
  dir: "/var/lib/nats/jwt"
  allow_delete: false
  interval: "2m"
  timeout: "2s"
}

# 安全：禁用非 JWT 方式的用户认证（避免误开匿名/静态密码）
# authorization { ... }  # 不使用传统 auth block

# =========
# Observability
# =========
# 建议：打开慢订阅、连接上限、JetStream 审计等（按业务启用）
```

**落地要点**
- `operator` + `resolver` 是 Operator 模式的核心；账号/用户 JWT 必须放入 resolver 目录（或通过 nsc push）。
- TLS：
  - 生产建议 client mTLS（`verify: true`）。
  - 证书到期/轮换必须支持热加载（见 §3/§4 演练）。

### 1.2 生成与管理（nsc）

> 需要 `nsc`（NATS Account/JWT 工具）。命令供参考：

```bash
# 1) 初始化 operator/account（一次性）
nsc add operator --name OP
nsc add account --name CORE

# 2) 为 account 创建 signing key（用于签发用户）
nsc edit account CORE --sk generate

# 3) 为各角色创建 user（签发 creds）
nsc add user --account CORE --name svc_api
nsc add user --account CORE --name opencode
nsc add user --account CORE --name ci_cd

# 4) 导出 operator/account/user jwt/creds
nsc describe operator --json > operator.json
nsc generate config --nats-resolver --sys-account CORE

# creds 通常在：~/.nsc/keys/creds/.../*.creds
```

**交付建议**
- Operator signing keys、Account signing keys：只存放于受控密钥系统（Vault/KMS/离线机），线上只落地需要的 jwt/creds（最小化暴露面）。

---

## 2) ACL 矩阵（含显式 deny：OpenCode publish *.dispatch）

### 2.1 角色与权限矩阵（模板）

> 说明：NATS 权限模型为 allow/deny 列表；**隐式拒绝**是默认行为。为防误配，建议对关键 subject 再加 **显式 deny 兜底**。

| 角色/主体 | Publish Allow | Publish Deny | Subscribe Allow | Subscribe Deny | 备注 |
|---|---|---|---|---|---|
| `svc_api`（业务服务） | `svc.api.>` `evt.>` | `admin.>` | `svc.api.reply.>` `evt.>` | `admin.>` | 典型业务服务 |
| `ci_cd`（发布流水线） | `ci.>` `deploy.>` | `*.dispatch` | `ci.>` | `admin.>` | CI 不应触达 dispatch |
| `ops_admin`（运维） | `>` | *(空)* | `>` | *(空)* | 高权限，强审计与 MFA |
| `opencode`（OpenCode） | `opencode.>` | **`*.dispatch`** | `opencode.>` | `admin.>` | **必须实现：禁止发布 *.dispatch** |

> 重要：
> - `*.dispatch` 仅匹配 **两段** subject，如 `job.dispatch`。
> - 若实际 dispatch 为三段或更多（如 `svc.job.dispatch`），需同步加入：`*.*.dispatch` / `*.*.*.dispatch` 等，或改用更精确命名（推荐：`dispatch.>` 并 deny `dispatch.>`）。

### 2.2 用户权限配置片段（示例）

> 在 Operator/JWT 模式下，用户权限写入用户 JWT（通过 `nsc edit user` 或模板生成）。示例表达为概念：

```yaml
# user: opencode
permissions:
  publish:
    allow:
      - "opencode.>"
    deny:
      - "*.dispatch"   # ✅ 显式 deny（按修订方案必须）
  subscribe:
    allow:
      - "opencode.>"
    deny:
      - "admin.>"
```

### 2.3 审计/验证用例（必须过）

- ✅ OpenCode 发布 `job.dispatch` 必须失败（权限拒绝）
- ✅ OpenCode 发布 `opencode.task.created` 必须成功
- ✅ OpenCode 订阅自身域 `opencode.>` 必须成功
- ✅ 非运维角色访问 `admin.>` 必须失败

验证命令（示例）：
```bash
# 使用 opencode.creds
export NATS_URL=tls://nats.example.com:4222

nats --creds /secure/opencode.creds pub job.dispatch '{"test":1}'
# 期望：permission violation

nats --creds /secure/opencode.creds pub opencode.task.created '{"ok":1}'
# 期望：OK
```

---

## 3) 凭证轮换（Signing Keys / User Creds / TLS）

### 3.1 轮换对象与频率（建议）

- Operator signing key：半年~一年（重大事件立即轮换）
- Account signing key：季度~半年
- User creds（.creds）：30~90 天（高危角色更短）
- TLS 证书：按 CA 策略（常见 60~90 天），确保支持热加载

### 3.2 轮换流程（Runbook）

#### A) User creds 轮换（不停服）
1. 为用户生成新 creds（并行存在）
2. 将新 creds 分发到调用方（K8s Secret/配置中心）
3. 灰度切换：先 1% → 10% → 100%
4. 观测连接数、授权拒绝、业务错误率
5. 回收旧 creds（撤销旧 user jwt 或 rotate user nkey）

命令参考：
```bash
# 生成新 creds（示例）
nsc edit user --account CORE opencode --generate-nkey
nsc generate creds --account CORE --name opencode > opencode.new.creds

# 推送更新到 resolver（full resolver 或 nats-account-server）
nsc push --account CORE
```

#### B) Account signing key 轮换
1. 生成新的 account signing key
2. 用新 signing key 重新签发用户 jwt（或逐个轮换）
3. 推送到 resolver
4. 观测无异常后，撤销旧 signing key（保留回滚窗口）

#### C) TLS 证书轮换（热加载优先）
1. 下发新证书文件（原路径原文件名原权限）
2. `nats-server` reload（SIGHUP 或 systemd reload）
3. 用 `openssl s_client` 验证服务端链路与证书序列号

---

## 4) 切流/回滚演练脚本（模板，可直接改变量执行）

> 目标：把“轮换/改 ACL/改 TLS”从手工操作，固化为可审计脚本；每次演练产生日志与可回滚点。

### 4.1 变量约定

```bash
# 环境变量（按实际替换）
export NATS_HOST="nats-1.example.com"
export SSH_USER="ops"

export CONF_PATH="/etc/nats/nats-server.conf"
export JWT_DIR="/var/lib/nats/jwt"
export TLS_DIR="/etc/nats/tls"

export CREDS_OLD="/secure/opencode.creds"
export CREDS_NEW="/secure/opencode.new.creds"

# 切流窗口（秒）
export CANARY_SLEEP=60
```

### 4.2 切流演练：轮换 OpenCode creds（灰度→全量）

> 文件建议：`scripts/drill_rotate_opencode_creds.sh`（本文提供内容模板）

```bash
#!/usr/bin/env bash
set -euo pipefail

log(){ echo "[$(date -Is)] $*"; }

check_perm(){
  local creds="$1"
  log "perm-check with creds=${creds}"
  # 1) 必须拒绝 dispatch
  if nats --creds "$creds" pub job.dispatch '{"test":1}' 2>&1 | grep -qi "permission"; then
    log "OK: dispatch publish denied"
  else
    log "FAIL: dispatch publish NOT denied"; exit 1
  fi
  # 2) 必须允许 opencode 域
  nats --creds "$creds" pub opencode.task.created '{"ok":1}' >/dev/null
  log "OK: opencode publish allowed"
}

log "== Precheck (OLD) =="
check_perm "${CREDS_OLD}"

log "== Canary switch (NEW) =="
check_perm "${CREDS_NEW}"
log "sleep ${CANARY_SLEEP}s for canary observation"
sleep "${CANARY_SLEEP}"

log "== Finalize =="
log "(应用侧) 将 Secret/配置指向 NEW creds，并滚动重启/热加载"
log "Done"
```

**回滚点**
- 应用侧随时可切回 `CREDS_OLD`（保留旧 creds 有效期 ≥ 24h 回滚窗口）。

### 4.3 切流演练：服务端 reload（TLS/ACL/JWT 更新）

> 文件建议：`scripts/drill_nats_reload.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

log(){ echo "[$(date -Is)] $*"; }

log "Reload nats-server on ${NATS_HOST}"
ssh "${SSH_USER}@${NATS_HOST}" "sudo nats-server --signal reload" || \
ssh "${SSH_USER}@${NATS_HOST}" "sudo systemctl reload nats" || \
( log "No reload method worked"; exit 1 )

log "Verify TLS endpoint"
echo | openssl s_client -connect "${NATS_HOST}:4222" -servername "${NATS_HOST}" -tls1_2 2>/dev/null | openssl x509 -noout -subject -issuer -dates

log "Done"
```

### 4.4 回滚脚本（模板）

> 文件建议：`scripts/rollback.sh`（原则：只做“恢复到上一个已知良好版本”）

```bash
#!/usr/bin/env bash
set -euo pipefail

log(){ echo "[$(date -Is)] $*"; }

log "Rollback plan"
log "1) 应用侧：把 creds 指回 OLD，并滚动重启"
log "2) 服务侧：恢复上一版 nats-server.conf / TLS / jwt resolver 目录快照"
log "3) 执行 reload 并做权限验证用例"

# 例：服务侧恢复（依赖你们的备份路径）
# ssh "${SSH_USER}@${NATS_HOST}" "sudo cp /etc/nats/backup/nats-server.conf.prev ${CONF_PATH} && sudo nats-server --signal reload"

log "Run post-rollback checks manually:"
log "- OpenCode publish *.dispatch must be denied"
log "- Key business pub/sub OK"
```

---

## 5) 最小化清单（上线前 Gate）

- [ ] NATS client 连接均为 `tls://`，证书链校验通过
- [ ] Operator/Account/User JWT 启用并能在 resolver 更新
- [ ] ACL 最小权限：非必要 subject 全部不可达
- [ ] ✅ **OpenCode publish `*.dispatch` 被显式 deny**（实测用例通过）
- [ ] 轮换 runbook 可执行（至少在预发完成一次演练）
- [ ] 切流/回滚脚本已落库，演练日志归档

---

## 6) 回滚方案（兵部口径）

- 轮换类回滚：保留旧 creds/JWT/TLS 至少 24h，出现异常可立刻切回旧版本并 reload。
- ACL 回滚：保留上一版用户 JWT/Account 配置快照；resolver 目录支持版本化（如按时间戳打包）。
- 变更控制：所有变更必须带“验证用例执行记录”（至少包含 OpenCode deny 校验）。
