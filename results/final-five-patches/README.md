# Final five semantic patches

2026-10-06，基于已经完成的本地 deployment realignment 工作树。本轮只补五项语义；原 North Star、README 大结构、双 Zone、A1/A2 failover、TCP simulation 和可靠性机制保留。没有提交/推送或新远端 CI。

## Files Changed

| 文件 | 本轮增量 |
|---|---|
| `sensor_node/control_relevance.py` | 新增轻量 communication gate：可信 soil/temperature 的双向 crossing、配置 margin entry、成功报告基准、local policy setter。 |
| `sensor_node/adaptive_sense.py` | 合并 relevance/health/core 上传原因；保留不可信环境评分隔离；提供成功报告通知。 |
| `sensor_node/adaptive_scheduler.py` | 保留所有 scheduler upload_reasons；wrapper-only report 同步 heartbeat/delta 参考。 |
| `sensor_node/sensor_node.py` | TCP send 成功后更新 relevance baseline。 |
| `sensor_node/runtime.py` | mock/adapter send 成功后更新 relevance baseline；异常仍 radio sleep。 |
| `common/settings.py` | 验证 margin、critical reserve、recent-command window。 |
| `config/software.json` | reserve 默认1000条/1,677,722bytes；recent IDs64；baseline margins。 |
| `config/profiles/simulation.json` | margin0，保持模拟 timing。 |
| `config/profiles/lab.json` | margin0，保持 lab timing。 |
| `config/profiles/deployment.json` | soil margin2、temperature margin0.5，可配置工程默认值。 |
| `scripts/generate_b1_profiles.py` | 生成 C local threshold / margin。 |
| `firmware/b1/main/b1_profiles.h` | 更新生成参数。 |
| `firmware/b1/main/b1_control_relevance.h` | 新增纯 C 温度 crossing / margin gate。 |
| `firmware/b1/main/b1_policy.h` | 新增成功 admitted baseline 和 local threshold setter。 |
| `firmware/b1/main/b1_policy.c` | 合并 threshold/health/core trigger；无关湿度故障不掩盖可信温度；失败 admission 不推进 baseline。 |
| `firmware/b1/main/b1_types.h` | sample 增加 control_relevant_change / upload_reasons mask。 |
| `firmware/b1/main/b1_sensor.c` | 只有 queue admission 成功才标记 reported。 |
| `firmware/b1/main/b1_telemetry.c` | sampling 中输出完整 upload_reasons JSON array。 |
| `firmware/b1/components/adaptive_sense/adaptive_scheduler.h` | 统一上传原因 bit definitions。 |
| `firmware/b1/components/adaptive_sense/adaptive_scheduler.c` | 收集全部 core trigger，保留原 bool 策略。 |
| `gateway/offline_queue.py` | HIGH/NORMAL 准入、条数/字节 reserve、数据库迁移、per-priority rejection metrics；不 evict、不改 replay FIFO。 |
| `gateway/gateway.py` | 容量拒绝 local alert latch、heartbeat evidence；持久化 takeover 后产生 HIGH failover history event。 |
| `controller_node/recent_commands.py` | 新增有界 RecentCommandStore，durable INTENT/result，未完成 intent 不驱逐，关键数据不回退。 |
| `controller_node/controller_node.py` | 加载 IDs；intent commit 在模拟执行之前；结果持久化失败报告 UNKNOWN 并禁止后续执行。 |
| `common/field_contract.py` | ZoneUplink 与无 wall-clock 的 FieldFreshnessGuard host models；不是 wire codec。 |
| `common/field_transport.py` | 补 Zone-oriented transport/freshness 契约。 |
| `tests/test_final_five_patches.py` | 33项针对五个漏洞的行为/失败/重启测试。 |
| `tests/test_upload_parity.py` | 原50项保留，新增6项 physical crossing/admission/unrelated-fault parity；比较原因。 |
| `tests/c_host/b1_policy_trace.c` | 成功 queue 才推进参考；可注入第二次 admission rejection，输出原因 mask。 |
| `tests/c_host/stubs/cJSON.h` | 最小 array 构造桩，明确只测 dispatch。 |
| `README.md` | 原结构内补五条规则，纠正旧 volatile-ID/唯一 wall-clock 限制描述。 |
| `docs/DEPLOYMENT_SEMANTICS.md` | 更新 five-patch 契约、持久化/容量/freshness 边界。 |
| `docs/DEPLOYMENT_REALIGNMENT_REPORT.md` | 一行标明旧298项报告为历史快照，链接本次补丁。 |
| `firmware/b1/README.md` | 补 physical 温度 relevance 和 admission/硬件边界。 |
| `docs/VERIFICATION_STATUS.json` | 追加本次验证；保留上一轮298项和旧 manifest 作为历史证据。 |
| `experiments/runner.py` | Cloud恢复后以有界持久化完成检查代替固定2.5s吞吐假设；原排空/250条断言不变，10s预算写入 config。 |
| `results/final-five-patches/` | 本轮 before-source hashes、测试/build/scenario日志、最终汇总/manifest。 |

## Five Issues Status

1. **Control-relevant upload — Host Tested / Firmware Implemented**：soil `< threshold` 和 temperature `> threshold` 双向 crossing 均立即上报；margin entry 可配置；upload_reasons 不丢其它原因。以成功发送/队列准入值作参考，失败不会消费 crossing。故障通道不产生正常 crossing；其他通道故障不掩盖可信温度。物理 B1 没有 soil，C 测的是温度逻辑；Python 支持两者。B 没有 actuator DecisionEngine。Local threshold setter 已提供，未来无线 adapter 的 policy version/threshold exchange 待完成，不宣称与所有动态 A 策略已自动同步。
2. **Critical queue reserve — Host Tested**：HIGH 包括 CRITICAL、CONTROL_RESULT、命令投递失败、takeover 和严重 fault。NORMAL 不能占满 reserved entries/bytes；HIGH 可到 total bound。总容量满时明确拒绝、计数、log/local alert state；不删除未确认消息。Priority 是 admission，重放保持全局 FIFO、IDs、at-least-once、dedup、PERSISTED_ACK。不是物理磁盘/WAL quota。
3. **Zone-oriented LoRa contract — Designed / Host Tested model**：B1/Zone1、B2/Zone2 固定；同一 uplink 在 ownership takeover 前后由允许的 Gateway 处理。B 不承担 A1/A2 health/heartbeat，不需要通过持续 probe 改绑定。现有 TCP fallback 不改。没有 E220 driver。
4. **Recent command persistence — Host Tested**：默认64个 IDs，可配置。validate→persist INTENT→模拟执行→persist result。重启后 completed 和 unresolved IDs 都阻止二次执行；关键数据损坏/intent 写失败默认 DO NOT EXECUTE；结果写失败保留 INTENT，报告 UNKNOWN。仅 completed oldest 可以离开窗口，unfinished 不驱逐。窗口之外、真实 actuator 状态、文件整体丢失/provisioning 仍需设备契约，不能承诺永久 exactly-once。NVS mapping 仅设计。
5. **Wall-clock-independent freshness — Designed / Host Tested model**：owner/epoch + gateway/receiver sessions + command sequence/id + receiver预发唯一 receive window + 本地 monotonic TTL/retry bound。无 wall clock 也可接受有效上下文；旧 epoch/session/window/sequence 或超时拒绝。收到延迟包后重新开 TTL 不能证明 freshness。TCP legacy TTL 保持兼容；field model 尚未接入无线固件。

## Tests

最终实际结果见 [summary](validation/summary.json)。原298项全部保留，新增33项五补丁测试+6项parity，共337项。原始结果不由历史 CI 推断。

- 针对性旧能力回归：93 passed（`targeted-initial.log`）。
- 新增与 parity 最新组合：89 passed，8.42s（`new-tests-final.log`）。
- Python3.14.7 全量：**337 passed，44.31s**（`full-python314-final.log`；完成 replay barrier 后）。
- Python3.10.21 全量：**337 passed，103.70s**（`full-python310-sequential.log`；production代码最终版，随后 harness 等待修正由下面 Python3.10 的20场景复验）。
- lab / deployment+PM+tickless+light-sleep：**ESP-IDF5.4.4 build PASS**（`firmware-lab.log` / `firmware-low-power.log`），未 flash。
- Python3.10.21 最终内部场景：**20/20 PASS**（`scenarios-final/suite_summary.json` / `validation/scenarios-final.log`）；最终 harness 使用10s完成预算，断言不变。SQLite运行位于 /tmp，JSON/raw日志随后归档到本目录。
- `full-python314.log` 和 `scenarios/` 是并行负载时的失败过程：336 passed/1 failed，250条 replay 检查时余71；内部15/20。顺序工作区场景为16/20（`scenarios-sequential/`），临时目录的原固定等待版本为18/20（`scenarios-temp-before-barrier/`）。最终定位到 Cloud恢复后的固定2.5s吞吐假设；等待改为10s预算内的完成检查，原排空/250条持久化断言和故障注入保持。所有失败日志保留，未删除测试。

`baseline-source.json` 记录本轮前的 dirty source hash，`validation/manifest.json` 记录本次最终 source hash；上轮报告/manifest 保持其原范围，不覆盖历史结果。数据库仍按已有 .gitignore 仅本地保留，JSON/raw logs 是可保存证据。

## Validation Boundary

Host Tested：通信 gate、mock failed send、critical admission/migration/metrics、SQLite intent/result/restart/corruption、Zone/freshness 模型。Firmware Implemented：physical temperature gate 与 upload-reason payload；实际 build 证据见 summary。Designed：E220 framing/session handshake/policy exchange、NVS 映射、真实时钟/执行安全。Hardware Tested：本轮无，没有 flash、E220 RF、NVS、电流或 actuator 新结果。

## Remaining Hardware Work

实现 E220 本地链路和 gateway/session/threshold handshake；把 recent intents/epoch 映射到 NVS 并验证断电；测 B duty cycle/电流和 C 实际执行；完成双 Zone Gateway Failure Hardware Demonstration。下一阶段应进入这些真实硬件验证，不扩展纯软件功能。
