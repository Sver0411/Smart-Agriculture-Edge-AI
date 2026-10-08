# B1 可靠交付契约 v1

这是 research 的第一阶段实现说明。范围是物理 B1 的 Wi-Fi/TCP 集成链路与 A 的持久化交接；不是射频、低功耗或物理断电验证报告。

## 身份与兼容

B1 的 boot_id 包含设备 MAC、NVS 提交后的 64 位启动计数及 128 位随机量。正常重启改变 boot_id；已缓存记录保留原 boot_id。sequence 是本次启动内的 uint32 采样序号，所有采样均递增；达到 UINT32_MAX 后停止新增采样、输出 SEQUENCE_EXHAUSTED_REBOOT_REQUIRED，网络任务仍可交付缓存，人工重启后使用新 boot_id。不会回绕后复用身份。人工擦除 NVS 会破坏缓存和计数，不属于正常恢复。

- sample_id：`B1-{boot_id}-{sequence:08x}`。
- SENSOR_DATA message_id：`{sample_id}-S`；伴随 ALERT：`{sample_id}-A`。
- 入队时冻结序列化证据、产生时刻、策略版本、重要性。策略版本包含 profile 与配置哈希。
- transport 仅调整 target 和 delivery_age_ms；不改变逻辑证据与消息身份。
- 新消息使用现有 protocol_version=1、sequence 字段，payload 增加 `delivery_contract=gateway-durable-v1`，不增加消息类型。
- 旧 B/TCP 消息仍走原流程。旧网关不能产生新契约 ACK，新 B 会保留数据并耗尽有限重试，不会误判交付。
- Python SensorNode / SensorRuntime 与 MockFieldTransport 尚未迁移到这一契约；mock 返回只代表软件提交，不能引用为无线交付证据。

## 五层语义

| 观察 | 含义 | 能否清理 B 缓存 |
| --- | --- | --- |
| b1_queue_sample 返回 true | 已进入有界缓存；HIGH 在此之前完成 NVS 提交，NORMAL 只有 RAM | 否 |
| TCP send / transport sink 返回成功 | 提交至本地传输接口 | 否 |
| A 已解析消息 | 网关收到；尚不足以证明保存 | 否 |
| PERSISTED_ACK，scope=GATEWAY_OUTBOX，persisted=true，契约/来源/目标/identity 匹配 | A 的云端 outbox 与 sensor_receipts 已同事务提交，SQLite WAL + synchronous=FULL | 对该消息可以；同一样本的 SENSOR_DATA 和 ALERT 均确认后才清理样本 |
| SERVER→A PERSISTED_ACK | 服务器事务已经持久化；沿用现有实现 | 删除 A 的 outbox 行，不删除 A 的 sensor_receipts |

B 的 ACK 不代表服务器已经保存。A 的磁盘永久损毁不在单副本交接保证之内。SQLite/NVS 的物理掉电行为仍须实测。

## 有界缓存和故障处理

便携 C 状态机管理 16 个样本槽，NORMAL 最多 12，保留 4 个位置给 HIGH；HIGH 也可以使用其余空位。故障通知、环境事件及其恢复、控制阈值相关变化归为 HIGH。满载拒绝新样本，绝不驱逐已经入队的样本；拒绝身份和重要性写入 B1_DELIVERY 日志，local_queue_drops 是入队拒绝计数。

HIGH 在入队前写 NVS；清理时删除 NVS 后才释放 RAM 槽。持久化记录没有指针，带版本、CRC、身份与原始消息。NVS 采用实际消息长度的 blob，不为整个 4096 字节容量每次写满；没有重试计数写入。正常成功周期每条 HIGH 是一次保存、一次删除，NORMAL 不写样本 Flash。启动身份计数另有一次每启动写入。实际页擦写次数、掉电原子性和寿命未测量，不能把两次应用提交等同于两次物理 Flash 擦写。

默认 NVS 分区仍为原来的 24 KiB，与 Wi-Fi 等共享；16 是 RAM 槽上限，不保证能保存 16 条最大 HIGH。NVS 满时明确拒绝，原记录不删除；没有改变分区表或擦除现有 NVS。版本不兼容、CRC 错误、NVS 初始化失败均保留存储、停止启动并输出诊断。需要备份和人工迁移，不能自动清空故障证据。

状态：PENDING → IN_FLIGHT → RETRY_PENDING；匹配的全部 ACK 后成为 ACKNOWLEDGED（释放槽并累计计数）。每次启动最多 5 次传输尝试，ACK 等待 3 s，超时退避 1/2/4/8 s，之后 FAILED 停放、不删除；有效迟到 ACK 仍可释放。重启恢复为 PENDING，保留身份，但新的启动重新获得 5 次尝试。未实现跨启动的全寿命重试预算；频繁重启会增加尝试次数。普通 RAM 数据断电会丢失，且断电期间未采样的事件无法恢复。

就绪记录按原入队顺序发送，单条在途；重试退避中的记录不会阻塞其他就绪记录。没有声称实现高优先级回放或最优检测/交付延迟。伴随 ALERT 的确认也是独立消息；任意一条 ACK 丢失都保留整个样本，重启可重发已确认部分，A/Server 负责去重。

A 的 receipts 默认最多 100000 个身份，保存 SHA256 证据摘要。重复身份和相同证据重新 ACK，不再次排队或决策；身份相同但证据不同拒绝。receipt 已存在时，即便云端 outbox 已清理，重发仍不会产生第二条历史。达到上限拒绝新身份，旧身份继续可确认；不自动过期或删除去重凭据。生产长期运行仍需“确认 B 不再持有旧记录后归档”的可验证协议。逻辑容量不等于 WAL/物理磁盘硬上限。

## 报告基线和控制安全

保留 AdaptiveSense/SensorTrust 核心。B1 包装层撤销核心在 upload intent 时对报告基线的自动推进，只有可靠 ACK 完成后，由传感器任务读取确认样本并更新阈值、delta/heartbeat 基线。队列接受和 socket send 不更新确认基线。ACK 等待期间可能产生更多上传请求，这是可靠性与通信预算的真实权衡，尚未证明能耗收益。

旧 boot 的恢复样本、未知 age、age 超过 5 s、同一 boot 中序号落后于持久化 receipt 高水位的样本只能成为历史，不能驱动新控制。当前 boot 来自已接受注册；年龄由可信实验固件提供，不是密码学证明，也不替代未来 E220 接收窗口与认证。重复样本不重复决策；但保存数据与产生控制命令不是一个事务，崩溃可能漏掉本次决策，不保证恰好一次控制。

未调整 A ownership/takeover、C 执行保护、OfflineQueue 回放顺序、Server/AI 算法。双网关非对称分区、设备认证及物理关闭仍是独立待完成事项。

## 低功耗边界

当前仍是双任务、Wi-Fi modem power save 和可选自动 Light Sleep。Light Sleep 保留算法 RAM 上下文；冷启动只恢复关键交付记录，算法上下文重新初始化，不能将 NVS outbox 当作 AdaptiveSense/SensorTrust/owner 的完整快照。没有启用 Deep Sleep，没有引入 E220 radio sleep。

下一阶段应实现“唤醒→恢复明确状态→采样→可信检查→调度/控制相关性→通信/确认→保存→关闭外设→休眠”，先固定单调时间换算、算法版本和 owner/session 恢复契约，再决定 RTC/NVS 存储。现阶段构建成功和发送次数都不是实际省电证据。
