# Smart Agriculture Edge AI v0.2

一个最小可运行的**智慧农业边缘 AI 系统**：多节点架构（云端服务器 / 边缘网关 / 传感器节点 / 控制器节点）的完整链路原型。

v0.1 证明这条链路能跑起来；**v0.2 的主题是工程加固** —— 不做架构重写，而是在已有链路上补齐真实系统必须有的东西：

```text
节点注册与归属    谁归谁管，什么时候归谁管
网关故障接管      对端死掉后接管它的节点，并让旧主人彻底失效
消息可靠性        ACK + 重试；ACK（收到了）与 CONTROL_RESULT（执行了）分离
控制安全          幂等执行 + origin epoch 校验，迟到的旧命令打不动执行器
断网容错          服务器不可用时网关本地排队，恢复后按序回放
故障可验证        故障注入 + 4 个可复现场景 + 指标汇总
```

**当前版本全部为软件模拟**，不连接任何真实硬件。所有节点都在本机通过 `asyncio` TCP 通信。

---

## 系统架构

```text
                              ┌──────────────────────────┐
                              │        云端服务器         │
                              │──────────────────────────│
                              │ 历史数据存储 (SQLite)     │
                              │ 去重 (message_id UNIQUE)  │
                              │ 策略版本下发 policy_version│
                              │ 告警与日志管理            │
                              └────────────┬─────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │                                             │
                    ▼                                             ▼

        ┌──────────────────┐                         ┌──────────────────┐
        │   边缘网关 A1     │ ←────────────────────→ │   边缘网关 A2     │
        │──────────────────│   心跳 / generation 同步  │──────────────────│
        │ 节点注册表        │                         │ 节点注册表        │
        │ 归属 + generation │                         │ 归属 + generation │
        │ 边缘决策          │                         │ 边缘决策          │
        │ ACK / 重试        │                         │ ACK / 重试        │
        │ 断网本地队列      │                         │ 断网本地队列      │
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
│ 光照            │  │ Safety Guard   │    │ 光照            │  │ Safety Guard   │
│ SensorTrust     │  │ 幂等执行        │    │ SensorTrust     │  │ 幂等执行        │
│ AdaptiveSense   │  │ epoch 校验      │    │ AdaptiveSense   │  │ epoch 校验      │
└────────────────┘  └────────────────┘    └────────────────┘  └────────────────┘
```

B 与 C 是**并列**节点，C 不挂在 B 后面：

```text
        A1                    B1 采集  →  A1 决策  →  C1 执行
       /  \                              ↓
      B1  C1                   C1 结果  →  A1 上传  →  Server
```

---

## 节点说明

| 节点 | 角色 | 关键职责 |
| --- | --- | --- |
| `Server` | 云端服务器 | 接收 A1 / A2 上传；`message_id` 去重；SQLite 保存传感器历史 / 网关心跳 / 控制命令与结果 / 告警；周期性下发带 `policy_version` 的 `SERVER_POLICY` |
| `Gateway A1 / A2` | 边缘网关 | 节点注册与归属管理；边缘决策；向 C 下发命令并等待 ACK（超时重试）；处理 `CONTROL_RESULT`；与对端心跳、超时接管；服务器不可用时本地排队 |
| `Sensor Node B1 / B2` | 传感器节点 | 模拟生成 `temperature` / `humidity` / `soil_moisture` / `light`；SensorTrust 基础可信检查；AdaptiveSense 动态采样周期；网关故障时切到备用网关 |
| `Controller Node C1 / C2` | 控制器节点 | 收到命令立刻回 ACK；Safety Guard 校验（类型 / TTL / epoch / owner / 幂等 / duration / cooldown）；执行或拒绝；回传 `CONTROL_RESULT` |

每个网关内部拆成 **7 个互不阻塞的 `asyncio` 任务**：

```text
Task 1  接收传感器数据 + 边缘决策
Task 2  上传服务器（含断网排队与回放）
Task 3  接收服务器策略
Task 4  发送控制命令给 C（等待 ACK）
Task 5  处理 CONTROL_RESULT
Task 6  对等心跳 / 看门狗 / 故障接管
Task 7  重试未 ACK 的关键消息            ← v0.2 新增
```

---

## 消息协议

所有模块共用同一信封，TCP + 换行分隔 JSON：

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

v0.2 的消息类型（v0.1 的 6 种 + 新增的 4 种）：

```text
SENSOR_DATA        传感器数据上报
CONTROL_COMMAND    控制命令下发
CONTROL_RESULT     命令执行结果（执行了 / 拒绝了）
HEARTBEAT          网关存活 + role + generation
ALERT              传感器异常 / 命令投递失败
SERVER_POLICY      云端策略下发（带 policy_version）

NODE_REGISTER      B / C 向网关注册                    ← 新增
NODE_REGISTER_ACK  网关回复 owner + generation          ← 新增
NODE_STATUS        网关反向通知归属变更 / 节点保活        ← 新增
ACK                收到确认（与 CONTROL_RESULT 分开）    ← 新增
```

---

## 可靠性模型（Reliability Model）

### 1. 节点注册与归属

网关上有一张内存注册表，每行是：

```text
node_id | node_type | owner_gateway | status | last_seen | generation
```

启动时网关会预注册自己 Zone 的 B / C（`OFFLINE`）。B / C 连上后主动发 `NODE_REGISTER`，网关回 `NODE_REGISTER_ACK`，其中带 **owner 和当前 generation**。控制器把这两个值记在 Safety Guard 里 —— 它因此知道「谁有权命令我」以及「哪个 epoch 才算新」。

### 2. 消息可靠性：ACK + 重试，与执行结果分离

```text
A1 --CONTROL_COMMAND--> C1
A1 <------ACK---------- C1      “我收到了”（只表示收到）
A1 <--CONTROL_RESULT--- C1      “我执行了 / 我拒绝了，原因是 …”
```

这两件事必须分开。如果只有一条回复，「命令丢了」和「命令被拒绝了」无法区分，网关就只能盲目重发——而盲目重发意味着水泵可能被启动两次。

- 关键消息（`CONTROL_COMMAND`、`NODE_REGISTER`）进入 `AckTracker`
- `ACK_TIMEOUT = 2s` 未收到 ACK → 重发，最多 `MAX_RETRIES = 3` 次
- 重试耗尽 → 记 `COMMAND_DELIVERY_FAILED` 计数并上报告警（不静默丢失）
- 投递语义是 **at-least-once**，配合下面的幂等接收端才安全

重传队列里带一个 `(message, is_retry)` 标记：一次重传**不能**被当成一条新命令，否则它会重置自己的重试预算，永远重试下去。

`--drop-command-rate 0.6` 时的真实日志：

```text
[A2] ACK timeout for command_id=8f9431c6ff14, retry 1/3
[A2] ACK timeout for command_id=8f9431c6ff14, retry 2/3
[A2] ACK timeout for command_id=8f9431c6ff14, retry 3/3
[A2] COMMAND_DELIVERY_FAILED command_id=8f9431c6ff14 after 3 retries
[SERVER] alert stored (COMMAND_DELIVERY_FAILED: command 8f9431c6ff14 not acknowledged)
```

同一次运行的指标：

```text
 control commands          : 12
 duplicates                : 2
 retries                   : 13
 delivery failures         : 1
```

也就是说：丢帧 → 重传 → 最终要么送达，要么明确报告投递失败。没有任何一条命令是「不知道去哪了」。

### 3. 控制器幂等

`command_id` 在执行成功后写入 `executed_command_ids`。任何重发/重放的同一 `command_id` 会得到：

```text
[C1] IRRIGATION command is a duplicate (command_id=296719786da4) - not executed again
[C1] CONTROL_RESULT DUPLICATE (DUPLICATE_COMMAND_ID)
```

**执行器不会第二次动作**。这是「至少一次投递」能安全使用的前提。

注意幂等标记只在**执行成功后**写入：一条被 `COOLDOWN` 拒绝的命令不会被记住，等冷却结束后仍然可以正常下达。

### 4. 服务器侧去重

网关可能因为重试、重连、队列回放而重复上传同一条消息。服务器对每个 `message_id` 做 `INSERT OR IGNORE`：

```sql
CREATE TABLE processed_message (message_id TEXT PRIMARY KEY, created_at REAL NOT NULL);
```

重复的直接丢弃并记 `duplicate ... ignored`。**SQLite 里不会出现两条相同上传。**

### 5. 策略版本

`SERVER_POLICY` 带 `policy_version`。网关只接受**比当前更新**的版本，旧的（乱序到达或重放）被忽略：

```text
[A1] SERVER_POLICY v3 ignored (already at v5)
```

并且策略始终是**建议性**的：网关的控制阈值可以来自云端，但决策本身不依赖云端在线。

---

## 网关归属与 Generation（防脑裂）

v0.1 只能**发现**对端静默。v0.2 加了接管，并用一个单调递增的 `generation`（epoch）来保护它：

```text
A1 与 A2 各自维护 generation。
命令带上 gateway_generation。
控制器记住自己接受过的最高 generation，拒绝更旧的（STALE_GENERATION）。
```

关键规则：

```text
1. 新启动的网关 generation = 1，role = ACTIVE
2. 对端心跳超时（HEARTBEAT_TIMEOUT = 10s）→ 视为对端死亡
3. 接管：generation = max(自己, 对端) + 1，role = ACTIVE，对端节点归自己
4. 即使没有节点需要移动，generation 也必须递增
   —— 对端已被判定死亡，它此后发出的任何命令都属于旧 epoch
5. 对端比自己的 generation 高 → 自己降为 STANDBY（不抢）
6. 对端只是 OFFLINE，不会让自己降级
```

**没有 Raft、Paxos、etcd**。两个网关、一个机房的场景里，心跳 + 超时 + 归属 + epoch 就够了。

### 已知边界

- `generation` **只存在内存里**，网关重启后会回到 1。因此 epoch 保护的是「被替换但仍在运行」的网关（deposed but alive），而不是「接管过节点的那台网关随后重启」这种情况。重启后的网关与对端可能同时处于 `ACTIVE`、epoch 相同 —— 但两者**不会真正抢同一个执行器**：`may_control` 要求 `role == ACTIVE` **且**注册表里 owner 是自己，而归属是跟着 TCP 连接走的，一个 B / C 同一时刻只连一台网关。
- 控制器侧的 `current_generation` 同样是内存态，重启后回到 1。真实部署里这类状态应该落在本地持久化上，这一版没有做（见「明确未实现」）。

---

## 故障接管（Gateway Failover）

`--scenario failover` 的真实运行日志（节选）：

```text
14:06:10 [B1] registered with A1 (generation=1)
14:06:10 [C1] registered with A1 (generation=1)

14:06:12 [DEMO] === simulating A1 crash ===
14:06:12 [C1] connection to A1 lost, re-registering elsewhere
14:06:13 [A2] C1 registered (CONTROLLER, owner=A2, generation=1)
14:06:14 [B1] registered with A2 (generation=1)

14:06:34 [A2] FAILOVER A1 -> OFFLINE
14:06:34 [A2] ownership generation = 1 -> 2
14:06:34 [C2] owner_gateway = A2 (generation=2)
14:06:34 [C1] owner_gateway = A2 (generation=2)

14:06:40 [DEMO] === A1 recovering ===
14:06:40 [A1] gateway started on 127.0.0.1:9201 (sensor=B1, controller=C1, peer=A2, generation=1, role=ACTIVE)
14:06:43 [A1] peer ownership generation = 2 (mine 1) - entering STANDBY

14:06:48 [DEMO] === split brain check: delayed command from A1 generation=1 -> C1 ===
14:06:48 [C1] IRRIGATION command received (command_id=3955513564de, duration=10s, generation=1)
14:06:48 [C1] IRRIGATION command rejected: STALE_GENERATION
```

要点：

- B1 / C1 先**自行回退**到 A2（连接是 TCP，断了自己会重连候选列表里的下一个）
- A2 在心跳超时后**正式接管**并把 epoch 推到 2，同时把新 epoch 推给所有自己拥有的节点
- A1 恢复后看到对端 epoch 更高 → 进入 `STANDBY`，**不自动切回**（no automatic failback）
- 最后一条来自旧 epoch 的命令被 `STALE_GENERATION` 拒绝 —— 这就是防脑裂

恢复后的网关状态（真实日志）：

```text
 A1: role=STANDBY health=ONLINE  generation=1 peer=ONLINE
    B1: owner=A1 generation=1 status=OFFLINE
    C1: owner=A1 generation=1 status=OFFLINE
 A2: role=ACTIVE  health=ONLINE  generation=2 peer=ONLINE
    B1: owner=A2 generation=2 status=ONLINE
    C1: owner=A2 generation=2 status=ONLINE
```

注意 A1 的注册表里 B1 / C1 仍然是 `OFFLINE`（它已经不拥有它们了），而 A2 的表里两个节点都在 epoch 2。

### 关于自动切回

**故意没有做自动切回。** 恢复的网关以 `STANDBY` 归队，是否需要把节点交还给它，是一个运维决策，不是一个能靠心跳自动做对的决定（自动切回会带来额外一次无谓的 epoch 抬升和一次控制中断）。这是有意的设计取舍，不是遗漏。

---

## 断网运行（Offline Operation）

服务器**不在控制链路上**。它下线时：

```text
[A1] server unavailable, SENSOR_DATA queued locally (depth=1)
[A1] command sent to C1 (IRRIGATION 10s, command_id=5ecead0933d9, generation=1)
[A1] server unavailable, CONTROL_COMMAND queued locally (depth=2)
[A1] controller result received (IRRIGATION -> REJECTED, reason=COOLDOWN)
[A1] server unavailable, CONTROL_RESULT queued locally (depth=3)
```

服务器恢复后：

```text
[A2] connected to server 127.0.0.1:9100
[A1] connected to server 127.0.0.1:9100
[A2] flushing offline queue (15 messages, oldest first)
[A2] offline queue empty
[A1] flushing offline queue (19 messages, oldest first)
[A1] offline queue empty
```

- 排队是**持久化**的（每个网关一个 SQLite 文件 `gateway_queue_A1.db`），进程重启也不丢
- 回放按 `queue_id` 升序，**最老的先发**
- 回放保留原始 `message_id`，所以服务器去重依然有效
- 排队期间**边缘决策与执行完全不中断** —— 这是「边缘自治」真正的含义

`--scenario server-offline` 的指标（真实运行）：

```text
 offline queued            : 34
 queue replayed            : 34
 server duplicates ignored : 0
```

34 条全部排队、全部回放，一条不丢。

---

## 安全模型（Safety Model）

### Safety Guard 检查顺序

控制器收到命令**不能直接执行**。顺序是刻意安排的（先廉价且无歧义的，再归属/epoch，最后执行器限制）：

```text
1. 命令类型合法                  -> INVALID_TYPE
2. command_id 存在               -> INVALID_COMMAND_ID
3. 命令未过期（COMMAND_TTL=10s） -> EXPIRED
4. generation 不比已接受的小     -> STALE_GENERATION     ← v0.2
5. 来源网关就是当前 owner        -> NOT_OWNER            ← v0.2
6. command_id 未执行过           -> DUPLICATE_COMMAND_ID（幂等）
7. duration 为正数               -> INVALID_DURATION
8. duration 未超上限             -> DURATION_EXCEEDED（30s）
9. 不在 cooldown 窗口内          -> COOLDOWN（灌溉 60s / 通风 30s）
```

`STALE_GENERATION` 与 `NOT_OWNER` 是两道独立的防线：一条来自旧 epoch 的命令无论由谁发出都会被拒；一个非 owner 网关除非携带更高的 epoch，否则也发不出有效命令。

### 传感器数据可信

SensorTrust 判定 `FAULT` 的数据**不会进入控制决策**，只作为 `ALERT` 上报：

```text
[B1] sensor health = FAULT (soil_moisture out of range: 999.0 (expected 0.0..100.0))
[A1] sensor B1 health = FAULT -> control decision skipped
[SERVER] alert stored (SENSOR_FAULT: ...)
```

---

## 如何运行

要求：Python 3.10+（仅使用标准库，无第三方运行时依赖）。

一条命令启动全部节点：

```bash
python demo.py                                   # normal 场景，默认 30 秒
python demo.py --scenario failover               # A1 崩溃 → A2 接管 → A1 以 STANDBY 回归
python demo.py --scenario server-offline         # 云端下线 → 本地排队 → 恢复回放
python demo.py --scenario normal --duration 20 --drop-command-rate 0.5 --duplicate-command
```

也可以每个节点单独启动（和 demo 走的是同一套代码路径）：

```bash
python server/server.py

python gateway/gateway.py --id A1
python gateway/gateway.py --id A2

python sensor_node/sensor_node.py --id B1
python sensor_node/sensor_node.py --id B2

python controller_node/controller_node.py --id C1
python controller_node/controller_node.py --id C2
```

默认端口：Server `9100`，网关 A1 `9201`，网关 A2 `9202`。

---

## 故障注入（Fault Injection）

`demo.py` 的可靠性和容错主张不是「写在那里」，而是**被注入的故障验证过的**。

| 参数 | 作用 |
| --- | --- |
| `--scenario {normal,failover,server-offline}` | 预设时间线，一键复现下面三种场景（split-brain 检查内置在 `failover` 里） |
| `--kill-gateway A1 --at 14` | 第 14 秒模拟指定网关崩溃 |
| `--revive-at 30` | 第 30 秒让被杀的网关重新上线（观察它进入 STANDBY） |
| `--inject-stale-at 38` | 第 38 秒重放「旧主人」在崩溃前发出的最后一条命令（脑裂检查） |
| `--server-offline-at 10` | 第 10 秒云端下线（观察本地排队） |
| `--server-online-at 25` | 第 25 秒云端恢复（观察队列回放） |
| `--drop-command-rate 0.5` | 50% 的控制命令帧被静默丢弃（观察 ACK 超时与重试） |
| `--duplicate-command` | 每条命令故意发两遍（观察幂等：第二次得到 `DUPLICATE`，执行器不重跑） |

四个场景的完整时间线：

```text
normal           正常跑满，无故障
failover         14s 杀 A1 → A2 接管并抬升 epoch → 30s A1 回归 → 38s 注入旧 epoch 命令
server-offline   10s 云端下线 → 25s 云端恢复
split-brain      failover 内置：--inject-stale-at 触发，C1 必须回 STALE_GENERATION
```

---

## Demo 输出

正常链路（真实日志节选）：

```text
[B1] sample #1 soil moisture = 21.6% (temp=24.9C, hum=60.5%, light=791.8)
[B1] sensor health = HEALTHY
[B1] SENSOR_DATA -> A1

[A1] received SENSOR_DATA from B1
[A1] edge decision = IRRIGATION (soil_moisture 21.6 < 25.0)
[A1] command sent to C1 (IRRIGATION 10s, command_id=903854b28d29, generation=1)

[C1] IRRIGATION command received (command_id=903854b28d29, duration=10s, generation=1)
[C1] ACK sent (command_id=903854b28d29)
[C1] safety check passed
[C1] irrigation executed
[C1] CONTROL_RESULT sent to A1

[A1] ACK received (message_id=903854b28d29)
[A1] controller result received (IRRIGATION -> EXECUTED)
[A1] CONTROL_RESULT uploaded to server
[SERVER] control result stored (IRRIGATION -> EXECUTED)
```

`python demo.py --scenario normal --duration 14` 结束时的指标汇总（真实运行）：

```text
==============================================================
 demo summary - metrics
==============================================================
 sensor messages           : 8
 control commands          : 7
 executed                  : 2
 rejected                  : 5
 duplicates                : 0
 retries                   : 0
 delivery failures         : 0
 failovers                 : 0
 offline queued            : 0
 queue replayed            : 0
 server duplicates ignored : 0
==============================================================

==============================================================
 demo summary - sqlite
==============================================================
 sensor_data rows        : 7
 controller_command rows : 7
 controller_result rows  : 7
 gateway_heartbeat rows  : 10
 alert rows              : 1
 processed_message rows  : 36
 sqlite file             : demo.db
==============================================================

 gateway state
 ------------------------------
 A1: role=ACTIVE  health=ONLINE  generation=1 peer=ONLINE
    B1: owner=A1 generation=1 status=ONLINE
    C1: owner=A1 generation=1 status=ONLINE
 A2: role=ACTIVE  health=ONLINE  generation=1 peer=ONLINE
    B2: owner=A2 generation=1 status=ONLINE
    C2: owner=A2 generation=1 status=ONLINE
```

`failover` 场景的指标（真实运行）：

```text
 failovers                 : 1
 retries                   : 0
 delivery failures         : 0
```

`server-offline` 场景的指标（真实运行）：

```text
 offline queued            : 34
 queue replayed            : 34
 server duplicates ignored : 0
```

---

## 测试

```bash
pip install -r requirements.txt
python -m pytest -q
```

**84 个测试**，全部通过（约 28 秒）。覆盖：

```text
协议层        消息序列化 / 反序列化 / 协议校验 / ACK 构造
v0.1 组件     SensorTrust / AdaptiveSense / edge_decision / 策略下发 / SQLite 写入
Safety Guard  类型 / 最大执行时间 / cooldown / 重复 command_id / 过期 / STALE_GENERATION / NOT_OWNER
节点注册表    upsert / transfer / owned_by / 看门狗 expire / snapshot
网关归属      claim / takeover 抬升 epoch / 空接管也抬升 / 观察更高 epoch 降 STANDBY /
              OFFLINE 对端不降级 / peer_generation 单调
消息可靠性    AckTracker 超时判定 / 最多重试 3 次 / 重试后重新计时 / 按 message_id 匹配 ACK
断网容错      OfflineQueue 的 FIFO / 保留 message_id / 回放只删已投递 / 重开文件仍在 /
              Deduplicator 首次为新 / 重放被忽略 / 无 id 不去重 / 落库可计数
端到端        真实 TCP：节点注册与 ACK、网关故障接管、旧 epoch 命令被拒、
              恢复网关不抢权、重复命令不重跑、丢帧后重传到「投递失败」告警、
              服务器下线时边缘不中断、队列回放后服务器只存一份、旧版本策略不覆盖
```

端到端测试使用真实 socket、真实 SQLite、真实 `asyncio` 任务，不是 mock。

### CI

`.github/workflows/tests.yml` 在 Python 3.12 上跑 `python -m pytest -q`（push / PR / 手动触发）。无 Docker、无矩阵、无覆盖率门槛。

---

## 目录结构

```text
Smart-Agriculture-Edge-AI/
├── server/
│   ├── server.py            # 云端服务器
│   ├── database.py          # SQLite 持久化（含 message_id / generation 列）
│   └── dedup.py             # message_id 去重                        ← v0.2
├── gateway/
│   ├── gateway.py           # 边缘网关（7 个 asyncio 任务）
│   ├── registry.py          # 节点注册表                             ← v0.2
│   ├── ownership.py         # 归属 + generation（防脑裂）             ← v0.2
│   ├── offline_queue.py     # 断网 store-and-forward（SQLite）        ← v0.2
│   └── edge_decision.py     # 边缘 AI 接口（规则版，可替换）
├── sensor_node/
│   ├── sensor_node.py       # B 节点 + 数据模拟 + 网关回退
│   ├── sensor_trust.py      # SensorTrust 基础接口
│   └── adaptive_sense.py    # AdaptiveSense 基础接口
├── controller_node/
│   ├── controller_node.py   # C 节点（ACK + 幂等）
│   └── safety_guard.py      # Safety Guard（含 epoch / owner 校验）
├── common/
│   ├── messages.py          # 统一消息协议（10 种类型）
│   ├── reliability.py       # AckTracker / Counters               ← v0.2
│   └── config.py            # 全局配置
├── tests/                   # 84 个测试
├── .github/workflows/tests.yml
├── demo.py                  # 一键启动全部节点 + 故障注入
├── README.md
├── requirements.txt
└── LICENSE
```

---

## 明确未实现（Current Limitations）

这一轮**没有**做，也不打算声称做了：

```text
真实 ESP32 / 真实 LoRa / 真实传感器 / 真实执行器
真实 Edge AI 模型训练（edge_decision 仍是规则，接口可直接替换）
完整 SensorTrust / 完整 AdaptiveSense
RAFT / Paxos / etcd 等共识算法（用心跳 + epoch 代替）
epoch / generation 的持久化（重启后回到 1，见上文「已知边界」）
自动故障切回（恢复的网关停在 STANDBY，见上文说明）
跨机房 / 多网关（>2）的归属协商
传感器节点的反向通道（B 只发不收，读不到 NODE_STATUS 推送）
真实低功耗测试 / 硬件 PCB / OTA
```

同时也没有：Web Dashboard、前端页面、React / Vue、Docker、Redis、Kafka、MQTT Broker、TinyML、登录与权限、微服务、插件系统。

**全部行为都是单机软件模拟**：所谓「A1 崩溃」是把它的 `asyncio` 任务取消并关闭 socket；所谓「水泵执行」是按 `duration × 0.2` 睡一段时间。可靠性机制本身是真的（真实 socket、真实 SQLite、真实超时与重试），但它们保护的对象是模拟设备。

---

## Roadmap

```text
v0.1  端到端链路 + 统一协议 + Safety Guard + 心跳检测          ✅
v0.2  节点注册 / 归属与 epoch / 故障接管 / ACK 与重试 /
      幂等执行 / 断网排队与回放 / 服务器去重 / 故障注入与场景    ✅
v0.3  （未开始，等 v0.2 验收后另行设计）
```

---

## License

MIT
