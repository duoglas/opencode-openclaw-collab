# JJC-20260304-002 ACL 矩阵（Subject级）

> 原则：默认拒绝（deny by default），按最小权限放行。

## 1. 角色定义
- `openclaw-dispatcher`：OpenClaw 调度发布主体
- `openclaw-worker`：OpenClaw 执行节点
- `opencode-producer`：OpenCode 事件生产者
- `bridge-service`：桥接服务
- `sre-ops`：运维控制面
- `audit-reader`：审计只读主体

## 2. Subject 权限矩阵

| Subject | openclaw-dispatcher | openclaw-worker | opencode-producer | bridge-service | sre-ops | audit-reader |
|---|---|---|---|---|---|---|
| `openclaw.dispatch.v1` | pub ✅ / sub ❌ | pub ❌ / sub ✅ | pub ❌ / sub ❌ | pub ❌ / sub ✅ | pub ❌ / sub ❌ | pub ❌ / sub ❌ |
| `openclaw.result.v1` | pub ❌ / sub ✅ | pub ✅ / sub ❌ | pub ❌ / sub ❌ | pub ✅ / sub ✅ | pub ❌ / sub ✅ | pub ❌ / sub ✅ |
| `opencode.event.v1.*` | pub ❌ / sub ✅ | pub ❌ / sub ❌ | pub ✅ / sub ❌ | pub ✅ / sub ✅ | pub ❌ / sub ❌ | pub ❌ / sub ❌ |
| `bridge.control.v1.*` | pub ❌ / sub ❌ | pub ❌ / sub ❌ | pub ❌ / sub ❌ | pub ✅ / sub ✅ | pub ✅ / sub ✅ | pub ❌ / sub ❌ |
| `bridge.dlq.dispatch.v1` | pub ❌ / sub ✅ | pub ❌ / sub ❌ | pub ❌ / sub ❌ | pub ✅ / sub ✅ | pub ❌ / sub ✅ | pub ❌ / sub ✅ |
| `audit.dispatch.v1` | pub ✅ / sub ❌ | pub ✅ / sub ❌ | pub ❌ / sub ❌ | pub ✅ / sub ✅ | pub ❌ / sub ✅ | pub ❌ / sub ✅ |

## 3. 强制规则（关键）
1. **OpenCode 禁止 publish `*.dispatch`**（显式 deny，优先级高于 allow）。
2. `bridge.control.v1.*` 仅 `bridge-service` 与 `sre-ops` 可访问。
3. 所有主体必须绑定 `nkey + jwt`，并在 JWT claim 中限制 subject 前缀。
4. 跨环境（dev/stage/prod）账号隔离，不可复用凭据。

## 4. 审计与告警联动
- ACL 拒绝事件写入 `audit.dispatch.v1`。
- 越权尝试触发安全告警（分钟级聚合）。
- 连续越权超过阈值（例如 5 次/5 分钟）自动封禁 token。
