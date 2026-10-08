# 第一阶段硬件验证操作表（全部待实测）

本轮未烧录、未进行物理断电、未接通执行器，也未测电流。先使用传感器和串口，C 保持模拟模式。

## 准备

- ESP32-S3、SHT30、USB 串口和可控的板级电源；功耗分析仪或带时间戳的分流电阻/采集器。
- 按实际开发板确认 3.3 V、GND、SDA、SCL；固件默认 GPIO8/9，SHT30 地址 0x44。用 menuconfig 核对，不能照旧实验接线而不探测。
- PC 启动文件缓存网关：`.venv/bin/python -m gateway.gateway --id A1 --host 0.0.0.0 --queue-db /absolute/path/new-A1.db`。A1 端口 9201；可增加 A2 9202。确保 LAN、防火墙和局域网地址正确。Server 可独立停止用于交接实验。
- 保存旧固件及 NVS 备份，核对分区不变。不要运行 erase-flash。损坏或不兼容记录必须先备份分析，不能删除来使测试通过。

## 构建/烧录

使用 ESP-IDF 5.4.4 的 Python 3.13 环境；系统 Python 3.14 不能直接激活本机已有 IDF 环境。

```sh
export PATH="/Users/mac/.espressif/python_env/idf5.4_py3.13_env/bin:$PATH"
. /Users/mac/esp/esp-idf/export.sh
cd firmware/b1
idf.py menuconfig
idf.py build
idf.py -p /dev/cu.YOUR_ESP32 flash monitor
```

设置 Wi-Fi SSID、密码、A1/A2 LAN 地址、lab profile；故障注入默认关闭。实际串口自行核对。烧录是你后续的硬件操作，不是本轮已经执行的命令。采集可使用 `scripts/capture_b1.py`（先看 --help），串口 stdout 应保存为新目录里的原始文件，勿覆盖历史 HW1。

## 逐项验证

1. 启动确认 SHT30_PROBE 和 B1_BEGIN。记录固件 SHA256、boot_id、GPIO、供电方式和实际 NVS 剩余容量。
2. 通过拔掉传感器或使用明确标记的测试注入制造 HIGH；看到入队后、发出前切断板级电源，恢复后核对相同 sample_id/message_id。串口采样日志不是 NVS 提交证据，需结合存储/交付计数及重启重发。
3. 网关已保存后屏蔽/丢弃 B 的 GATEWAY_OUTBOX ACK，再断电恢复，核对原 ID 重发且 cloud/history 只有一条。普通数据的 RAM 断电损失单独统计。
4. 停止网关、连续断网；观察 5 次每启动尝试后 FAILED 保留。恢复网络不保证 FAILED 自动再试，需保留证据后重启 B 开启新尝试窗口。该运行限制应计入实验结果。
5. 满载、NVS 满载、网关重启、相同数据重复和乱序；记录拒绝数量，确认旧 HIGH 未被驱逐。不要通过擦除 NVS 构造“恢复成功”。
6. Server 停止时，A 的本地持久化 ACK 应仍能出现；Server 恢复后，再观察 A→Server 的持久化和清理。这是两个不同的确认边界。
7. 采集包含启动、采样、Wi-Fi 建链、发送、ACK 等待、重试和空闲的完整电流曲线。相同供电、采样轨迹、信道条件、时长下比较 Light Sleep 开/关，记录负面结果。

## 数据格式

空白记录模板在 `results/research-phase1/hardware_measurement_template.csv`。每行保存仪器时间、run_id、阶段、电压、电流、持续时间、sample/message 身份、尝试/确认、NVS 占用及备注。外部功耗积分：`energy_j = Σ voltage_v * current_a * dt_s`，包括休眠与唤醒；单位可靠交付能耗只用已经达到声明确认层级的唯一样本计数作分母。没有仪器曲线时标记 not_measured，不能用上传次数换算“实测”。

Flash 写入寿命、真实 RF、Deep Sleep、C 物理独立超时关闭分别需要额外实验。本表没有给真实泵、阀、风机接线或自动通电流程。
