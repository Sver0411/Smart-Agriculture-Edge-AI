# Smart Agriculture Edge AI v0.1

一个最小可运行的**智慧农业边缘 AI 系统**：多节点架构（云端服务器 / 边缘网关 / 传感器节点 / 控制器节点）的完整链路验证原型。

v0.1 的目标不是做完整产品，而是先证明这条链路能真正跑起来：

```text
B 能采集 -> A 能接收 -> A 能判断 -> C 能安全执行 -> A 能获得执行结果 -> A 能上传 -> Server 能保存
```

同时验证两个网关 A1 / A2 能并行运行并互相检测在线状态。

**当前版本全部为软件模拟**，不连接任何真实硬件。

---

## 系统架构

```text
                           ┌──────────────────────────┐
                           │        云端服务器         │
                           │──────────────────────────│
                           │ 历史数据存储             │
                           │ 全局数据分析             │
                           │ AI 模型训练 / 更新       │
                           │ 策略配置与下发           │
                           │ 设备管理                 │
                           │ 告警与日志管理           │
                           │ 可视化监控               │
                           └────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │                                             │
                 ▼                                             ▼

        ┌──────────────────┐                         ┌──────────────────┐
        │   边缘网关 A1     │ ←────────────────────→ │   边缘网关 A2     │
        │──────────────────│      心跳检测 / 状态同步 │──────────────────│
        │ 边缘 AI 推理      │         / 故障接管      │ 边缘 AI 推理      │
        │ 数据汇聚          │                         │ 数据汇聚          │
        │ 上传 / 下载并行   │                         │ 上传 / 下载并行   │
        │ 本地决策          │                         │ 本地决策          │
        │ 断网自治          │                         │ 断网自治          │
        └────────┬─────────┘                         └────────┬─────────┘
                 │                                              │
       ┌─────────┴─────────┐                        ┌──────────┴──────────┐
       │                   │                        │                     │
       ▼                   ▼                        ▼                     ▼

┌────────────────┐  ┌────────────────┐    ┌────────────────┐  ┌────────────────┐
│ 传感器节点 B1   │  │ 控制器节点 C1   │    │ 传感器节点 B2   │  │ 控制器节点 C2   │
│────────────────│  │────────────────│    │────────────────│  │────────────────│
│ 土壤湿度        │  │ 水泵 / 电磁阀   │    │ 土壤湿度        │  │ 水泵 / 电磁阀   │
│ 空气温湿度      │  │ 风扇 / 加湿器   │    │ 空气温湿度      │  │ 风扇 / 加湿器   │
│ 光照 / 雨量     │  │ 安全控制模块    │    │ 光照 / 雨量     │  │ 安全控制模块    │
│ SensorTrust     │  │ 本地安全联锁    │    │ SensorTrust     │  │ 本地安全联锁    │
│ AdaptiveSense   │  │ 低功耗运行      │    │ AdaptiveSense   │  │ 低功耗运行      │
│ 电池供电        │  │ 休眠唤醒        │    │ 电池供电        │  │ 休眠唤醒        │
│ 深度休眠        │  │                 │    │ 深度休眠        │  │                 │
└────────────────┘  └────────────────┘    └────────────────┘  └────────────────┘
```

注意 B 与 C 是**并列**节点，C 不挂在 B 后面：

```text
        A1
       /  \
      B1  C1
```

---

## 节点说明

| 节点 | 角色 | 关键职责 |
| --- | --- | --- |
| `Server` | 云端服务器 | 接收 A1 / A2 上传的数据；SQLite 保存传感器历史、网关状态、控制命令与结果、告警；周期性下发 `SERVER_POLICY` |
| `Gateway A1 / A2` | 边缘网关 | 接收 B 数据、数据检查、边缘决策、上传 Server、接收 Server 配置、下发控制命令给 C、接收执行结果、与另一网关互发心跳 |
| `Sensor Node B1 / B2` | 传感器节点 | 模拟生成 `temperature` / `humidity` / `soil_moisture` / `light`；SensorTrust 基础可信检查；AdaptiveSense 动态采样周期 |
| `Controller Node C1 / C2` | 控制器节点 | 接收控制命令；Safety Guard 安全检查；执行或拒绝；回传 `CONTROL_RESULT` |

每个网关内部拆成 6 个互不阻塞的 `asyncio` 任务：

```text
Task 1  接收传感器数据 + 边缘决策
Task 2  上传服务器
Task 3  接收服务器配置
Task 4  发送控制器命令
Task 5  处理控制结果
Task 6  网关 heartbeat（对等网关 + 上报 Server）
```

---

## 当前实现

**统一消息协议**（所有模块共用同一信封，TCP + 换行分隔 JSON）：

```json
{
  "type": "SENSOR_DATA",
  "source": "B1",
  "target": "A1",
  "timestamp": 1234567890.0,
  "message_id": "9f2c1ab34d5e",
  "payload": {}
}
```

消息类型：`SENSOR_DATA` / `CONTROL_COMMAND` / `CONTROL_RESULT` / `HEARTBEAT` / `ALERT` / `SERVER_POLICY`。

**边缘 AI 接口**（v0.1 内部是规则，接口与最终形态一致，可直接替换成 Logistic Regression / Decision Tree / Tiny MLP）：

```python
def edge_decision(sensor_data):
    ...
# soil_moisture < 25  ->  IRRIGATION
# temperature   > 32  ->  VENTILATION
```

**SensorTrust 基础检查**：

```python
check_sensor_health(data)   # -> HEALTHY / FAULT
```

字段缺失、非数值、温度 / 湿度 / 土壤湿度 / 光照越界都判为 `FAULT`。判定为 `FAULT` 的数据**不会进入控制决策**，而是作为 `ALERT` 上报网关。

**AdaptiveSense 基础动态采样**：

```python
next_sample_interval(history)   # 数据稳定 -> 5s，变化明显 -> 2s
```

**Safety Guard**（控制器收到命令也不能直接执行）：

```text
命令类型是否合法            -> INVALID_TYPE
command_id 是否缺失/重复    -> INVALID_COMMAND_ID / DUPLICATE_COMMAND_ID
命令是否过期（>10s）        -> EXPIRED
duration 是否为正数         -> INVALID_DURATION
是否超过最大允许时间        -> DURATION_EXCEEDED   (IRRIGATION / VENTILATION 均 30s)
是否处于 cooldown           -> COOLDOWN            (灌溉 60s，通风 30s)
```

**网关心跳**：A1 与 A2 每 3 秒互发一次 `HEARTBEAT`，超过 10 秒未收到即标记对端 `OFFLINE` 并打印 `[A1] A2 detected offline`。v0.1 **只检测，不接管**。

**云端下发的策略**（`SERVER_POLICY`，同时保存在 `common/config.py`）：

```json
{
  "soil_moisture_threshold": 25.0,
  "temperature_threshold": 32.0,
  "irrigation_duration": 10,
  "ventilation_duration": 5
}
```

---

## 如何运行

要求：Python 3.10+（仅使用标准库，无第三方运行时依赖）。

每个节点都可以单独启动：

```bash
python server/server.py

python gateway/gateway.py --id A1
python gateway/gateway.py --id A2

python sensor_node/sensor_node.py --id B1 --gateway A1
python sensor_node/sensor_node.py --id B2 --gateway A2

python controller_node/controller_node.py --id C1 --gateway A1
python controller_node/controller_node.py --id C2 --gateway A2
```

也可以一条命令启动全部节点：

```bash
python demo.py                    # 默认运行 30 秒
python demo.py --duration 20
python demo.py --kill-peer-at 20  # 第 20 秒模拟 A2 故障，观察 A1 检测到对端离线
```

其它常用参数：

```bash
python sensor_node/sensor_node.py --id B1 --gateway A1 --inject-fault 4   # 第 4 次采样注入异常数据
python server/server.py --port 9100 --db smart_agriculture.db
```

默认端口：Server `9100`，网关 A1 `9201`，网关 A2 `9202`。

---

## Demo 示例

`python demo.py` 的终端输出（节选，真实运行日志）：

```text
01:25:10 [B1] sample #1 soil moisture = 21.6% (temp=24.9C, hum=60.5%, light=791.8)
01:25:10 [B1] sensor health = HEALTHY
01:25:10 [B1] SENSOR_DATA sent to A1
01:25:10 [B1] next sampling interval = 5s

01:25:10 [A1] received SENSOR_DATA from B1
01:25:10 [A1] edge decision = IRRIGATION (soil_moisture 21.6 < 25.0)
01:25:10 [A1] SENSOR_DATA uploaded to server
01:25:10 [A1] command sent to C1 (IRRIGATION 10s, command_id=5e1ba420ec10)

01:25:10 [C1] IRRIGATION command received (command_id=5e1ba420ec10, duration=10s)
01:25:10 [C1] safety check passed
01:25:12 [C1] irrigation executed
01:25:12 [C1] CONTROL_RESULT sent to A1

01:25:12 [A1] controller result received (IRRIGATION -> EXECUTED)
01:25:12 [A1] CONTROL_RESULT uploaded to server
01:25:12 [SERVER] control result stored (IRRIGATION -> EXECUTED)

01:25:13 [A1] heartbeat -> A2
01:25:13 [A2] heartbeat -> A1
```

异常数据被拦下（`--inject-fault`）：

```text
01:25:22 [B1] sensor health = FAULT (soil_moisture out of range: 999.0 (expected 0.0..100.0))
01:25:22 [B1] ALERT sent to A1 (data never reached the decision stage)
01:25:22 [A1] sensor B1 health = FAULT -> control decision skipped
01:25:22 [SERVER] alert stored (B1: soil_moisture out of range: 999.0 (expected 0.0..100.0))
```

安全联锁拒绝（同一类命令处于 cooldown 内）：

```text
01:25:15 [C1] IRRIGATION command received (command_id=ae2086969807, duration=10s)
01:25:15 [C1] IRRIGATION command rejected: COOLDOWN
01:25:15 [C1] CONTROL_RESULT sent to A1
```

采样周期随环境变化（AdaptiveSense）：

```text
01:25:15 [B2] next sampling interval = 2s
01:25:17 [B2] next sampling interval = 5s
01:25:28 [B1] next sampling interval = 5s
01:25:33 [B1] next sampling interval = 2s
```

对端网关离线检测：

```text
01:25:30 [DEMO] simulating an A2 failure (v0.1 only detects it, no takeover)
01:25:40 [A1] A2 detected offline
```

`python demo.py` 结束时会打印 SQLite 里落库的行数：

```text
============================================================
 demo summary
============================================================
 sensor_data rows        : 18
 controller_command rows : 18
 controller_result rows  : 18
 gateway_heartbeat rows  : 19
 alert rows              : 1
 sqlite file             : demo.db
============================================================
```

---

## 测试方法

```bash
pip install pytest
pytest
```

25 个测试，覆盖：

```text
消息序列化 / 反序列化与协议校验
SensorTrust 基础检查
AdaptiveSense 采样周期变化
edge_decision 与策略下发
Safety Guard：类型 / 最大执行时间 / cooldown / 重复 command_id / 过期命令
心跳超时判定
SQLite 写入
端到端链路（B -> A -> C -> A -> Server，真实 TCP + 真实 SQLite）
```

---

## 目录结构

```text
Smart-Agriculture-Edge-AI/
├── server/
│   ├── server.py            # 云端服务器
│   └── database.py          # SQLite 持久化
├── gateway/
│   ├── gateway.py           # 边缘网关（6 个 asyncio 任务）
│   └── edge_decision.py     # 边缘 AI 接口（规则版，可替换）
├── sensor_node/
│   ├── sensor_node.py       # B 节点 + 数据模拟
│   ├── sensor_trust.py      # SensorTrust 基础接口
│   └── adaptive_sense.py    # AdaptiveSense 基础接口
├── controller_node/
│   ├── controller_node.py   # C 节点
│   └── safety_guard.py      # Safety Guard
├── common/
│   ├── messages.py          # 统一消息协议
│   └── config.py            # 全局配置
├── tests/                   # 25 个测试
├── demo.py                  # 一键启动全部节点
├── README.md
├── requirements.txt
└── LICENSE
```

---

## 暂未实现功能

v0.1 **明确没有**实现以下内容：

```text
真实 ESP32
真实 LoRa
真实传感器
真实执行器
真实 Edge AI 模型（未做任何模型训练）
完整 SensorTrust
完整 AdaptiveSense
自动网关故障接管（只做「检测到网关离线」）
真实低功耗测试
硬件 PCB
```

同时也没有：Web Dashboard、前端页面、React / Vue、Docker、Redis、Kafka、MQTT Broker、TinyML、OTA、登录与权限系统、微服务、插件系统。

---

## License

MIT
