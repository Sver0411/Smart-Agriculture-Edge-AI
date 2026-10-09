# EventGuard-LoRa 版本复核与下一阶段复用边界

2026-10-08 实际获取并检查 [EventGuard-LoRa](https://github.com/Sver0411/EventGuard-LoRa)，固定 HEAD：`f7b6e44597abe958d7e9d6d481265d0fae33b749`。只读检出放在忽略的 `.external/eventguard-lora`；未复制其源文件到本项目。

源码确认可参考：

- `firmware/common/protocol.c/.h`：26 字节 DATA、13 字节 ACK、显式编码/解码、CRC16。其 sequence/sample_id 是 16 位，没有本项目所需的跨冷启动 boot_id 身份空间，不能直接作为新可靠交付契约使用。
- `firmware/common/e220.c`：原生 UART、AUX 等待/超时、模式引脚切换、启动读取寄存器并验证配置、串口/RX 诊断。
- `firmware/common/e220_stream_parser.c`：UART 流解析及异常恢复；应复用设计和对照测试而非为每次 UART read 假设一整个包。
- `firmware/main/main.c`：有限发送副本、ACK 超时、接收去重；ACK 表示实验接收，并没有本项目的 SQLite/NVS 持久化交接语义。

该仓库保留了真实 E220 实验和负面结果，包括未解决的后期接收停滞。其软件注入丢包结果不能转写成本项目的射频成功率；本轮未复跑其硬件实验。NORMAL/IMPORTANT/CRITICAL 与冗余预算可作为公平联合实验的对照，不是这里已经实现的新算法。

下一阶段应建立独立 transport/codec 层：保留当前 TCP adapter；把本项目逻辑身份、确认 scope、消息类型和版本映射到紧凑二进制帧；明确最大消息长度、分片索引/数量、重组期限/内存上限、CRC、重复/乱序/缺片、有限 ACK 重试及无线唤醒预算。不能把当前 1–2 KiB 的 JSON 当作它的 26 字节 DATA。

需要先通过 host codec/故障测试，再接 UART/E220，再实测 RF 和耗电。AdaptiveSense 不应依赖 UART/射频格式。`NOTICE.md` 是限制复用的权利声明，不是开放源码许可证；这里没有移植代码。后续复用源码时按本任务作者授权与实际范围保留出处、版本和权利说明。

状态：版本和实际源码已审查；E220 adapter、二进制编码/分片、RF/电流验证尚未实现/执行。
