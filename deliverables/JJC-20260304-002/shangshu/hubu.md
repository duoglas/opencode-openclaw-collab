# JJC-20260304-002 指标 / SLO / 成本与容量估算方案（户部）

## 1. 目标与边界

- 适用对象：基于 **NATS 集群 + bridge 服务 + DLQ 存储** 的消息链路。
- 估算目标：在给定业务流量下，明确可观测指标、SLO 口径、容量计算方法与成本拆分维度。
- 统计周期建议：
  - 实时监控：15s~60s scrape interval
  - SLO评估：滚动 1h / 24h / 30d
  - 成本复盘：日 / 周 / 月

---

## 2. SLO 定义与计算口径

### 2.1 成功率 SLO（Availability / Delivery Success）

**SLO 定义（建议）**：
- 月度成功率（30d）≥ **99.9%**（核心主题）
- 次核心主题可设为 99.5%~99.9%

**成功事件定义**：
- 消息被 bridge 接收后，在规定时间窗内被目标订阅者成功处理并 ACK。

**失败事件定义**：
- 处理超时、NACK、重试后仍失败、进入 DLQ。

**计算口径（推荐）**：

```text
成功率 = 成功处理消息数 / (成功处理消息数 + 失败处理消息数)

30d 成功率 = sum_over_30d(success_total)
           / (sum_over_30d(success_total) + sum_over_30d(failure_total))
```

> 注意：
> - 重试消息按“最终结果”计一次，避免重复计数导致口径漂移。
> - 对于超时后晚到 ACK，需定义是否计入成功（建议按“窗口内成功”计入，否则算失败）。

### 2.2 延迟 SLO（Latency）

**SLO 定义（建议）**：
- P95 端到端延迟 ≤ **500ms**
- P99 端到端延迟 ≤ **1500ms**

**端到端延迟定义**：
- `consumer_ack_ts - producer_publish_ts`

**计算口径（推荐）**：

```text
P95/P99 基于 histogram bucket 计算
观测窗口：5m（告警）/1h（运营）/30d（SLO审计）
```

> 注意：
> - 严禁均值替代分位值。
> - 对跨机房时钟偏差需采用单调时钟或链路打点统一校时。

---

## 3. 关键指标列表（含 Prometheus 样例）

以下命名采用通用规范，实际以系统 exporter 指标名为准。

### 3.1 流量与吞吐

- `bridge_messages_in_total`：bridge 入站消息总数（Counter）
- `bridge_messages_out_total`：bridge 出站消息总数（Counter）
- `bridge_bytes_in_total` / `bridge_bytes_out_total`：字节流量（Counter）
- `nats_server_in_msgs` / `nats_server_out_msgs`：NATS消息收发

PromQL 示例：

```promql
# 当前每秒入站消息速率
sum(rate(bridge_messages_in_total[5m]))

# 当前每秒字节流量（MB/s）
sum(rate(bridge_bytes_in_total[5m])) / 1024 / 1024
```

### 3.2 可用性与成功率

- `bridge_delivery_success_total`
- `bridge_delivery_failure_total`
- `bridge_retry_total`
- `bridge_dlq_total`

PromQL 示例：

```promql
# 30天成功率
sum(increase(bridge_delivery_success_total[30d]))
/
(sum(increase(bridge_delivery_success_total[30d]))
 + sum(increase(bridge_delivery_failure_total[30d])))

# 5分钟失败率
sum(rate(bridge_delivery_failure_total[5m]))
/
sum(rate(bridge_messages_in_total[5m]))
```

### 3.3 延迟与积压

- `bridge_e2e_latency_seconds_bucket`（Histogram）
- `bridge_processing_latency_seconds_bucket`
- `bridge_queue_depth`（Gauge）
- `nats_subscription_pending_messages`

PromQL 示例：

```promql
# 5分钟窗口 p95 延迟
histogram_quantile(
  0.95,
  sum(rate(bridge_e2e_latency_seconds_bucket[5m])) by (le)
)

# 5分钟窗口 p99 延迟
histogram_quantile(
  0.99,
  sum(rate(bridge_e2e_latency_seconds_bucket[5m])) by (le)
)

# 订阅积压总量
sum(nats_subscription_pending_messages)
```

### 3.4 资源与稳定性

- `process_cpu_seconds_total`（bridge）
- `process_resident_memory_bytes`（bridge）
- `nats_varz_connections` / `nats_varz_routes` / `nats_varz_slow_consumers`
- `up{job="bridge"}` / `up{job="nats"}`

PromQL 示例：

```promql
# bridge CPU核数占用
sum(rate(process_cpu_seconds_total{job="bridge"}[5m]))

# bridge 内存占用（GiB）
sum(process_resident_memory_bytes{job="bridge"}) / 1024 / 1024 / 1024
```

---

## 4. 容量估算方法（吞吐 / 消息大小 / 订阅数）

## 4.1 输入参数（需业务给定）

- `Qps_in`：入站消息速率（msg/s）
- `Msg_size_avg`：平均消息大小（bytes）
- `Msg_size_p99`：P99 消息大小（bytes）
- `Subs`：平均订阅者数（每条消息扇出数）
- `Ack_ratio`：ACK相关额外开销系数（建议 1.05~1.20）
- `Burst`：峰值系数（建议 2~5）
- `Headroom`：冗余系数（建议 30%~50%）

### 4.2 核心估算公式

1) **逻辑出站吞吐**（考虑订阅扇出）：

```text
Qps_out = Qps_in × Subs
```

2) **字节吞吐（平均）**：

```text
Bytes_per_sec = Qps_out × Msg_size_avg × Ack_ratio
```

3) **峰值字节吞吐（容量规划）**：

```text
Bytes_peak = Bytes_per_sec × Burst × (1 + Headroom)
```

4) **bridge 副本数估算**（单副本能力为 `Cap_replica`）：

```text
Replicas = ceil(Qps_out / Cap_replica × (1 + Headroom))
```

5) **NATS 集群节点估算**（单节点有效吞吐 `Cap_nats_node`）：

```text
Nats_nodes = ceil(Bytes_peak / Cap_nats_node)
```

### 4.3 DLQ 容量估算

假设失败率 `Fail_rate`，保留天数 `Retain_days`：

```text
DLQ_msgs_per_day = Qps_in × 86400 × Fail_rate
DLQ_storage = DLQ_msgs_per_day × Msg_size_avg × Retain_days × Compression_factor
```

其中 `Compression_factor` 可取 0.3~0.8（取决于压缩算法与消息结构）。

### 4.4 建议执行流程

1. 采集 7~14 天真实流量分布（均值/P95/P99）。
2. 按平峰/高峰/大促三档分别估算。
3. 用压测验证单副本与单节点上限，校正 `Cap_replica`、`Cap_nats_node`。
4. 将结果反推 SLO 风险点（高延迟、积压、DLQ激增）。

---

## 5. 成本维度拆分

### 5.1 NATS 集群成本

- 计算资源：节点 CPU / 内存 / 网络带宽
- 高可用成本：奇数节点、跨可用区流量
- JetStream（若启用）存储与复制因子
- 运维成本：监控、备份、升级窗口

成本近似：

```text
Cost_nats ≈ 节点数 × 单节点单价 + 跨AZ流量费 + 存储费（若有）
```

### 5.2 bridge 副本成本

- Pod/VM 规格（vCPU / RAM）
- 副本数（与峰值吞吐、SLO余量相关）
- HPA扩缩容对峰值时段成本影响

成本近似：

```text
Cost_bridge ≈ 副本数 × 单副本单价 × 运行时长
```

### 5.3 DLQ 存储成本

- 存储总量（由失败率、保留周期决定）
- 存储介质分层（热/温/冷）
- 读取与回放操作成本

成本近似：

```text
Cost_dlq ≈ 存储容量 × 单位存储价格 + 读写请求费 + 数据回放流量费
```

---

## 6. 优化建议（降本与稳态并行）

1. **降低无效扇出**：按主题/租户精细化订阅，减少 `Subs`。
2. **消息体瘦身**：字段裁剪 + 压缩，直接降低带宽与存储成本。
3. **桥接层弹性策略**：
   - 以队列深度 + 延迟双指标驱动 HPA，避免纯CPU扩容失真。
4. **重试与DLQ治理**：
   - 指数退避 + 最大重试次数；
   - 对可恢复/不可恢复错误分类，减少无效重试。
5. **SLO分级**：核心链路高保障（99.9+），非核心链路适度降级，避免全链路过度配置。
6. **容量基线滚动更新**：每月基于真实分位流量更新参数，避免长期按一次性峰值超配。

---

## 7. 交付检查清单

- [x] SLO定义与计算口径（成功率 / 延迟）
- [x] 关键指标列表与 Prometheus 样例
- [x] 容量估算方法（吞吐 / 消息大小 / 订阅数）
- [x] 成本维度（NATS 集群 / bridge 副本 / 存储 DLQ）
- [x] 优化建议
