# Deployment Semantics & Edge Autonomy Realignment

日期：2026-10-06。基线：`f56b857`，工作分支：`codex/deployment-semantics`。这是现有 v0.3.1 的增量维护；历史报告、完整架构图、可靠性机制和模型证据保留。本报告对应本地工作树，未推送、未创建 PR、未运行新的远端 CI。

本报告记录最初 realignment 的298项验收快照。随后五项小补丁及当前代码状态见 [Final five semantic patches](../results/final-five-patches/README.md)；下文测试计数和原验证边界保留历史范围。

## 1. Architecture Audit

修改前已符合 North Star 的部分：SensorTrust / AdaptiveSense 本地感知和调度；A 的 Trust Gate 与 Rule/Logistic/Tree/MLP DecisionEngine；固定 `CONTROLLER_OF_SENSOR` B1→C1、B2→C2；A1/A2 heartbeat、OwnershipManager、generation、接管、注册、恢复 STANDBY；C 的 ACK、TTL、cooldown、owner/epoch、幂等和 CONTROL_RESULT；Cloud 的 SQLite、事务去重、PERSISTED_ACK、版本策略；OfflineQueue 的 store-before-send、FIFO、重连重放。AI 工具已明确属于 synthetic policy imitation，保留这一边界。

本轮完整阅读 README、docs、config、sensor_node、gateway、controller_node、server、ai、firmware、tests、experiments 后修改；未从零重写。North Star 现已固定在 README 靠前位置。两 Zone 的成员关系恒定，只有 Gateway ownership 迁移。`Cloud unavailable ≠ Farm unavailable` 是控制闭环约束。

## 2. Drift Found

1. **真实 B1 丢失上传决定**：C scheduler 已计算 `upload_requested`，但 policy/sample 没有传递它；sensor task 每次入队，network 每次发送。采样频率自适应没有实现必要时才通信。
2. **上传 parity 不完整**：已有算法测试没有穿过实际 B1 policy→sample→queue→telemetry sink；事件恢复未单独触发上报；新增通道与未初始化的上次值比较可能产生假 delta；Python/C 历史容量不同。
3. **常在线集成语义**：Wi-Fi/TCP、注册与 socket 读取同业务消息构造耦合；秒级 lab/simulation 与最终电池部署缺少配置隔离。现有 TCP adapter 仍会保持 Wi-Fi 关联，不能声称现场 duty cycle 已完成。
4. **故障上报语义**：不可信 B1 样本仍更新环境检测历史并重复上报故障。真实读数失败发送空 `data`，Server 会拒收，可能卡住 FIFO 离线重放。
5. **Cloud 重连/回执耦合**：固定软件重连节奏，缺少正式 connectivity 状态；Cloud receipt 等待阻塞上传 worker 的后续持久化入队。原本本地决策没有依赖 Cloud，继续保留并强化此隔离。
6. **重启状态丢失**：策略、Gateway ownership/epoch、C 最高 epoch 原先仅在内存。离线重启缺少 last-known-good 与旧命令拒绝状态。
7. **长期离线增长**：SQLite outbox 缺少明确容量界限及拒绝指标。Dashboard/真实数据训练仍缺失，继续以设计契约表达。

## 3. Changes Made

以下逐文件列出本轮实际修改或新增的源码、配置、测试、文档。结果目录的每次运行保留原始输出，见 [evidence index](../results/deployment-realignment/README.md)。

| 文件 | 实际变更 |
|---|---|
| `README.md` | 永久 North Star、完整两 Zone/failover、三 profile、B 工作流、Cloud/功耗边界、验证矩阵、硬件展示路线。 |
| `common/settings.py` | 递归合并并验证 profile、上传开关/阈值和 outbox 上限；提供 physical B1 配置入口。 |
| `common/field_transport.py` | wake/send/sleep 消息接口和可观测 host mock；没有 E220 驱动。 |
| `common/state_store.py` | 两槽 SQLite checkpoint，canonical JSON、SHA-256、updated_at；policy 可回退，epoch 不回退；显式关闭连接。 |
| `config/software.json` | 增加 10,000 条 / 16 MiB 载荷 outbox 默认上限。 |
| `config/physical_b1.json` | 保存物理温湿度 trust/noise 参数，禁用没有的 soil/light。 |
| `config/profiles/simulation.json` | 软件秒级采样/上传/重连/回放参数。 |
| `config/profiles/lab.json` | 独立加速固件集成参数。 |
| `config/profiles/deployment.json` | 分钟级采样、6h 健康上传、5/15/30/60/300s Cloud 退避工程默认值。 |
| `sensor_node/adaptive_scheduler.py` | 事件恢复同 onset 可触发上传；来源说明更新。 |
| `sensor_node/adaptive_sense.py` | profile、故障签名/提醒/恢复上报；故障暂停环境评分、恢复重置 baseline。 |
| `sensor_node/change_detector.py` | 有界历史容量与 C 对齐，更新来源说明。 |
| `sensor_node/scheduler_config.py` | 从配置推导相同 bounded history capacity。 |
| `sensor_node/sensor_node.py` | simulation/lab 配置入口、共享 payload；明确拒绝在常在线 TCP 模拟器使用 deployment。 |
| `sensor_node/telemetry.py` | 提取与 socket 无关的传感器业务 payload。 |
| `sensor_node/runtime.py` | host duty-cycle skeleton，必要时才 wake/send/sleep，异常也 sleep；保留算法对象。 |
| `firmware/b1/main/b1_types.h` | 纯 sample/stats 类型；上传、事件、health/recovery 字段。 |
| `firmware/b1/main/b1.h` | 引用纯类型，公开 queue/runtime 初始化入口。 |
| `firmware/b1/main/b1_policy.h` | 解耦 ESP-IDF，增加健康通知状态与时间。 |
| `firmware/b1/main/b1_policy.c` | 读取生成 profile；完整传递 upload 位；故障/恢复语义匹配 Python。 |
| `firmware/b1/main/b1_profiles.h` | 由 JSON 自动生成三组 C 参数，算法不写死部署间隔。 |
| `firmware/b1/main/b1_queue.c` | suppressed sample 在任何队列操作前返回；保留 admitted sample 的有界队列行为。 |
| `firmware/b1/main/b1_sensor.c` | 使用受 upload 决定约束的 queue helper；日志增加 upload/event，NaN score 输出 null。 |
| `firmware/b1/main/b1_transport.h` | payload sink 接口及 success/failure 的 payload 所有权契约。 |
| `firmware/b1/main/b1_telemetry.c` | 独立消息构造/第二道 upload guard；故障通知去重、恢复；读数失败显式 null 通道。 |
| `firmware/b1/main/b1_network.c` | 保留 Wi-Fi/TCP adapter，接入 sink、modem power save；epoch 数值/目标/同 epoch owner 校验。 |
| `firmware/b1/main/b1_runtime.c` | opt-in 自动 light sleep，保留 RAM 算法状态；没有 deep sleep。 |
| `firmware/b1/main/main.c` | 调用 runtime 初始化。 |
| `firmware/b1/main/Kconfig.projbuild` | 三 profile 选择及依赖 PM/tickless 的 light sleep 开关。 |
| `firmware/b1/main/CMakeLists.txt` | 注册 queue/runtime/telemetry 和 esp_pm 依赖。 |
| `firmware/b1/components/adaptive_sense/adaptive_scheduler.h` | last-upload validity mask，避免与未上传通道零值比较。 |
| `firmware/b1/components/adaptive_sense/adaptive_scheduler.c` | 有效通道 delta、事件恢复上传，与 Python 同步。 |
| `firmware/b1/README.md` | Wi-Fi 集成定位、profile/上传/休眠/验证边界与操作说明。 |
| `scripts/generate_b1_profiles.py` | 从验证后的共享 JSON 生成 C 配置，支持 `--check`。 |
| `scripts/capture_b1.py` | capture CSV 包含 upload_requested / detected_event；本轮未采集硬件。 |
| `gateway/connectivity.py` | ONLINE/DEGRADED/OFFLINE、饱和退避、限频 CRITICAL 提前 retry。 |
| `gateway/edge_decision.py` | 策略 validate→persist→activate；重启恢复上一有效策略或默认值。 |
| `gateway/gateway.py` | 独立入队与后台 receipt/replay、配置节流、状态指标、epoch 持久化/fail closed、命令保留 sensor origin。 |
| `gateway/offline_queue.py` | 条数/载荷容量准入、重复 ID 复用、拒绝/age 指标；保留已入队未确认数据。 |
| `gateway/ownership.py` | 旧 Gateway 的 STANDBY 不因 equal/stale heartbeat 自动解除。 |
| `controller_node/safety_guard.py` | 持久化 highest epoch/owner，损坏禁止执行，重启完整 cooldown。 |
| `controller_node/controller_node.py` | 模拟执行前持久化，CLI state-db 入口。 |
| `server/database.py` | heartbeat metadata_json 迁移/存储，保留 connectivity/ownership/outbox 元数据。 |
| `server/server.py` | 将完整 heartbeat payload 交给数据库。 |
| `experiments/runner.py` | 记录 simulation backoff；固定 Zone 和接管后两 Zone 的非空命令断言。 |
| `experiments/edgefaultlab.py` | 各外部场景隔离 Controller state-db，避免跨场景 epoch 泄漏。 |
| `tests/test_upload_parity.py` | 50 项共享 trace / C 编译 / generator 验证，覆盖三 profile×八类输入。 |
| `tests/test_deployment_semantics.py` | 17 项配置、radio mock、Cloud 隔离、持久化、队列、故障 null 接收回归。 |
| `tests/c_host/adaptive_trace.c` | 实际四通道 C scheduler host trace runner。 |
| `tests/c_host/b1_policy_trace.c` | 实际 B1 policy/queue/telemetry dispatch runner，计数/guard/null-field 断言。 |
| `tests/c_host/stubs/cJSON.h` | host sink 构造接口桩；不模拟真实 JSON 序列化/RF。 |
| `tests/c_host/stubs/freertos/FreeRTOS.h` | host 队列测试所需最小类型桩。 |
| `tests/c_host/stubs/freertos/queue.h` | host queue dispatch API 桩。 |
| `third_party/adaptive_sense/SOURCE.md` | 记录 C 本地上传语义适配及来源。 |
| `third_party/adaptive_sense/PYTHON_SOURCE.md` | 记录 bounded history/event recovery 等本地适配。 |
| `docs/DEPLOYMENT_SEMANTICS.md` | 固定契约、睡眠状态表、radio/TTL/registration/liveness 与持久化/存储边界。 |
| `docs/CLOUD_BOUNDARIES.md` | 只读 API、Dashboard 和真实版本数据集/离线训练/registry 设计。 |
| `docs/VERIFICATION_STATUS.json` | 更新当前验证状态，保留历史来源，硬件/device metrics 明确未测。 |
| `docs/DEPLOYMENT_REALIGNMENT_REPORT.md` | 本报告。 |
| `results/deployment-realignment/README.md` | 本轮真实运行、失败过程、复现与证据索引。 |

## 4. B Node Result

- **Sampling decision**：Python/C 使用共享配置并逐 sample 对比。deployment STABLE20→40min，ACTIVE10→5min，ALERT5→2→1min；这些是待校准默认值。SensorTrust 与环境 detector 各保留上下文。
- **Upload decision**：`upload_requested` 完整贯穿实际 B1 pipeline；false 不入队、不调用发送 sink。首次有效值、状态/间隔变化、confirmed event onset/recovery、有意义 delta、健康故障/恢复/低频提醒可上报。故障不重复刷屏。
- **Transport**：Wi-Fi/TCP 仍是开发集成 adapter；消息构造已独立。Python wake/send/sleep mock 已测，E220 framing/registration/ownership/sleep adapter 只有契约。
- **Sleep**：固件 modem power save、opt-in MCU 自动 light sleep 已实现并编译，RAM state 保留；真实 duty-cycled E220 未完成。RTC/NVS deep-sleep checkpoint、owner epoch 跨 B 重启均待做。没有电流或电池寿命结论。

固定时间 trace 的 100 次稳定物理 B1 host 样本，simulation/lab/deployment 分别只有 10/3/2 次 SENSOR_DATA sink 调用。这里计数的是 C queue/sink dispatch，不能换算 RF 成功率或能耗。

## 5. Gateway Result

正常 `B1→A1→C1`、`B2→A2→C2` 保持；A1 故障后 `B1→A2→C1`，同时 `B2→A2→C2` 继续。实验逐命令检查 sensor origin→固定 C，并要求接管后的两个路径实际产生命令。旧 epoch 命令拒绝，恢复 A1 留在 STANDBY；没有新增自动 failback。

Cloud backoff、receipt timeout 和离线回放不会等待在本地决策路径上。outbox 准入 worker 与 Cloud flush 分开；stalled receipt/full queue 回归证明仍能本地处理传感器和发命令。部署退避 5/15/30/60/300s，CRITICAL 提前 retry 限频。LKG 策略与 ownership 在 host SQLite 恢复；takeover 先落盘再通知。

C 持久化最高 epoch 后再模拟执行，重启保守 cooldown。NVS 尚未实现；幂等 ID/results 仍只在内存，不能承诺跨重启 exactly-once。两 peer 的 epoch 保护仍不构成任意分区下的共识。

outbox 容量有界并拒绝新准入；已接受消息保留 message_id、at-least-once、dedup、PERSISTED_ACK，不删未确认行。物理磁盘/WAL 限额、priority/critical 预留、损坏行隔离仍待做；满时新历史可能丢失并报告，现场控制继续。

## 6. Cloud Result

完成：既有 TCP ingestion、业务语义验证、SQLite 历史、commit 后持久化确认、dedup、策略 push 继续通过；新增保存 Gateway connectivity/ownership/outbox 元数据。真实物理 read fault 的 null 通道可经过 Gateway 被 Server 持久化接受。

未完成：HTTP API/前端 Dashboard、现场 Dataset Builder、带标签版本数据集、RTX GPU 训练、Model Registry、审批/部署自动化。本轮给出明确输入/输出契约，没有实现额外服务。Logistic/Tree/MLP 仍是 synthetic 软件验证，**NOT validated agricultural intelligence**；未来仅 batch/scheduled retraining。

## 7. Test Results

最终结果与完整原始日志见 [validation summary](../results/deployment-realignment/validation/summary.json) 及 [evidence index](../results/deployment-realignment/README.md)。这两个文件记录最终运行计数、耗时及具体路径，不引用历史 CI 作为本轮结果。

验证覆盖：保留原 231 项；新增 50 项 upload parity 和 17 项 deployment semantics，共 298 项。三 profile×八类 trace 测 B1 trust wrapper 的实际 C policy/queue/sink，以及四通道 core；要求 state/interval/event/upload 一致。C 编译使用 C11、`-Wall -Wextra -Werror`；相同 float32 输入，score 绝对容差 0.002。

全量测试在 Python 3.14 与 3.10 顺序执行；20 个内部 TCP 软件实验另行复验；ESP-IDF5.4.4 分别编译 lab 和 deployment+PM+tickless+light sleep。未 flash。

| 最终实际运行 | 结果 | 日志 |
|---|---|---|
| Python 3.14.7 全量 | **298 passed，42.48s** | `validation/acceptance-python314-sequential.log` |
| Python 3.10.21 全量 | **298 passed，41.77s** | `validation/acceptance-python310-sequential.log` |
| 内部完整软件场景 | **20/20 PASS** | `scenarios-acceptance/suite_summary.json` |
| ESP-IDF lab build | **PASS** | `validation/firmware-lab-acceptance.log` |
| ESP-IDF deployment + light sleep build | **PASS** | `validation/firmware-low-power-acceptance.log` |

以上相对日志路径均位于 `results/deployment-realignment/`。`validation/manifest.json` 保存本地代码/配置 SHA-256 和基线 commit，补足工作树未提交时的来源证据。

失败过程保留：初次 fault trace 断言把 SPIKE 清除后 RANGE 签名变化误当成重复，修正测试；初次 Zone 断言漏导入 config，补齐后重跑；最后两套全量 pytest 并行使用固定 9201/9202 导致端口冲突，顺序重跑。不会把失败隐藏或计为成功。

独立 EdgeFaultLab 本轮 **NOT RUN**：GitHub clone 连接 443 失败。adapter 测试属于本地全量 suite；历史 5/5 不算新证据。未运行新的远端 CI。

## 8. Validation Boundary

| 等级 | 本轮边界 |
|---|---|
| Designed | E220 radio framing/registration/epoch/liveness、NVS/RTC 状态、HTTP/数据集/registry 契约。 |
| Host Tested | trust/scheduler、完整 C 上传 dispatch、mock radio 生命周期、backoff、LKG/epoch 持久化、容量准入、本地控制隔离。 |
| Software Experimentally Evaluated | 20 个完整 TCP 软件场景：Cloud 离线/恢复、接管/恢复、过期 owner/命令、ACK 丢失、dedup/replay 等。 |
| Firmware Implemented | B1 上传门控/消息 sink、三 profile、Wi-Fi modem power save、opt-in 自动 light sleep；两配置 ESP-IDF 编译。 |
| Hardware Tested | 本轮没有。历史 HW1 仅 SHT30 30 次 CRC 正常读数等记录，其范围保持原样。 |
| Pending / not-tested | 新固件板上行为、LoRa RF、真实 A/C 执行、AP 断开后本地 coordination、功耗、电池、农业模型效果。 |

## 9. Remaining Hardware Work

| 项目 | 当前真实状态 |
|---|---|
| B↔A E220 | 接口/协议契约和 mock；没有真实 adapter/RF 结果。 |
| A↔C E220 | 契约；没有真实 adapter、TTL 时钟或 ACK/result 无线结果。 |
| A1↔A2 real heartbeat | TCP 软件实验已测；独立于 Wi-Fi AP 的本地硬件链路待实现。 |
| B low-power | 状态保留/light sleep 编译；radio duty cycle、电流、电池测试未做。 |
| C actuator | host SafetyGuard 和模拟执行；继电器/泵/风扇安全断电、NVS、故障反馈未做。 |
| full failover hardware test | Pending；未人工断 A1、未实测 A2 同时驱动两 Zone、未实测恢复 STANDBY。 |

## 10. Next Steps

1. 实现并验证 E220 的 B↔A、A↔C 和不依赖 AP 的 Gateway coordination；同时移植 NVS epoch/LKG 与安全 TTL 时钟。
2. 刷入本轮 B1，实测 samples/messages 和 radio duty cycle、电流；保留算法状态后再按证据考虑 deep sleep。
3. 完成 README 的 Gateway Failure Hardware Demonstration：断 Cloud/AP、关闭 A1、确认 A2 接管 Zone1 且 Zone2 持续、恢复 A1 留 STANDBY、旧命令拒绝。
4. 稳定采集现场数据后再做只读 Dashboard 与版本数据集/离线训练；先定义标签和评估，不包装 synthetic 结果。
