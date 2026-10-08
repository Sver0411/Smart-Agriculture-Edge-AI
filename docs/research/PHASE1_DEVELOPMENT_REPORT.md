# research 第一阶段正式开发总结

日期：2026-10-08（Asia/Shanghai）。本轮交付 **Phase 0 与 Phase 1 的实际代码、测试与固件编译**，并准备后续低功耗/射频硬件验证。整个科研平台的 Phase 2–5 尚未完成，不能把这个里程碑描述为全部优化完成。

## 1. Git 状态

- 干净的原工作区在 main；执行 git fetch origin 后，从已有 origin/research 建立本地 tracking research。
- 基础 research：`ccff0ae690073c9cc40b184932fe7b98abd70302`。
- main：`167e307ad220d2df2b3405ede8ac8f47220c13e8`，未移动、未修改、未合并。
- 网关事务确认提交：`ffb5615225ba0a7b76ad8ac65da7a9821a239264`。
- B1 缓存/身份/确认基线提交：`827cc393af34a1921613e9239785a625f191eafb`。
- 文档、原始证据和测试采集随后单独提交；最终交付 SHA 和远程推送状态以最终回复为准。
- 未创建 PR、未 force push、未修改 Tag、未删除历史结果或改写历史。

## 2. 发现的问题

| 文件 | 原因、级别与真实影响 | 本轮结果 |
| --- | --- | --- |
| b1_queue.c | P0：满队列先拿走最旧样本，再塞入新样本；可能驱逐未确认关键数据 | 先复现失败断言，再替换为不驱逐的有界缓存，NORMAL 上限 12/总槽 16 |
| b1_network.c | P0：xQueueReceive 后 TCP send 成功就移除；send 不是可靠保存 | 等待身份、来源、目标、scope 和契约匹配的持久化 ACK；有限重试后保留 FAILED |
| b1_telemetry.c | P0：每次重发都构造新 message_id，使用当前 boot_id | 入队冻结逻辑身份和 JSON；断电恢复保留原 boot，SENSOR/ALERT 身份独立且稳定 |
| main.c / sensor task | P0：32 位随机 boot、uint32 序号可回绕；缓存纯 RAM；NVS 初始化异常会自动擦除 | MAC+持久化启动计数+128 位随机；序号耗尽停新增；HIGH NVS 快照；异常不自动擦除 |
| b1_policy.c 调用 as_update | P0：核心把 upload intent 直接标成 reported，队列失败/无确认仍可能推进 delta/heartbeat | 新失败测试复现；在 B1 包装层保存/还原报告字段，只有可靠 ACK 完成后更新；核心源码不改 |
| gateway sensor/outbox 路径 | P0：没有 B→A durable receipt，也没有跨 cloud 清理后的 B 重发凭据 | outbox+receipt 同事务，FULL 同步；不同证据复用身份拒绝；重复重发只 ACK，不重复排队或决策 |
| gateway control freshness | P0：恢复旧样本可能被当成当前控制输入 | 旧 boot、未知/过大的 age、持久化高水位以下乱序数据只入历史；不是密码学认证 |

这里的“修复”指源码实现及所列软件/编译验证；不指真实物理断电已经验证。存储损坏恢复的原则是保留证据、拒绝/停止，未实现自动修复数据库或 NVS。

## 3. 修改内容与兼容

- 增加便携 `b1_outbox.c/.h`，实际固件和 host fault tests 使用同一状态机；`b1_storage.c/.h` 是 NVS/互斥锁后端，核心不依赖 RTOS。
- 现有 queue/network/telemetry/main/sensor 包装接入新闭环，继续使用 Wi-Fi/TCP。关键快照是版本+CRC+固定身份+原消息，没有算法指针；普通采样不写 Flash。
- B1 的报告基线通过传感器任务领取确认记录后更新，避免网络任务并发修改算法上下文。增加任务栈预算，编译验证实际内存占用。
- `gateway/sensor_delivery.py` 定义 opt-in 契约；OfflineQueue 新增 sensor_receipts 表和原子 admission，旧数据库增量建表，无需清空；回放仍使用原 FIFO 和 SERVER PERSISTED_ACK。
- 不改消息类型和 AdaptiveSense/SensorTrust 核心。不带新 delivery_contract 的旧消息保留行为；旧网关不会让新固件误认为交付成功。
- generated profile 增加配置哈希版本；host 测试复用明确版本的 MIT cJSON 验证真实 JSON，不用 stub 将调用成功冒充序列化验证。生产继续链接 ESP-IDF cJSON。
- CI 的 push 分支增加 research；未声称远程 CI 已经通过。

详细状态、容量、重试和迁移边界见 [B1_RELIABLE_DELIVERY.md](B1_RELIABLE_DELIVERY.md)。

## 4. 真实验证结果

| 命令/检查 | 实际结果 |
| --- | --- |
| `.venv/bin/python -m pytest -q` 基线 | 350 passed，44.81 s |
| 原固件满队列 C 断言 | 失败：新样本被接受、旧样本被驱逐；保存原测试源与 queue-before.log |
| 初始新 gateway receipt tests | 5 failed：源码没有所需确认/拒绝行为；gateway-before.log |
| 确认报告基线失败测试 | 1 failed：as_update 直接设 has_uploaded；report-baseline-before.log |
| 目标可靠交付/真实 wire/原有 parity/outbox/Server receipt 测试 | 91 passed，6.05 s；targeted-acceptance.log |
| 最终完整回归 | 363 passed，48.64 s；committed-code-regression.log |
| `python -m experiments.runner --all --output results/research-phase1/scenarios-acceptance` | 20/20 PASS；seed=42，真实本机 TCP，软件传感/执行器 |
| ESP-IDF 5.4.4 `idf.py -C firmware/b1 build` | PASS；idf-release-build.log；ESP32-S3 固件未烧录 |
| `idf.py -C firmware/b1 size` | image summary 280736 B，DIRAM 静态报告 148827 B；是链接统计，不是运行时功耗或剩余堆实测 |
| `scripts/generate_b1_profiles.py --check` / `git diff --check` | 通过；profile freshness 亦在完整测试中执行 |

C outbox 在 host 运行 ASan/UBSan，故障包括发送前重启、发送后 ACK 前重启、伴随 ALERT ACK 丢失、未知 ACK、失败清理写入、连续断网、满载、CRC/版本错误、无效/最大序号。存储 callback 模拟持久化，不等于实际 ESP-IDF NVS 掉电测量。

真实 C 生成的健康/故障 SENSOR_DATA 与 ALERT 通过真实 TCP 进入 A/Server：丢第一条 B 的网关 ACK，等待 cloud 清理后重发同一身份，最终只有 **2 条样本历史、1 条告警**，没有重复样本；原 JSON 与 transport events 保存于 raw/。网关重启后的重复/乱序路径、事务中途失败回滚、receipt 上限、RAM 网关拒绝 durable ACK 也经过 host tests。

本机直接 export.sh 起初失败：系统 Python 3.14 对应 IDF 环境未安装。使用已存在的 IDF Python 3.13 后编译成功，失败日志也保留。曾有中间测试夹具断言错误和临时失败，日志保留但不作为最终失败结论。

## 5. 可证实的研究结果与限制

- 完整测试从 350 增加到 363，最终全部通过；20 个既有故障场景全部通过。
- 缓存实验断言 NORMAL 0 次样本持久化调用；一次成功 HIGH 周期 1 次保存+1 次删除，4 次重试不产生额外样本写入。是应用 callback 计数，**不是真实 Flash 擦写数或能耗**。
- 16 槽、NORMAL 12、5 次每启动尝试是明确资源限制；满载/NVS 失败拒绝新数据，普通数据断电可丢失。FAILED 记录保留，占用容量；重启重开有限尝试窗口，长期交付率不保证。
- 默认 NVS 24 KiB 与其他功能共享，HIGH 实际容量可能低于 16；每条消息有最大长度限制。A receipt 默认 100000 身份，满后拒绝新身份，不自动过期。
- `.bin` 实际 280848 B，SHA256 `7e1a16db9695af1dbdaa246fd63f266cc1b59f9a3892fad04a070c1a8ff86761`；这次构建是本机配置，不能假设换板/配置后哈希相同。
- 没有硬件功耗、RF 丢包率、实际电池寿命、农作物效果或物理执行安全结论。ACK 等待和未确认基线可能增加发送/采样请求，不能宣称低功耗优化已经获胜。
- 本轮没有新增联合算法胜负实验；固定短/中/长、AdaptiveSense、ControlRelevanceGate 与联合策略的公平多种子对照仍待建设。既有场景是可靠性回归，不能替代能耗/事件召回研究。

全部新证据在 [results/research-phase1](../../results/research-phase1/README.md)，含环境、来源 SHA、种子、配置、原始 records、负面日志和哈希。历史实验未覆盖。

## 6. 尚未完成的工作分级

| 状态 | 范围 |
| --- | --- |
| 已通过软件测试 | B1 便携缓存、身份/ACK、错误/重启/去重、B1 包装层确认基线、真实 C JSON→TCP→SQLite |
| 已通过固件编译 | 实际 B1 TCP/NVS 适配，ESP-IDF 5.4.4 / ESP32-S3 |
| 已编码但未完成真实硬件验证 | NVS 实际掉电、剩余空间/寿命、任务栈与运行时堆、Light Sleep 运行与电流 |
| 尚未编码/迁移 | Deep Sleep 算法/owner/单调时间恢复；E220 adapter/二进制帧/分片；Python SensorRuntime 的 durable-ACK 迁移；长期 receipt 归档与跨启动全寿命预算 |
| 尚未开展本轮专项 | A 非对称分区/仲裁、有限优先回放/WAL硬限/损坏恢复；C 执行器抽象与独立物理关断；公平联合采样通信实验 |
| 已完成真实硬件验证 | 本轮 **无** |

EventGuard-LoRa HEAD 已实际核对，复用边界见 [EVENTGUARD_REUSE_REVIEW.md](EVENTGUARD_REUSE_REVIEW.md)。未导入其源码，未复测其射频结果。

## 7. 下一阶段最值得做的三个任务

1. 对本版 B1 做断电/ACK 丢失/NVS 满载实测，记录完整电流曲线，再实现有版本和单调时间契约的算法状态保存；先验证真实损失与成本。
2. 从固定版本 EventGuard 设计建立独立 E220 codec/adapter，优先测试分片、CRC、重组上限、ACK scope 和预算，之后才接硬件射频。
3. 用相同轨迹、随机种子和电池/无线成本条件建立联合策略公平对照，并补入 A/C 分区和安全降级故障矩阵；保留漏检与失败，不保证复杂策略获胜。

## 8. 你需要进行的硬件操作

见 [HARDWARE_VALIDATION_PHASE1.md](HARDWARE_VALIDATION_PHASE1.md)：列明所需 ESP32-S3/SHT30/仪器、GPIO 核对、构建烧录命令、断电与 ACK 测试顺序、原始串口/电流采集和积分公式。空白 CSV 模板已提供。先备份 NVS，保持 C 模拟，禁止为使结果通过而擦除缓存或接通真实执行器。
