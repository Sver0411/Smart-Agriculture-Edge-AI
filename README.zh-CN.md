<h1 align="center">Smart Agriculture Edge AI</h1>

<p align="center"><strong>A Research Platform for Agricultural IoT and Edge AI</strong></p>

<p align="center">Trustworthy Sensing · Low-Power Communication · Safe Local Control · Reproducible Experiments</p>

---

<p align="center">An independently developed research prototype integrating embedded sensing, edge intelligence, and resilient IoT communication for smart agriculture.</p>

<p align="center">
  <a href="#project-north-star--do-not-drift">Overview</a> ·
  <a href="#两个独立农业-zone-与-gateway-ownership">Architecture</a> ·
  <a href="#验证等级矩阵">Implementation</a> ·
  <a href="https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/main/README.md#related-research-projects">Related Projects</a> ·
  <a href="README.md">English</a>
</p>

---

**research 分支：当前实现与验证**

七角色研究原型，涵盖可信感知、选择性通信、安全本地控制、网关接管和离线同步。所有节点角色可在一台电脑上运行，运行时仅依赖 Python 标准库。Rule 是默认决策引擎，学习模型用于可复现的合成策略参考。

本分支已实现注册与样本新鲜度补强、有界 LoRa 协议和 B1 E220 UART 驱动、实验性 RTC/NVS 休眠恢复、控制结果可靠交付、可跨重启恢复的策略发布，以及显式传感器确认模式。[AR-1](docs/architecture/AR1_SENSOR_PIPELINE.md) 已将纯传感器处理从 Gateway 协调逻辑中提取，保持运行行为。这些研究扩展尚未合入 [main](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/tree/main)。

**最近一次已记录验证**：Python 3.10 和 3.12 各通过 631 项测试；TCP 场景 20/20、主机模拟 LoRa 全拓扑场景 20/20；四种 ESP32-S3 固件配置编译通过。[完整结果](#实验与实际验证)分别说明软件实验、固件编译和实物测量。所有必要链路完成认证前，deployment 入口保持 fail-closed。

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

- B/C 注册和连接路由共同确定节点连接、owner 与 generation；来源不一致或旧 generation 会被拒绝。
- 节点在线判断、重试、冷却和样本年龄使用单调时钟；协议时间戳和历史记录保留墙上时钟。客户端时间戳不决定在线状态。可靠与物理样本的五秒控制新鲜度包含网关内部排队时间，并要求 boot 与注册值一致；持久化准入及 ACK 等待之后、实际决策之前，再次检查年龄。
- 可靠样本在丢失、缓冲和重启后保留原 boot/sequence 身份。Gateway 先将回执和历史提交到文件型 SQLite outbox，再发送 `GATEWAY_OUTBOX` 范围的 PERSISTED_ACK。重复重传可以重新确认，但不产生额外回执或控制决策。旧 boot、过期或年龄未知的可靠样本仅作为历史。
- Host SensorNode 保留 `legacy-write` 兼容模式，并提供可选的 `gateway-durable` 模式。后者将 HIGH 待确认记录写入 checkpoint，NORMAL 仍只保留在 RAM；只有匹配的持久化 ACK 才推进上传基线。旧 boot 历史的确认只清退旧记录，不确认新 boot 基线。
- CONTROL_COMMAND 保持稳定的 `message_id`/`command_id`，ACK 重试有界，控制器按身份幂等处理。命令 ACK 仅确认接收，CONTROL_RESULT 才报告执行。结果缺失时记为 UNKNOWN，迟到结果可以消除不确定性；不能发起新动作来修复结果丢失。
- Controller 串行处理命令。SafetyGuard 检查类型、身份、TTL、owner/generation、重复、执行时长和冷却时间；意图与结果 checkpoint 支持保守恢复。CONTROL_RESULT 使用有界持久化重发窗口，保留原始消息内容，由 `CONTROL_RESULTS` 范围的持久化 ACK 清退。Gateway 提交结果回执、历史和 outcome 后才确认。
- 心跳超时触发接管并提高 generation，恢复的网关保持 STANDBY，不自动切回。故障检测器区分本地监视任务暂停与远端失联；这一机制不是任意分区下的共识协议。
- 云端上传使用有界 SQLite outbox、HIGH 容量保留、稳定身份、FIFO 回放和 Server 事务去重；commit 后才发送 ACK。重连与回放由独立任务处理。无效上传不占用身份，ACK 丢失时保留记录，供去重重传。
- 过期、控制器不可用或失去控制权的未发送命令记为 NOT_DISPATCHED；可能已发送的命令可以保持 UNKNOWN。现场命令不会积压到故障恢复后再执行。
- SERVER_POLICY 先验证内容与版本，再持久化激活。Gateway 恢复最后有效策略；Server 将发布内容和版本一起持久化，避免重启后版本归零。未改变内容或重复广播不生成新版本。策略 ACK 仍只确认接收，不构成保证重试契约。
- A1/A2 的隔离实验可使用 HMAC 会话，但 B↔A、A↔C、云端和实物 RF 链路尚未形成完整认证会话。因此 `profile=deployment` 即使配置了有效 peer key，也会在启动前被拒绝。CRC 只能验证完整性，不能认证身份。

### 协议兼容

TCP 上使用逐行 JSON，原有六字段 envelope 保持兼容：

```json
{"type":"SENSOR_DATA","source":"B1","target":"A1","timestamp":1234567890.0,"message_id":"sample-001","payload":{}}
```

可选字段为 `protocol_version:1`、`sequence`、`attempt`、`generation`；未携带时按旧协议处理。新模拟传感器使用 boot_id + sequence 区分逻辑采样；重排/重复旧数据可保留用于审计，但不再驱动新控制。解析拒绝非有限/溢出数字、错误字段类型、不支持的版本和超长帧。Gateway 与 Server 需配套升级：旧 Server 无持久化确认时，新网关保留 outbox 副本。JSON envelope 和 LoRa CRC 不认证 B/C/云端身份；可选 peer HMAC 仅覆盖 A1/A2 实验，完整认证前禁止 deployment。

## 运行

使用 Python 3.10 或更高版本；CI 验证 3.10 / 3.12。下列主机示例使用 simulation/lab 配置；deployment 时序是工程契约，当前入口会主动拒绝启动。

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

demo 保留 normal、failover、server-offline 场景及旧命令/重复命令注入。正式实验使用独立配置、端口和数据库。验证传感器持久化确认时，为 B 指定 `--delivery-mode gateway-durable`，为 Gateway 指定文件型 `--queue-db`；默认仍为 `legacy-write` 兼容模式。

## 配置

`config/software.json` 保留软件基线和完整拓扑；`common/settings.py` 验证，`common/config.py` 保留兼容常量。`SMART_AGRICULTURE_CONFIG=/path/config.json` 可为独立进程指定基线配置，构造器覆盖和实验 runtime_overrides 写入实验配置。

`config/profiles/` 将 sampling/upload 与 Cloud reconnect 分成独立 profile：

| Profile | STABLE | ACTIVE | ALERT | 稳定上传 heartbeat |
|---|---|---|---|---|
| simulation | 20→40→60 s | 15→10→5 s | 5 s | 60 s |
| lab | 2→4→5 s | 2→1 s | 1 s | 300 s |
| deployment | 20→40 min | 10→5 min | 5→2→1 min | 6 h |

deployment 时序只是**工程默认值**，不代表当前软件允许安全部署；需要依据作物特性、传感器噪声、环境动态、电池测试与农田实验校准。阈值、EMA 窗口、事件持续时间和故障提醒同样配置化；不是只改变一个 sleep 常量。

`config/physical_b1.json` 显式保存历史温湿度 SensorTrust 配置。`python scripts/generate_b1_profiles.py` 生成 B1 的 C 参数，`--check` 检查配置是否过期。Python/C Upload Decision Parity 用相同输入逐条比较 state、next interval、detected_event、upload_requested，覆盖稳定、缓慢变化、突变、事件开始/恢复、传感器故障、周期上传和大 delta。共享 trace 验证不等于对所有浮点边界的数学证明。

## 实验与实际验证

最近一次完整 AR-1 回归验证的功能源码为 `add9d076a04670b63b643fb822cfa84b23e99975`。最终报告版本 `825bb92` 的 [push CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37880089604) 和 [PR CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37880093415) 均完整通过，功能源码和配置 hash 与本地验收一致。[AR-1 记录](docs/architecture/AR1_SENSOR_PIPELINE.md)与[稳定化报告](docs/research/RELIABILITY_STABILIZATION_REPORT.md)说明了验证范围、来源和保留的失败过程。

| 评估 | 已记录结果 | 范围 |
| --- | --- | --- |
| 完整 pytest，Python 3.10 / 3.12 | 每个版本各 631 项通过 | 全部原有 587 项与 AR-1 新增 44 项；不跨解释器累加 |
| 基准与重构行为对照 | 256/256 一致 | 使用真实处理函数比较记录、命令、顺序状态、日志、指标和审计 |
| 原有 TCP 故障场景 | 20/20 PASS | 七角色主机拓扑与模拟执行器 |
| 重复归属与可靠性场景 | 20/20 PASS | 旧 generation ×10、接管 ×3、恢复 ×3，以及其他四种故障 |
| 主机模拟 LoRa 全拓扑 | 20/20 PASS | 真实应用逻辑通过模拟 RF 载体通信 |
| 固定 seed LoRa 比较 | 56/56 安全检查通过 | 43 COMPLETE、13 INCOMPLETE；未确认记录继续保留 |
| 实际 C 休眠恢复参考 | 19/19 PASS，2800 次观察 | 已知 elapsed oracle 与未知时间保守恢复；不是物理 RTC 实测 |
| 跨阶段集成 / 外部 EdgeFaultLab | 10/10 与 5/5 PASS | 生产 C/应用路径与独立故障运行器 |
| GitHub Actions | push 和 PR 均 6/6 job 通过 | 两种 Python、完整实验矩阵和四种固件构建 |
| ESP32-S3 固件 | ESP-IDF v5.4.4 下四种配置编译通过 | lab、light-sleep、lora-prototype、deep-sleep-experimental；编译不等于板上实验 |

每次运行使用新的忽略目录：

```bash
python -m experiments.runner --all --output .research-runs/tcp-NEW
python -m experiments.reliability_stabilization --output .research-runs/repeats-NEW
python -m experiments.runner --all --transport simulated-lora --output .research-runs/lora-NEW
python -m experiments.lora_harness --seed 42 --output .research-runs/radio-NEW
python -m experiments.snapshot_harness --output .research-runs/snapshot-NEW
python -m experiments.phase123_integration --seed 42 --output .research-runs/integration-NEW

git clone https://github.com/Sver0411/EdgeFaultLab ../EdgeFaultLab
git -C ../EdgeFaultLab checkout c7248239f456cc877114ca1e67c5949fb4a7b958
python -m experiments.edgefaultlab --edgefaultlab-root ../EdgeFaultLab --output .research-runs/external-NEW
```

同一机器上的两种 Python 完整测试应串行运行，因为部分 e2e 测试使用固定端口。Host C 测试需要 C11 编译器，适用的 sanitizer 检查包含在 pytest 内。EdgeFaultLab 保持外部维护，固定到审查版本。核心断言失败会返回非零退出码。

实验保留配置、注入计划、原始事件、指标、汇总，以及源码和配置 hash；输出目录拒绝覆盖，CI 也保留失败 Artifact。指标区分 `null / not measured` 与 `0 / observed`，并分别记录接收、ACK、执行结果和持久化。已有科研证据保留，新生成数据写入 `.research-runs/` 或 CI Artifact。

历史 v0.3/v0.3.1 的 155 项、231 项测试 checkpoint 仍保留在[可靠性报告](docs/V0_3_1_RELIABILITY_REPORT.md)。240 条合成留出样本上的 FP32 导出一致性，以及 Logistic INT8 的 2/240 差异、MLP 的 0/240 差异，是软件与模型存储参考，不能证明农业精度或 MCU 能耗。历史实物感知仍限于 [30 次 CRC 有效 SHT30 读取](results/v0.3/README.md)。

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

B1 的实物感知仍是 SHT30 温度与湿度；土壤湿度控制相关性目前只在主机原型验证。

当前 `firmware/b1` 的 ESP32 Wi-Fi/TCP 是 **Development / Integration Transport**，保留其硬件整合价值。SensorTrust/AdaptiveSense 不知道 socket；`b1_telemetry.c` 构造业务 payload，`b1_transport.h` 提供 sink，`b1_network.c` 是 TCP/Wi-Fi adapter。Python `SensorRuntime` 与 `MockFieldTransport` 在 host 验证 radio wake/send/sleep 路径；Python TCP SensorNode 只接受 simulation/lab，不能把 deployment 的分钟周期配在秒级在线 keepalive 上冒充电池部署。

lab/light-sleep 保留 Wi-Fi/TCP 集成。research 的 E220 驱动已实现有界 UART/AUX 通信窗口，以及空队列变为非空或 HIGH 准入时的通知调度与断链退避。UART 写入完成不等于远端收到；只有匹配的网关持久化 ACK 才能清退可靠记录。无线唤醒/休眠、AUX 时序和 RF 行为仍需实测。

Phase 3 已提供默认关闭的 Deep Sleep 任务、RTC 算法快照和 NVS HIGH 恢复，并用实际 C 实现验证 SensorTrust/AdaptiveSense 连续性。默认 elapsed provider 返回 UNKNOWN，固件保守重建时间与上报基线，不把计划休眠时间当作实测值。每次唤醒使用新 boot 身份，旧 HIGH 保留原身份。详见[休眠配置与调试要求](firmware/b1/EXPERIMENTAL_TRANSPORT_SLEEP.md)。板上连续性、电流和电池寿命仍未测量。

现场目标是 **ESP32-S3 + E220 LoRa**，用于 B↔A、A↔C；A1↔A2 coordination 也必须独立于 Internet/Cloud/Wi-Fi AP。有界分帧/重组、角色路由、重试和 B1 UART 驱动已有源码及主机测试或编译证据；Gateway/Controller 实物 E220 端点、完整无线注册、归属通知与心跳集成仍待硬件工作。**Field LoRa Semantics**：B belongs to a Zone, not permanently to a Gateway. Uplink 携带 source_node_id、zone_id、sequence、boot/session id、payload；只有当前 Zone owner 可以驱动固定 C。Gateway 层检测 failover，B 不持续监听两个 A 或发送高频 probe。TCP fallback 是 host integration behavior；最终 LoRa 可以按 Zone 上行，B 不必改自己的 Zone 或先改目的 Gateway。必要的本地策略/epoch 交换在通信窗口完成，最终时序需硬件验证。

## A 的 Edge Autonomy 与弱网同步

本地路径始终是 receive B → validate / Trust Gate → DecisionEngine → CONTROL_COMMAND → C → CONTROL_RESULT。[sensor_pipeline](gateway/sensor_pipeline.py) 用纯函数准备记录、信任、新鲜度和告警；Gateway 保留顺序/boot 状态、SQLite 准入、ACK、实时控制权、generation 和命令派发，原有处理接口保持可用。Cloud reconnect 与 outbox replay 使用独立任务；慢回执也不会挡住新历史的本地落盘和 B→A→C。

Cloud connectivity 分为 ONLINE、DEGRADED、OFFLINE；deployment 重连退避为 5/15/30/60/300 s，simulation/lab 各有独立参数。恢复后按配置节流回放，仍由每条 PERSISTED_ACK 删除；显式 CRITICAL event 可触发一次受 cooldown 限制的提前重连。连接状态和 outbox depth/bytes/oldest age/rejections 随 Gateway heartbeat 保存在 Cloud 历史。heartbeat 的 host TCP 实现不能证明现场在 Wi-Fi AP 断开后仍工作。

**Offline Queue**：critical capacity is reserved。默认 10,000 条 / 16 MiB 中，为 HIGH 保留 1,000 条 / 1,677,722 bytes；NORMAL 到保留边界即拒绝，HIGH 可继续进入总容量。CONTROL_RESULT、CRITICAL、命令投递失败、Gateway takeover、严重 sensor fault 使用 HIGH。总容量满时明确拒绝并记录 priority metrics/log/local alert state；不驱逐已入队消息，FIFO、ID、dedup、PERSISTED_ACK 保持。

**Controller Safety**：recent command IDs must survive restart before real actuator deployment。Host RecentCommandStore 保存可配置有界窗口（默认64），先 persist INTENT，再模拟执行，再 persist result；损坏或 intent 写失败默认 DO NOT EXECUTE。未完成 intent 也阻止重启重放，不能当作已成功执行。未来 ESP32 使用 NVS；没有板上验证。

**Time Semantics**：Wall-clock time is not the sole safety basis for offline control TTL。Host LoRa 新鲜度契约组合 owner/epoch、gateway/receiver boot session、command sequence/id、接收端预先发出的 receive window 和 monotonic expiry/retry bounds；实物 A/C 端点集成仍待完成。Host contract 在无 wall clock 时可验证新鲜命令；现有 TCP timestamp TTL 保持兼容。仅收到旧包后重新启动 TTL 不能证明新鲜。详见[五项补丁与证据](results/final-five-patches/README.md)。

## Cloud 边界与现场数据学习

Cloud 已有 TCP 接收、SQLite 历史、原子去重/PERSISTED_ACK 和可跨重启恢复的策略发布；策略内容与版本一起持久化，未改变内容及重复广播不提高版本。**HTTP API / Web Dashboard 仍然缺失**。下一阶段的只读 API 应展示 Zone status、latest/history curves、Gateway ownership/connectivity、alerts、control history、OfflineQueue/replay，并区分“数据过期”与“低功耗节点预计休眠”。设计契约见[Cloud 边界](docs/CLOUD_BOUNDARIES.md)，本轮不引入 broker、微服务或 Kubernetes。

Logistic / Tree / MLP 继续是 synthetic policy imitation：**NOT validated agricultural intelligence**。未来闭环：

```text
Field Data → Cloud DB → Dataset Builder → Versioned Dataset
    → RTX GPU Offline Training → Candidate Model → Evaluation
    → Model Registry → Approved Deployment
```

采用 batch / scheduled retraining；绝不每收到一个 sample 就重新训练。当前外部 rows 是软件训练入口；现场标签、版本数据集、RTX GPU 训练、评估审批、registry 与自动部署尚未完成。

## 验证等级矩阵

Designed = 契约已定义；Host Tested = 主机测试；Software Experimentally Evaluated = 完整软件故障实验；Firmware Implemented = 固件源码/编译；Hardware Tested = 有真实设备证据；Pending = 后续工作。各等级可同时成立，不能互相替代；固件源码与编译状态明确区分，均不代表板上运行。

| 能力 | 当前证据等级 | Pending / 边界 |
|---|---|---|
| SensorTrust | Host Tested / Firmware Implemented；历史 HW1 正常读数 | 故障阈值农田校准 |
| AdaptiveSense | Host Tested / Software Experimentally Evaluated / Firmware Implemented | 新语义硬件重验、真实环境事件 |
| B upload policy | Host Tested Python/C 逐 sample + queue/sink / Firmware Implemented | 新固件 radio 上传实测 |
| Physical SHT30 | Hardware Tested，历史 30 次 CRC 正常读取 | 本轮未刷板；温湿度以外通道未测 |
| B low-power runtime | Host/C 快照测试；包括实验 Deep Sleep 的四种配置编译通过 | 校准 RTC elapsed、GPIO/无线休眠、NVS 断电、电流与电池测量 |
| B↔A LoRa | 有界 Host 协议测试；B1 E220 UART 源码编译通过 | 实物 Gateway 端点、RF 调试与端到端测量 |
| A DecisionEngine | Host Tested / Software Experimentally Evaluated | MCU port、真实农业效果 |
| A1/A2 heartbeat | Host Tested / Software Experimentally Evaluated | 本地无线硬件链路 |
| Gateway failover | Host Tested / Software Experimentally Evaluated | 整套硬件展示，无自动 failback |
| A↔C LoRa | 主机拓扑、路由及控制 fencing 测试 | 实物 A/C E220 端点与 RF 测量 |
| C actuator | Host Tested 安全守卫 / 模拟执行 | relay / pump / fan 真实执行 |
| Cloud offline replay | 样本/结果持久化回执、FIFO 回放、策略版本恢复的 Host 测试 | 长期容量与断电评估 |
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

同时关闭 Internet/Cloud，并验证 coordination 不依赖 Wi-Fi AP。记录每条 sample/command 的 Zone、owner/generation、ACK 与执行结果，注入旧 A1 command 验证 C1 拒绝。完成 A/B/C 实物 RF 调试、Gateway/Controller 板上恢复状态、B 休眠计时校准和真实执行器集成后再执行；当前硬件展示仍是 Pending。本轮不接入 Camera、Tiny Vision、YOLO 或图像上传。

## 当前限制

- 回执账本、HIGH 缓冲、结果重发窗口和近期命令保护都有容量边界。容量压力会明确拒绝准入，不能静默删除身份；物理磁盘/WAL 增长、Flash 磨损、长期离线和可证明的回执清退仍需运维评估。
- Host ownership/generation 和命令意图/结果 checkpoint 支持 fail-closed 重启恢复；ESP32 控制器及网关实物 RF 端点尚未实现。不可观察的崩溃窗口和有界去重历史，使系统不能无条件承诺执行器 exactly-once。
- 双网关心跳故障检测不是分布式共识。split-brain、单向丢失、恢复和旧 generation 实验验证明确的故障计划，不能证明任意分区下的独占控制。
- legacy-write 遥测仍为尽力传输。非 physical 的 legacy 实验输入使用接收年龄和按 boot 的顺序检查，没有可靠/物理路径的注册 boot 门槛。可靠 HIGH 历史可通过 checkpoint/重试保留，Host NORMAL 待确认数据仍只在 RAM。提交后 ACK 发送失败，不会在重传时重新执行被中断的控制决策。[AR-1 边界](docs/architecture/AR1_SENSOR_PIPELINE.md#remaining-architecture-debt)记录了这些保持不变的行为。
- 可选 HMAC 仅保护 peer 实验。B/C/云端/RF 会话认证、加密、跨节点时钟调试和现场校准尚未完成，因此 deployment 模式仍被拒绝。
- E220 RF 可靠性、A/C 集成、GPIO/AUX/复位行为、校准的 RTC elapsed、NVS 断电、真实执行器、电流和电池寿命仍待硬件验证。实验源码与四种固件编译通过不能替代这些测量。
- STUCK、DRIFT 是启发式指标，也可能对应真实环境行为。学习模型仍为合成策略参考，完整 C 推理一致性、农业效果、MCU 资源和能耗尚未验证。

## 文档与下一阶段

[v0.3.1 可靠性报告](docs/V0_3_1_RELIABILITY_REPORT.md) · [本轮代码审查](docs/V0_3_1_RELIABILITY_REVIEW.md) · [v0.3 整合与复用记录](docs/V0_3_INTEGRATION_REPORT.md)

research 最新记录：[Phase 1.2](docs/research/PHASE1_2_DEVELOPMENT_REPORT.md)、[LoRa 协议/UART](docs/research/PHASE2_LORA_DEVELOPMENT_REPORT.md)、[实验休眠](docs/research/PHASE3_DEEPSLEEP_DEVELOPMENT_REPORT.md)、[跨阶段集成](docs/research/PHASE1_2_TO_PHASE3_INTEGRATION_REPORT.md)、[可靠性稳定化](docs/research/RELIABILITY_STABILIZATION_REPORT.md)、[AR-1 架构](docs/architecture/AR1_SENSOR_PIPELINE.md)。更早的整合报告保持历史范围；AR-1 不包含 AR-2/AR-3/AR-4。

后续优先完成实物 A/C E220 端点、现场/云端认证会话、RTC/NVS 校准、真实执行器，以及无线/休眠能耗测量，再进行硬件接管展示。完整拓扑始终保留。

相关研究独立维护：[AdaptiveSense](https://github.com/Sver0411/AdaptiveSense)、[SensorTrust](https://github.com/Sver0411/SensorTrust)、[EventGuard-LoRa](https://github.com/Sver0411/EventGuard-LoRa)、[EdgeFaultLab](https://github.com/Sver0411/EdgeFaultLab)、[TinyEdgeBench](https://github.com/Sver0411/TinyEdgeBench)、[AgriTinyVision](https://github.com/Sver0411/AgriTinyVision)。这些项目的硬件或模型结果不构成本系统现场性能证据；复用范围见[集成来源](docs/integration_sources.json)与 [EventGuard 审查](docs/research/EVENTGUARD_REUSE_REVIEW.md)。

MIT。直接复用的 AdaptiveSense Python 文件保留其 MIT 许可证与来源记录。
