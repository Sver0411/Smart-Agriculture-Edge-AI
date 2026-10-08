# Smart Agriculture Edge AI v0.3.1

[English](README.md) | [简体中文](README.zh-CN.md)

`research` 分支已加入网关注册与新鲜度补强、有界 LoRa 协议及 B1 E220 UART 适配、默认关闭的 Deep Sleep 快照路径。可复现软件结果与仍待实测的硬件项目见 [集成报告](docs/research/PHASE1_2_TO_PHASE3_INTEGRATION_REPORT.md)。

**Reliability Hardening & Protocol Correctness**

完整的分布式智慧农业软件系统：可信感知、自适应采样、可切换的边缘决策、安全控制、网关接管、离线历史回放和可执行故障实验。所有七个角色可以在单台电脑上运行，运行时仅依赖 Python 标准库。

## Project North Star — Do Not Drift

**这是长期设计约束；以后 README 重构不得删除或弱化本章节。**

项目的目标不是“把所有农业传感器数据实时发送到服务器”。真正目标是：

> 在电池供电、弱网甚至完全没有互联网连接的农业环境中，让各节点在本地完成感知、判断和控制，只在信息值得通信成本时才传输，并在网络恢复后再与云端同步。

```text
Sense locally
    ↓
Evaluate locally
    ↓
Transmit only when necessary
    ↓
Decide locally
    ↓
Act locally
    ↓
Sync when connectivity allows
    ↓
Learn from accumulated field data

Cloud unavailable ≠ Farm unavailable
```

Cloud Server 是 Enhancement Layer，绝不能成为现场实时控制闭环的必要组成部分。A 在本地作判断，C 安全执行；Cloud 用于历史、同步、策略增强和未来离线训练。

## 两个独立农业 Zone 与 Gateway ownership

Zone 1 固定为 **B1 ↔ C1**，Zone 2 固定为 **B2 ↔ C2**。每个 Zone 都有完整的 Sensor B、Gateway A、Controller C。A1/A2 互发 heartbeat；有网络时才与 Cloud 同步。下面的完整架构图是两个区域的正常部署关系，不是“基础 ABC 加第二套可选 ABC”。

| 状态 | Zone 1 | Zone 2 |
|---|---|---|
| 正常 | B1 → A1 → C1 | B2 → A2 → C2 |
| A1 故障 | B1 → A2 → C1 | B2 → A2 → C2 |
| A2 故障 | B1 → A1 → C1 | B2 → A1 → C2 |

迁移的是 **Gateway ownership**，永远不是 **Zone membership**。`CONTROLLER_OF_SENSOR` 的 B1→C1 / B2→C2 是固定基础。接管沿用 OwnershipManager、heartbeat timeout、generation/epoch、注册与过期命令拒绝；恢复的旧 Gateway 进入 STANDBY。没有自动 failback。

```text
                                      ┌─────────────────────────────┐
                                      │        Cloud Server         │
                                      │                             │
                                      │  • Sensor History           │
                                      │  • Node / Gateway Status    │
                                      │  • Control History          │
                                      │  • Alerts                   │
                                      │  • Policy Management        │
                                      │  • Deduplication            │
                                      │  • SQLite Persistence       │
                                      └──────────────┬──────────────┘
                                                     │
                                   telemetry / policy / replay
                                                     │
                        ┌────────────────────────────┴────────────────────────────┐
                        │                                                         │
                        ▼                                                         ▼
              ┌──────────────────────┐                                 ┌──────────────────────┐
              │      Gateway A1      │◄──── Heartbeat / Ownership ────►│      Gateway A2      │
              │                      │      Generation / Failover    │                      │
              │  • Node Registry     │                                 │  • Node Registry     │
              │  • Sensor Quality    │                                 │  • Sensor Quality    │
              │    Gate              │                                 │    Gate              │
              │  • Edge AI /         │                                 │  • Edge AI /         │
              │    DecisionEngine    │                                 │    DecisionEngine    │
              │  • ACK / Retry       │                                 │  • ACK / Retry       │
              │  • Dedup / Sequence  │                                 │  • Dedup / Sequence  │
              │  • Offline Queue     │                                 │  • Offline Queue     │
              │  • Local Autonomy    │                                 │  • Local Autonomy    │
              │  • Failover Control  │                                 │  • Failover Control  │
              └─────────┬────────────┘                                 └─────────┬────────────┘
                        │                                                         │
              ┌─────────┴──────────┐                                    ┌─────────┴──────────┐
              │                    │                                    │                    │
              ▼                    ▼                                    ▼                    ▼
     ┌─────────────────┐  ┌─────────────────┐                  ┌─────────────────┐  ┌─────────────────┐
     │    Sensor B1    │  │  Controller C1  │                  │    Sensor B2    │  │  Controller C2  │
     │                 │  │                 │                  │                 │  │                 │
     │ Physical / Sim  │  │ Command RX      │                  │ Physical / Sim  │  │ Command RX      │
     │ Sensors         │  │      ↓          │                  │ Sensors         │  │      ↓          │
     │      ↓          │  │ Receipt ACK     │                  │      ↓          │  │ Receipt ACK     │
     │ SensorTrust     │  │      ↓          │                  │ SensorTrust     │  │      ↓          │
     │      ↓          │  │ Safety Guard    │                  │      ↓          │  │ Safety Guard    │
     │ Health / Fault  │  │      ↓          │                  │ Health / Fault  │  │      ↓          │
     │      ↓          │  │ Owner / Epoch   │                  │      ↓          │  │ Owner / Epoch   │
     │ AdaptiveSense   │  │ TTL / Cooldown  │                  │ AdaptiveSense   │  │ TTL / Cooldown  │
     │      ↓          │  │ Idempotency     │                  │      ↓          │  │ Idempotency     │
     │ Sampling /      │  │      ↓          │                  │ Sampling /      │  │      ↓          │
     │ Upload Policy   │  │ Actuator        │                  │ Upload Policy   │  │ Actuator        │
     │      ↓          │  │ Execution       │                  │      ↓          │  │ Execution       │
     │ SENSOR_DATA /   │  │      ↓          │                  │ SENSOR_DATA /   │  │      ↓          │
     │ ALERT           │  │ CONTROL_RESULT  │                  │ ALERT           │  │ CONTROL_RESULT  │
     └────────┬────────┘  └────────▲────────┘                  └────────┬────────┘  └────────▲────────┘
              │                    │                                    │                    │
              └─────── Zone 1 ────┘                                    └─────── Zone 2 ────┘
```

A1/A2 是边缘网关，B1/B2 是传感器节点，C1/C2 是同一区域的控制节点。B 与 C 并列；B1 的数据始终控制 C1，故障接管后也保持这个区域关系。Server、Controller 和网关可靠性机制均保留在本仓库。

## 数据与控制链路

```text
SensorSource → SensorTrust → AdaptiveSense → SENSOR_DATA / ALERT
                                               ↓
Gateway: quality gate → DecisionEngine → CONTROL_COMMAND
                                               ↓
Controller: ACK → SafetyGuard → simulated execution → CONTROL_RESULT
                                               ↓
Gateway: live upload / SQLite OfflineQueue → Server: atomic dedup + history
```

- **SensorTrust**：每个通道独立维护 RANGE、STUCK、SPIKE、DRIFT、MISSING 状态，输出 health_score、fault_flags 和 HEALTHY/DEGRADED/FAULT。DRIFT 使用每秒变化率。有效性与检测分数分开，MISSING 确认前的无效读数同样禁止控制。
- **数据可信边界**：Rule 灌溉依赖可信 soil_moisture，通风依赖可信 temperature；不相关通道故障不再封锁独立动作。Logistic/Tree/MLP 要求四通道全部有效且 HEALTHY。全局 health 与故障历史保留；ALERT 按状态/故障签名变化发送，并每 300 秒提醒、恢复时通知。
- **AdaptiveSense**：复用归一化 EMA/STD/ROC 评分和 STABLE/ACTIVE/ALERT 状态机，立即升级、逐级降级、滞回和分级周期；首次有效采样、状态/周期变化、事件开始/恢复、有效数据变化、低频上传心跳可触发上传。异常读数不进入变化评分，恢复后重建基线。
- **采样与保活**：Python SensorNode 是 Host Simulation Profile，socket RX、秒级 NODE_STATUS 与采样独立，用于协议、CI、接管和故障注入。真实电池 B 不持续联网，也不发送每几秒的在线心跳。**Simulation timing ≠ Deployment timing**。
- **DecisionEngine**：Rule、Logistic、Tree、MLP 共用 `predict(sample, policy)`。Rule 为默认；其他模型是固定 seed 的合成策略模仿参考，供训练/导出/切换验证，尚不是经过真实农业数据验证的控制模型。特征顺序与版本在 `ai/features.py` 固定。

## 可靠性与安全

- B/C 注册后取得 owner/generation；SensorNode 和 Controller 都接收网关 NODE_STATUS 更新，并拒绝不一致来源和过期 generation。
- 心跳、ACK/结果超时、节点在线超时与 cooldown 使用 monotonic 时间；last_seen/协议/数据库保留墙上时钟，客户端时间戳不决定 liveness。
- CONTROL_COMMAND 使用稳定 message_id/command_id、有限 ACK 重试和幂等控制器。重试 attempt 递增，逻辑消息身份保持不变。
- ACK 只确认收到；CONTROL_RESULT 表示执行结果。ACK 后结果超时记为 UNKNOWN，产生告警；迟到结果可补全状态，不通过再次执行修复丢失结果。
- Controller 串行处理命令，SafetyGuard 检查类型、command_id、TTL、generation、owner、重复、duration 上限和 cooldown；并发重复命令只执行一次。
- 网关心跳超时触发 takeover 和 generation 增长；恢复的旧网关进入 STANDBY，无自动切回。
- SENSOR_DATA/CONTROL_COMMAND/CONTROL_RESULT/ALERT 先写 SQLite outbox，保留 ID 按 FIFO 回放；仅收到独立的 `PERSISTED_ACK` 才删除。ACK 丢失时保留副本，重连后 Server 去重并重新确认。
- Controller 不在线、失去 ownership 或命令已过期时，未发送的命令记录 `NOT_DISPATCHED` 与原因；已经可能发送的重试无法继续时记录 `UNKNOWN`。控制命令不会排队等日后执行。
- Server 逐消息验证业务语义，再将去重与业务历史写入同一 SQLite 事务，commit 后返回持久化确认；无效上传不消耗 ID。
- `SERVER_POLICY` 使用版本校验和原子参数验证，先本地持久化再激活；Cloud 离线重启也可加载 last-known-good。checkpoint 包含 policy_version、payload、SHA-256、updated_at；策略损坏回退上一有效版本或编译默认值。ACK 是 receipt acknowledgement，Server 不提供基于 ACK 的策略重试保证。

### 协议兼容

TCP 上使用逐行 JSON，原有六字段 envelope 保持兼容：

```json
{"type":"SENSOR_DATA","source":"B1","target":"A1","timestamp":1234567890.0,"message_id":"sample-001","payload":{}}
```

可选字段为 `protocol_version:1`、`sequence`、`attempt`、`generation`；未携带时按旧协议处理。新模拟传感器使用 boot_id + sequence 区分逻辑采样；重排/重复旧数据可保留用于审计，但不再驱动新控制。解析拒绝非有限/溢出数字、错误字段类型、不支持的版本和超长帧。Gateway 与 Server 需配套升级：旧 Server 无持久化确认时，新网关保留 outbox 副本。协议不包含身份认证。

## 运行

Python 3.10+（CI 验证 3.10 / 3.12）：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python demo.py --duration 30
.venv/bin/python -m pytest tests/ -q
```

独立节点 CLI：

```bash
python -m server.server --port 9100 --db server.db
python -m gateway.gateway --id A1 --engine rule
python -m gateway.gateway --id A2 --engine rule
python -m sensor_node.sensor_node --id B1
python -m sensor_node.sensor_node --id B2
python -m controller_node.controller_node --id C1
python -m controller_node.controller_node --id C2
```

demo 保留 normal、failover、server-offline 场景及旧命令/重复命令注入选项。正式实验有独立配置、端口和数据库。

## 配置

`config/software.json` 保留软件基线和完整拓扑；`common/settings.py` 验证，`common/config.py` 保留兼容常量。`SMART_AGRICULTURE_CONFIG=/path/config.json` 可为独立进程指定基线配置，构造器覆盖和实验 runtime_overrides 写入实验配置。

`config/profiles/` 将 sampling/upload 与 Cloud reconnect 分成独立 profile：

| Profile | STABLE | ACTIVE | ALERT | 稳定上传 heartbeat |
|---|---|---|---|---|
| simulation | 20→40→60 s | 15→10→5 s | 5 s | 60 s |
| lab | 2→4→5 s | 2→1 s | 1 s | 300 s |
| deployment | 20→40 min | 10→5 min | 5→2→1 min | 6 h |

部署数值只是**工程默认值**，需要依据作物特性、传感器噪声、环境动态、电池测试与农田实验校准。阈值、EMA 窗口、事件持续时间和故障提醒同样配置化；不是只改变一个 sleep 常量。

`config/physical_b1.json` 显式保存历史温湿度 SensorTrust 配置。`python scripts/generate_b1_profiles.py` 生成 B1 的 C 参数，`--check` 检查配置是否过期。Python/C Upload Decision Parity 用相同输入逐条比较 state、next interval、detected_event、upload_requested，覆盖稳定、缓慢变化、突变、事件开始/恢复、传感器故障、周期上传和大 delta。共享 trace 验证不等于对所有浮点边界的数学证明。

## 实验与实际验证

```bash
python -m experiments.runner --all --output results/software-v0.3.1/my-run
python -m experiments.runner --scenario ack-loss --output results/software-v0.3.1/ack-loss-run

git clone https://github.com/Sver0411/EdgeFaultLab ../EdgeFaultLab
python -m experiments.edgefaultlab --edgefaultlab-root ../EdgeFaultLab --output results/software-v0.3.1/efl-run
```

正式复现请将 EdgeFaultLab 检出为 `docs/integration_sources.json` 中的审查版本。它保持独立，主项目只提供配置/CLI/端口适配器。运行失败返回非零退出码。

每个内部实验保存 `config.json`、`manifest.json`、`truth/injection_plan.json`、`raw/events.jsonl`、`results/metrics.json`、`results/summary.json` 和报告。输出目录拒绝覆盖。指标中的 `null / not measured` 与 `0 / observed` 分开；TCP 读取、ACK、执行和持久化也分开记账。

历史 v0.3 / v0.3.1 实际运行结果（本轮结果另见[部署语义报告](docs/DEPLOYMENT_REALIGNMENT_REPORT.md)）：

- v0.3 基线 155 个测试保留；v0.3.1 共 **231 个测试通过**，Python 3.10/3.12 [CI 通过](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37177748586)。实际命令和证据见[可靠性报告](docs/V0_3_1_RELIABILITY_REPORT.md)。
- **20/20 内部场景通过**：原 17 个场景及 registration-race、persisted-ack-loss、controller-unavailable。
- 独立 EdgeFaultLab 5/5 通过，已移除适配器 startup delay。v0.3 的首次失败记录与本轮回归过程保留。
- SensorTrust Python/C 共享轨迹继续在主机端测试；本轮没有硬件操作。
- 三个 FP32 导出在 240 条留出样本上与训练器预测一致；相同 seed 的四个训练/导出文件逐字节复现。
- INT8 权重存储参考：Logistic 有 2/240 条预测与 FP32 不一致，MLP 为 0/240。激活与 bias 保持浮点、推理先反量化，尚无整数内核或设备结果。

新软件能力的验证等级为 **host-tested / software experimentally evaluated**。历史 B1 固件和实验记录保留在 [firmware/b1](firmware/b1/README.md) 与 [results/v0.3](results/v0.3/README.md)，其验证范围独立于本轮。

## 模型软件工具

仅离线训练需要额外依赖，运行节点不需要 sklearn/numpy：

```bash
pip install -r requirements-training.txt
python -m ai.train --seed 42 --output ai/artifacts
python -m ai.quantize --output ai/artifacts/int8
python -m ai.benchmark --output model_benchmark.json
```

`ai.train.train(..., rows=feature_label_rows)` 接受外部提供的特征/标签数据，输出标记为 `user-provided-unvalidated`；这是未来数据替换入口。训练/留出划分、数据 hash、seed、特征版本和来源写入模型导出。Logistic 在合成留出集中有 10/240 条策略模仿误差；这是如实保留的负面结果，不是农业效果评估。主机延迟和 JSON 字节数不能当作 MCU 延迟、flash 或能耗。

## B 的 Physical Deployment Profile

> Sense locally and communicate only when information is worth the energy.

```text
Wake → Read Sensors → SensorTrust → AdaptiveSense → Update local state
    → Decide next sampling interval → Decide whether transmission is necessary
        ├── NO  → Sleep
        └── YES → Wake radio → LoRa → A → Radio sleep → Sleep
```

**sampled != transmitted**。B1 的 upload_requested 现在完整传递至 sample、发送队列和 transmission guard；稳定采样不再每次入队。communication events 来自首次有效 sample、重要状态变化、确认事件开始/恢复、大 delta、健康故障变化、低频健康报告及配置认可的 critical condition。故障签名不变时不重复发送每个异常 sample。

**Low-Power Communication**：Control-relevant threshold crossing is an immediate upload trigger. 轻量 ControlRelevanceGate 仅比较可信通道与上次成功发送/入队值，双向识别 soil `< threshold`、temperature `> threshold`；profile margin 可配置进入阈值邻域的额外上报。`upload_reasons` 保存所有触发原因。不可信通道走 sensor fault；不相关通道故障不掩盖可信温度 crossing。最终控制仍由 A 决定。

当前 `firmware/b1` 的 ESP32 Wi-Fi/TCP 是 **Development / Integration Transport**，保留其硬件整合价值。SensorTrust/AdaptiveSense 不知道 socket；`b1_telemetry.c` 构造业务 payload，`b1_transport.h` 提供 sink，`b1_network.c` 是 TCP/Wi-Fi adapter。Python `SensorRuntime` 与 `MockFieldTransport` 在 host 验证 radio wake/send/sleep 路径；Python TCP SensorNode 只接受 simulation/lab，不能把 deployment 的分钟周期配在秒级在线 keepalive 上冒充电池部署。

Phase 1：状态一直留在 RAM，采样后等待下次唤醒；Wi-Fi integration 启用 modem power save，并提供 opt-in IDF automatic light sleep。TCP 保持关联时仍有协议通信成本，E220 的按需唤醒/完整 radio sleep 尚待实现。Phase 2：设计 RTC retained state / NVS checkpoint，再引入 deep sleep。必须保存 SensorTrust history、EMA、time history、hysteresis/ladder、event duration、fault signature、last upload 和 ownership epoch；不能每次休眠后重置算法。详见[部署契约](docs/DEPLOYMENT_SEMANTICS.md)。没有本轮电流、能耗或电池寿命结论。

现场目标是 **ESP32-S3 + E220 LoRa**，用于 B↔A、A↔C；A1↔A2 coordination 也必须独立于 Internet/Cloud/Wi-Fi AP。E220 adapter、分帧、无线注册/ownership 通知和 heartbeat transport 当前是 **planned / host-tested contract**，不是 hardware validated。**Field LoRa Semantics**：B belongs to a Zone, not permanently to a Gateway. Uplink 携带 source_node_id、zone_id、sequence、boot/session id、payload；只有当前 Zone owner 可以驱动固定 C。Gateway 层检测 failover，B 不持续监听两个 A 或发送高频 probe。TCP fallback 是 host integration behavior；最终 LoRa 可以按 Zone 上行，B 不必改自己的 Zone 或先改目的 Gateway。必要的本地策略/epoch 交换在通信窗口完成，最终时序需硬件验证。

## A 的 Edge Autonomy 与弱网同步

本地路径始终是 receive B → validate / Trust Gate → DecisionEngine → CONTROL_COMMAND → C → CONTROL_RESULT。Cloud reconnect 与 outbox replay 使用独立任务；慢回执也不会挡住新历史的本地落盘和 B→A→C。

Cloud connectivity 分为 ONLINE、DEGRADED、OFFLINE；deployment 重连退避为 5/15/30/60/300 s，simulation/lab 各有独立参数。恢复后按配置节流回放，仍由每条 PERSISTED_ACK 删除；显式 CRITICAL event 可触发一次受 cooldown 限制的提前重连。连接状态和 outbox depth/bytes/oldest age/rejections 随 Gateway heartbeat 保存在 Cloud 历史。heartbeat 的 host TCP 实现不能证明现场在 Wi-Fi AP 断开后仍工作。

**Offline Queue**：critical capacity is reserved。默认 10,000 条 / 16 MiB 中，为 HIGH 保留 1,000 条 / 1,677,722 bytes；NORMAL 到保留边界即拒绝，HIGH 可继续进入总容量。CONTROL_RESULT、CRITICAL、命令投递失败、Gateway takeover、严重 sensor fault 使用 HIGH。总容量满时明确拒绝并记录 priority metrics/log/local alert state；不驱逐已入队消息，FIFO、ID、dedup、PERSISTED_ACK 保持。

**Controller Safety**：recent command IDs must survive restart before real actuator deployment。Host RecentCommandStore 保存可配置有界窗口（默认64），先 persist INTENT，再模拟执行，再 persist result；损坏或 intent 写失败默认 DO NOT EXECUTE。未完成 intent 也阻止重启重放，不能当作已成功执行。未来 ESP32 使用 NVS；没有板上验证。

**Time Semantics**：Wall-clock time is not the sole safety basis for offline control TTL。未来 LoRa 组合 owner/epoch、gateway/receiver boot session、command sequence/id、接收端预先发出的 receive window 和 monotonic expiry/retry bounds。Host contract 在无 wall clock 时可验证新鲜命令；现有 TCP timestamp TTL 保持兼容。仅收到旧包后重新启动 TTL 不能证明新鲜。详见[五项补丁与证据](results/final-five-patches/README.md)。

## Cloud 边界与现场数据学习

Cloud 已有 TCP Receiver、SQLite history、原子 dedup / PERSISTED_ACK、policy push。**HTTP API / Web Dashboard 仍然缺失**。下一阶段的只读 API 应展示 Zone status、latest/history curves、Gateway ownership/connectivity、alerts、control history、OfflineQueue/replay，并区分“数据过期”与“低功耗节点预计休眠”。设计契约见[Cloud 边界](docs/CLOUD_BOUNDARIES.md)，本轮不引入 broker、微服务或 Kubernetes。

Logistic / Tree / MLP 继续是 synthetic policy imitation：**NOT validated agricultural intelligence**。未来闭环：

```text
Field Data → Cloud DB → Dataset Builder → Versioned Dataset
    → RTX GPU Offline Training → Candidate Model → Evaluation
    → Model Registry → Approved Deployment
```

采用 batch / scheduled retraining；绝不每收到一个 sample 就重新训练。当前外部 rows 是软件训练入口；现场标签、版本数据集、RTX GPU 训练、评估审批、registry 与自动部署尚未完成。

## 验证等级矩阵

Designed = 契约已定义；Host Tested = 主机测试；Software Experimentally Evaluated = 完整软件故障实验；Firmware Implemented = 固件源码/编译；Hardware Tested = 有真实设备证据；Pending = 后续工作。各等级可同时成立，不能互相替代。

| 能力 | 当前证据等级 | Pending / 边界 |
|---|---|---|
| SensorTrust | Host Tested / Firmware Implemented；历史 HW1 正常读数 | 故障阈值农田校准 |
| AdaptiveSense | Host Tested / Software Experimentally Evaluated / Firmware Implemented | 新语义硬件重验、真实环境事件 |
| B upload policy | Host Tested Python/C 逐 sample + queue/sink / Firmware Implemented | 新固件 radio 上传实测 |
| Physical SHT30 | Hardware Tested，历史 30 次 CRC 正常读取 | 本轮未刷板；温湿度以外通道未测 |
| B low-power runtime | Designed / Host Tested mock / Firmware Implemented opt-in light sleep | radio duty cycle、电流与电池测试 |
| B↔A LoRa | Designed / Host Tested message/sleep contract | E220 adapter / RF |
| A DecisionEngine | Host Tested / Software Experimentally Evaluated | MCU port、真实农业效果 |
| A1/A2 heartbeat | Host Tested / Software Experimentally Evaluated | 本地无线硬件链路 |
| Gateway failover | Host Tested / Software Experimentally Evaluated | 整套硬件展示，无自动 failback |
| A↔C LoRa | Designed | E220 adapter / RF |
| C actuator | Host Tested 安全守卫 / 模拟执行 | relay / pump / fan 真实执行 |
| Cloud offline replay | Host Tested / Software Experimentally Evaluated | 长期存储设备/断电测试 |
| Dashboard | Designed | HTTP API / frontend 未实现 |
| real-data training | Designed；synthetic 工具 Host Tested | 现场数据、标签、GPU、registry |

历史硬件证据范围固定于 [HW1 记录](results/v0.3/README.md)；不能转用于本轮 upload、LoRa、power 或 failover 结论。

## Roadmap — Gateway Failure Hardware Demonstration

这是下一阶段最重要的系统级硬件实验之一：

```text
Normal: B1 → A1 → C1   and   B2 → A2 → C2
Power off A1
    ↓
A2 detects local heartbeat timeout
    ↓
A2 persists a newer epoch and takes ownership of Zone 1
    ↓
B1 → A2 → C1   while   B2 → A2 → C2 continues
Restore A1
    ↓
A1 sees newer generation → remains STANDBY
```

同时关闭 Internet/Cloud，并验证 coordination 不依赖 Wi-Fi AP。记录每条 sample/command 的 Zone、owner/generation、ACK 与执行结果，注入旧 A1 command 验证 C1 拒绝。E220 链路、NVS、B 休眠与 C actuator 完成后再执行；现在是 Pending，没有虚构硬件结果。本轮不接入 Camera、Tiny Vision、YOLO 或图像上传。

## 当前限制

- CLI 使用文件 outbox；构造器默认内存队列仅适合软件测试。持久化确认保护已进入 outbox 的上传；节点上行与入队前的内存任务队列仍没有持久化保证。outbox 按配置限制条数/载荷字节，满时明确拒绝新入队并记指标；已入队且未确认的历史不按 TTL 清除。物理磁盘容量、WAL 与损坏 FIFO 首条仍需运维处理。
- Host Gateway 保存 ownership/generation/peer epoch；恢复时先 STANDBY，再对齐 peer。Controller 保存最高 generation/owner、recent intent/result，并在模拟执行前落盘；重启保守等待完整 cooldown。关键状态损坏不回退旧值，禁止控制。ESP32 NVS 后端尚未实现；recent 窗口之外不提供永久幂等，崩溃时实际执行结果可能 UNKNOWN，不能承诺跨重启 actuator exactly-once。
- 双网关 heartbeat 与 owner/generation 检查不构成共识协议。split-brain 场景验证的是过期 generation 和同 epoch 非 owner 拒绝，不能证明任意网络分区下的独占控制。
- STUCK 无法区分真正恒定环境与冻结传感器；DRIFT 也可能来自真实持续环境变化。依赖通道 DEGRADED 的动作被禁止，阈值仍需农业场景校准。
- telemetry 仍是尽力传输；sequence 防旧数据控制，不提供传感器端持久化/重传。
- 无认证、加密、跨节点时钟同步和部署配置校准。现有 TCP CONTROL_COMMAND 时间戳仍要求 Unix wall clock；未来 field freshness 的 host model 已测，尚未接入无线固件。
- 模型只验证软件流程，INT8 只验证权重存储参考；完整 C 模型推理 parity、真实数据效果、设备资源和能耗未测量。

## 文档与下一阶段

[v0.3.1 可靠性报告](docs/V0_3_1_RELIABILITY_REPORT.md) · [本轮代码审查](docs/V0_3_1_RELIABILITY_REVIEW.md) · [v0.3 整合与复用记录](docs/V0_3_INTEGRATION_REPORT.md)

[分支整合审查与最新软件验证](docs/BRANCH_INTEGRATION_REVIEW.md) 记录开发线合入主线前的 checkpoint、命令窗口和配置修复；历史测试/实验报告保留原范围。

下一阶段优先打通现场 E220 通信、NVS epoch 与真实功耗验证，并进行上述 Gateway Failure Hardware Demonstration。完整拓扑始终保留。

MIT。直接复用的 AdaptiveSense Python 文件保留其 MIT 许可证与来源记录。
