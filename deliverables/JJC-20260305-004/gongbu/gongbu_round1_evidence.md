# JJC-20260305-004 · 工部首轮采证（唤醒失败/模型超时）

采证时间：2026-03-06 07:30~07:32 (GMT+8)
采证人：工部（gongbu）

## 1) 网关/agent 唤醒超时样本日志

### 命令
```bash
grep -nEi 'gateway timeout|falling back to embedded|lane wait exceeded|FailoverError|timed out|timeout after' /tmp/openclaw/openclaw.log | tail -n 120
```

### 输出片段（关键）
```text
... lane task error: lane=main durationMs=120120 error="FailoverError: LLM request timed out."
... lane task error: lane=session:agent:shangshu:main durationMs=120127 error="FailoverError: LLM request timed out."
... Gateway agent failed; falling back to embedded: Error: gateway timeout after 150000ms
... Gateway agent failed; falling back to embedded: Error: gateway timeout after 330000ms
... lane wait exceeded: lane=session:agent:shangshu:main waitedMs=552704 queueAhead=2
... All models failed ... session file locked (timeout 10000ms) ... .jsonl.lock
```

### 观察
- 同时存在三类超时：
  1. **模型请求超时**（120s）
  2. **gateway 通道超时**（150s / 330s）
  3. **lane 排队等待超时**（waitedMs 可达 5~10 分钟）
- 并出现 **session file lock timeout (10000ms)**，疑似并发/锁争用放大超时链路。

---

## 2) 网络连通性采证

### 命令
```bash
ss -ltnp | grep 18789
curl -sS -m 5 -I http://127.0.0.1:18789/ | sed -n '1,8p'
curl -sS -m 8 -o /dev/null -w 'code=%{http_code} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' https://api.openai.com/v1/models
curl -sS -m 8 -o /dev/null -w 'code=%{http_code} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' https://api.sgroup.qq.com/gateway
```

### 输出片段
```text
LISTEN ... 127.0.0.1:18789 ... users:("openclaw-gatewa",pid=2006,...)
HTTP/1.1 200 OK
openai: code=401 ... total=0.963766
qq gateway: code=401 ... total=0.185672
```

### 观察
- 网关本地监听正常（loopback 18789）。
- 到 OpenAI/QQ API 的 TCP+TLS 建连均可达（401 属鉴权响应，不是网络不可达）。
- 初判：**不是纯网络断连问题**，更偏向应用层排队/锁争用/调用时延链路。

---

## 3) 资源占用采证（CPU/Mem）

### 命令
```bash
uptime
free -h
vmstat 1 3
ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | grep -E 'openclaw|node .*entry.js gateway|ocbridge|python3' | head -n 20
```

### 输出片段
```text
load average: 0.42, 0.26, 0.20
内存 total 7.7Gi, used 6.1Gi, free 128Mi, swap used 2.8Gi/3.8Gi
openclaw 73.4% CPU, openclaw-agent 60.2%, 58.8% ...
openclaw-gateway 1.6% CPU, 6.2% MEM
```

### 观察
- CPU 存在多进程高占用尖峰（多个 openclaw/openclaw-agent）。
- 内存空闲低、swap 使用高（2.8Gi），可能造成抖动与响应时延上升。

---

## 4) 20分钟节拍现状（首轮）

基于日志样本可见：
- `07:13~07:31` 区间内持续出现 gateway fallback / lane wait / timeout 错误。
- cron lane 存在固定节拍报错（例如 taizi cron 的 FailoverError HTTP 404），对主 lane 也有挤占风险。

---

## 5) 首轮结论（Round1）
1. **唤醒失败并非单点网络故障**：本地网关与外网 API 建连均可达。  
2. **核心可疑链路**：lane 排队等待 + session lock 争用 + 高负载/高swap，导致请求在 120s/150s/330s 阈值触发超时。  
3. **建议 Round2 方向**：
   - 限流并发 session / 排查同 session 重入；
   - 清理僵持 lock（谨慎）；
   - 对 cron 重任务降频或错峰；
   - 采集更细粒度指标（每分钟 lane queue depth、lock wait、provider latency）。

---

## 证据附件
- `deliverables/JJC-20260305-004/_timeout_samples.txt`
- `deliverables/JJC-20260305-004/_net_sample.txt`
- `deliverables/JJC-20260305-004/_resource_sample.txt`

