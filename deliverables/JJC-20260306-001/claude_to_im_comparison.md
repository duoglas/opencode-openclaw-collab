# JJC-20260306-001 对标 Claude-to-IM-skill 改进清单

## 对标对象
- repo: https://github.com/op7418/Claude-to-IM-skill

## 目标
把 ocbridge + OpenCode 插件从“工程链路打通”升级为“产品化可运维工具”：setup/doctor/logs/reconfigure + 更好的事件流与错误可观测性。

## Claude-to-IM-skill 值得学习的点
1. 完整运维面: setup/start/stop/status/logs/doctor/reconfigure
2. 配置向导逐项采集并校验 token, 最终确认再写入
3. 明确的持久化目录结构: config.env/data/logs/runtime
4. 安全: chmod 600, 日志脱敏
5. 故障诊断优先: doctor 脚本覆盖 Node 版本, config, token 校验, PID, 最近错误
6. 权限交互: 内联 Allow/Deny 按钮 (工具调用门控)

## 我们当前差距
- 缺 setup/doctor/logs/reconfigure 命令闭环
- 缺固定日志落盘与轮转
- 缺错误状态/outbox 投递状态查询
- 事件流仅 long-poll, TUI 体验不够实时
- 参数校验/错误提示不够产品化

## 计划拆分(2天内完成)
### PR1 (P0): daemon 日志落盘 + /doctor + /logs
- daemon: 统一写入 ~/.local/share/ocbridge/logs/ocbridge.log 并轮转
- api: GET /doctor 返回 nats/db/订阅/版本/最近错误
- api: GET /logs?tail=N 返回最近 N 行
- plugin: /oc-doctor, /oc-logs N

### PR2 (P0): /oc-setup + /oc-reconfigure + 配置校验
- plugin: 生成 ~/.config/ocbridge/env 骨架, secrets 脱敏展示
- plugin: 输出当前关键配置摘要(不泄露 secrets)
- daemon: /status 返回更多配置摘要字段

### PR3 (P1): events follow 或 SSE + UX 确认
- plugin: /oc-follow 或 /oc-events --follow
- daemon: /events SSE 或增强 long-poll
- plugin: /oc-run 可选确认/干跑预览

### PR4 (P2): 文档与安全
- 文档补齐上述命令与排障
- 说明 secrets 脱敏策略

## 验收标准
- 任何新用户 10 分钟内完成: setup -> status ok -> pending -> claim -> run -> reply
- 遇到 NATS 断开/DB 锁冲突时: doctor/logs 可直观定位
- 多 TUI: session_id 可见, claim 排他可解释
