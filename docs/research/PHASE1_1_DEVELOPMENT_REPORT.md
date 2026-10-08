# Phase 1.1 软件可靠性验证报告

本轮完成 A–F 的软件实现、故障注入和编译验证。未连接开发板、未烧录、未测功耗、未做实体掉电或执行器实验。P2 的 E220 codec 与 Deep Sleep 算法快照尚未开发；现有 Wi-Fi/TCP 与 Light Sleep 保持原有启用方式。

## 1. Git 与基线

开始时工作区干净，fetch 后 research 与 origin/research 均为 `d3ba0d9ce511a74b32c1d55ae3189eb35fe6f9f9`，左右差异 0/0。阅读 INITIAL_CODE_REVIEW、PHASE1_DEVELOPMENT_REPORT、B1_RELIABLE_DELIVERY、HARDWARE_VALIDATION_PHASE1 及相关源码。重新执行 pytest：**363 passed，47.97 s**，不是引用历史数量。

main 与 origin/main 均保持 `167e307ad220d2df2b3405ede8ac8f47220c13e8`。所有开发和正常推送都在现有 research，没有 reset、force push 或合并。

代码提交：

| 提交 | 内容 |
|---|---|
| a01205c | FAILED 自动恢复、链路退避、存储隔离与 v2 格式、故障接口 |
| bd6d87f | receipt 容量并发保护、统计、归档、控制崩溃审计 |
| f84cd7c | C/Python 已确认基线、ACK 乱序与重启验证 |
| 5bc2bbf | 实验指标与原始事件统一测量窗口 |
| 110295e | 固定 IDF 的两种 ESP32-S3 CI 配置 |
| 329f8b2 | 修复容器内外路径差异造成的 manifest 归档遗漏 |

`results/research-phase1.1/validation/source_manifest.json` 保存实际验证源码的 SHA256。最终 pytest 在提交前运行。早期专项及本地整套实验为开发中间快照；最终代码上的 20+5 完整场景另外由 CI 实际重跑通过。实验原始 manifest 诚实保留当时 base HEAD 和 dirty 状态；不能把 manifest 的 base HEAD 当作修改后源码版本。最后的文档/证据提交位于上述代码提交之后，不更改功能源码。

## 2. 缺陷、最小修复与回归证据

| 文件 | 触发与原问题 | 实施与测试 | 结果 |
|---|---|---|---|
| b1_outbox.c / b1_retry.h / b1_network.c | 第五次超时进入 FAILED，同次启动不再发送；重连每秒重复 | 5 次快速尝试后 60→900 s 探测，原身份、按就绪 order 恢复，单条在途；虚拟时钟恢复、一小时离线、再次失败、FIFO、容量、倒退时钟和 20,000 次随机交错 | 修复；recovery-before.log 的 slot>=0 原断言失败，后续通过 |
| b1_outbox.c | save 返回 false 后复用相同 slot/order；后端可能已提交，或后续 commit 会发布此前 staged 数据 | 返回失败不计作 RAM active，不发送；quarantine 隔离槽位并消耗 order；重启从后端重新确认 | 修复；storage-before.log 原断言 last_slot!=first_slot 失败，后续通过 |
| b1_storage.c / b1_store_backend.c | erase 返回 NOT_FOUND 直接成功，可能只是上次失败 commit 留下的待提交删除 | remove=OK/MISSING 均必须 commit 成功才释放；失败时 active 保留；共同读/写/删除/提交接口供真实 NVS 和 Host 注入调用 | 修复与覆盖；pending erase + commit failure + retry 测试通过 |
| b1_checkpoint.c / b1_outbox.c | 原 v1 持久化依赖 native struct/padding；入队前 strcmp 使用未验证字符串 | 新写 v2 固定小端字段、长度与全帧 CRC；先验证再查重；v1 保留同 ABI 读取 | set/commit 前后失败、异常部分写、每个字节损坏、读失败、版本、重复恢复、最大 wire、sequence/order 边界测试通过 |
| offline_queue.py | 两个独立连接都先读取未满，再插入，突破 ledger 上限 | 容量/去重预检查前 BEGIN IMMEDIATE；outbox 入队同样取得写锁 | 修复；receipt-race-before.log 中限额 1 却入队 2，修复后仅 1 |
| offline_queue.py / gateway.py | 接近 receipt 上限缺少直接状态；持久化→ACK→决策→发命令之间缺少审计 | 80% 告警、logical_bytes/count/free/limit、进程拒绝计数；只读 SHA256 导出，无删除；receipt 同事务初始审计，决策/命令/发送/结果进度持久化 | gateway-before.log 缺少 API 的失败已修复；512 身份增长/云清理/重启/重复、ACK 窗口、planned/sent 崩溃、A2 旧样本通过 |
| gateway.py | 新增结果审计如遇写错误可能中断既有结果处理 | 审计失败保留 uncertain、计数并告警，继续原结果上传；发送前审计失败则阻止发送 | result-audit-before.log 复现结果任务终止，修复后通过 |
| b1_policy.c / b1_queue.c | policy 直接收到较旧确认会回退；队列重新初始化不清确认 mailbox | policy sequence/time 双检查；检测器故障恢复保留确认字段；boot 初始化清 mailbox，不伪造冷启动历史 | c-order-before.log 用原 policy 源码编译后断言失败；乱序、迟到、S/A 两种顺序、重复、两线程 2000 次重复 ACK、旧 boot 恢复通过 |
| adaptive_sense.py | core.update 在 upload intent 时自动记为 reported；mark_reported 使用确认时的 core.now | 撤销 core 的 intent 基线更新；异步确认使用采样 timestamp/sequence，拒绝旧/重复 sequence；故障恢复保留确认值 | 两个 Python 新用例修改前失败，修改后通过，原 C/Python parity 保留 |
| experiments/metrics.py / runner.py | shutdown await 后仍收集一条命令，原始事件比已冻结指标多 | 明确 freeze 测量窗口；原始事件、计数和延迟同一窗口，排除 teardown | 首次完整回归 374 passed/1 failed，确定 race；metrics-before.log 复现缺少 freeze，修复后完整回归通过 |

没有重写 AdaptiveSense 核心、Gateway 或协议，C 的 generation、TTL、重复执行和执行安全检查保留。

## 3. 实际测试与环境

环境：macOS arm64、Python 3.14.7（仓库 .venv）、Apple Clang；新 C Host 用例开启 ASan/UBSan，真实 cJSON、queue/policy/outbox/backend 源码参与。IDF 使用本机已安装 v5.4.4 / Python 3.13 工具环境；CI 使用独立容器。

| 实际命令（仓库根目录） | 结果 | 证据 |
|---|---|---|
| `.venv/bin/python -m pytest -q`（基线） | 363 passed | validation/baseline.log |
| `.venv/bin/python -m pytest -q`（最终） | **378 passed，0 failed，73.30 s** | validation/full-verified.log |
| `.venv/bin/python -m pytest -q -s tests/test_b1_retry_recovery.py` | 1 passed；一小时虚拟离线 11 次尝试（其中 6 次探测），保留 1 条 HIGH；20,000 次交错通过 | validation/retry-observations.log |
| `.venv/bin/python -m experiments.runner --all --output results/research-phase1.1/scenarios-final` | **20/20 PASS** | scenarios-final/suite_summary.json、每场景 raw、ground_truth、manifest、metrics |
| `.venv/bin/python -m experiments.edgefaultlab --edgefaultlab-root .external/edgefaultlab --output results/research-phase1.1/edgefaultlab` | **5/5 PASS** | edgefaultlab/suite_summary.json、独立进程 logs/events/report |
| `bash scripts/ci_build_b1.sh lab /tmp/b1-phase11-public-lab` | build / size / manifest 成功 | validation/firmware-public-lab.log、firmware-lab-manifest.json、firmware-lab-size.log |
| `bash scripts/ci_build_b1.sh light-sleep /tmp/b1-phase11-public-light` | build 成功且 PM/tickless/B1_LIGHT_SLEEP 都为 y | validation/firmware-public-light.log、firmware-light-sleep-manifest.json、firmware-light-sleep-size.log |

EdgeFaultLab 固定 revision `c7248239f456cc877114ca1e67c5949fb4a7b958`，5 个场景是 gateway_failover、server_outage、duplicate_control_command、stale_command、lost_command。新 pytest 数量为 15；C 单个 harness 内多种边界断言不冒充独立 pytest 项。

初次失败、首次修复通过、最终回归和两轮系统实验均保留在新目录，历史 phase1 数据未覆盖。`full-initial.log` / 各 before.log 的失败属于缺陷发现证据，不能解释为当前已知未修复失败。macOS 对三方 cJSON 的 sprintf 弃用警告在新的 sanitizer harness 中单独放宽 warning 类别；cJSON 未修改，其余编译 warning 仍 -Werror。ESP GCC 检查发现测试夹具 misleading indentation，已格式化并验证；最终 GitHub Linux GCC / ASan / UBSan 测试已实际通过。

## 4. 固件自动化

新增独立 firmware matrix：固定 `espressif/idf:v5.4.4`、ESP32-S3，lab 与 light-sleep。共用脚本检查 IDF 版本，使用独立 SDKCONFIG / build 目录，不读取开发者私人 sdkconfig；只用公开虚构 SSID 和文档用途 IP 保留实际网络路径的编译/链接。CI 仅上传 build/size/version 日志和 binary hash/size manifest，不上传完整配置、密钥或私人凭据。

早期空 SSID 的构建（291,088/309,280 字节）优化掉了网络路径，因此**不作为最终固件体积**。完整公开配置构建结果：

| profile | .bin 字节 | 链接 DIRAM 使用 / 区域总量 | .bss |
|---|---:|---:|---:|
| lab | 830928 | 209535 / 341760 | 102120 |
| light-sleep | 848512 | 216559 / 341760 | 102336 |

这些是链接器静态结果，不是实测峰值 heap/任务栈，也不是 Light Sleep 功耗。完整 hash 在 manifest。官方构建依据：[Espressif Docker 指南](https://github.com/espressif/esp-idf/blob/v5.4.4/docs/en/api-guides/tools/idf-docker-image.rst)、[SDKCONFIG_DEFAULTS 文档](https://github.com/espressif/esp-idf/blob/v5.4.4/docs/en/api-guides/build-system.rst)。

GitHub Actions 本次运行 [37767170403](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37767170403) 已实际完成 **success**。验证代码 SHA 为 `110295e4eabbfdd6423bfa1e5f751a16c24c332b`；Python 3.10、Python 3.12、firmware(lab)、firmware(light-sleep) 四个 job 全部 success。Python 3.10 为 378 passed / 56.52 s，Python 3.12 为 378 passed / 78.74 s；CI 在该精确提交上重跑 20 个系统场景与 5 个外部场景全部通过。状态 JSON、实际完整日志和下载的固件构建证据保存于 results/research-phase1.1；不引用历史 CI 成功。下载验证发现初次容器产物只包含 3 个日志而缺少 manifest，因此在 329f8b2 改为工作区相对产物路径，并重跑 CI 验证归档。最终运行 [37768007288](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37768007288) 在 `329f8b2f9325ac419a8a8b0ccf9ab854f55db360` **全部四个 job success**，两版 Python 各 378 passed、20 系统和 5 外部场景 PASS；下载后确认两种 firmware 产物各有 build.log、size.log、idf-version.log、manifest.json，大小与本地构建相同，hash 见 ci-firmware-final-*。首次完整软件场景原始证据另存 ci-software-110295e.tar.gz（hash 可核对），没有覆盖本地数据。最后文档/结果提交不改变已验证的功能代码。

## 5. 交付保证与限制

- HIGH 只有保存+提交成功才算 active；返回失败隔离 slot/order，不覆盖不确定数据。隔离减少可用槽位，需重新启动读取或将来经过验证的维护过程解决；不是自动擦除。删除确认失败保留并可用同身份重传。
- v2 格式为 `B1Q2`：44 字节头，version/header length/total length/CRC；order/acquired_ms 为 uint64 小端、sequence 为 uint32 小端，flags 与 boot/sample/wire 长度，随后非 NUL 字节数据。CRC32 的 12–15 字节计算时视为零；包含版本、长度和全部 payload。最大 4317 字节。native b1_record_t 仍用于 RAM 与同 ABI 的 v1 读取，v2 不持久化结构填充。
- 16 是逻辑 RAM 槽上限；默认共享 NVS 24 KiB，小于 16×最大 blob，更有 NVS 元数据/页开销。容量耗尽明确拒绝，不承诺所有新 HIGH 都能保存。
- Host 后端模拟 before/after commit、staged 与 committed、erase/read 错误。部分写模式故意让错误后端返回成功，验证重启检测损坏并保留存储；不能把这个恶意后端的成功返回当作真实 NVS 保证。实际 NVS 掉电页/GC 行为尚未复刻。
- 每条最多 5 次快速发送，随后 60→900 s 探测。非空 DATA 发起窗口 ≤30 s、≤80 次，窗口冷却 ≥60 s；空队列结束窗口。每 boot 有统计，没有永久耗尽总次数上限；全寿命总次数不是有限常数，频繁重启会补充快速预算。长期离线保留 HIGH，但无限离线/无限数据/磁盘损坏不保证最终交付。
- DATA 调度预算不是总射频开启或硬 deadline：DNS、Wi-Fi 驱动和阻塞 send 仍可能超过单次调用的软件预算，连接保持仍接收控制平面消息。没有声称实际省电、响应时间改善幅度或真实无线可靠率。
- receipts 和初始审计在 outbox 同事务提交后才 ACK。重复身份不 requeue、不重新决策。ledger 不按时间删除；export 是只读证据，不是身份退休协议或完整 DB 备份。统计逻辑字节不含 SQLite 索引、audit、WAL、页空闲；拒绝计数为本进程计数。
- 审计保存最后进度，不是完整不可变事件日志。RECEIVED/DECIDING 表示决策可能遗漏；COMMAND_PLANNED 表示计划产生、未证明已发送；DISPATCH_UNCERTAIN 表示可能已发送/执行。重启不自动重放这些命令，重复 B 上传不补做旧决策；可漏一次动作，不能声称恰好一次执行。新鲜可信样本才重新评估。
- A1/A2 各自 ledger 不构成跨网关一致性协议；持续非对称分区仍受现有 ownership 机制边界约束，没有证明全局恰好一次。旧 boot / 不明 age / age>5 s / 低序号样本保持历史用途。
- mailbox 合并只保留当前 boot 最大 sequence；通知尚未消费也不会倒退。旧 boot 的 ACK 可完成旧数据交付但不推进新 boot 算法。冷启动恢复交付记录，算法安全初始化；尚无完整 Deep Sleep 算法历史快照。
- Python SensorNode / MockFieldTransport 仍是原同步提交语义，不把其返回值称为 NVS 或无线 ACK。新增显式采样 timestamp/sequence 的 mark_reported API 供未来可靠异步调用。

## 6. 后续硬件与 Phase 2

待真实硬件：NVS set/commit/erase 的物理掉电和 GC、Flash 寿命与实际容量、任务栈峰值/动态内存、Wi-Fi/DNS 的板上阻塞时长、电流与 Light Sleep、E220 RF/分片实际交付率、Deep Sleep 时间连续性与唤醒、独立执行器物理超时关闭。具体新增步骤已写入 HARDWARE_VALIDATION_PHASE1.md，全程先用模拟 C，不自动启用真实执行器。

当前可继续 Phase 2 的**软件协议与状态快照准备**，不需要用户接硬件。E220 仍需设计适配长 JSON 的有界分片、boot/sample/ACK 身份与 CRC，不能直接沿用 EventGuard 的短帧身份宽度；Deep Sleep 仍需算法版本、状态 CRC、时间换算和安全降级。它们是本轮未实施的 P2 项，默认固件没有切换 Deep Sleep。本次已复现的软件 P0 缺陷已修复；真实设备发布条件尚未满足，也没有软件证据可以替代硬件验证。
