# Physical B1 firmware

ESP32-S3 / ESP-IDF 5.4.4. This firmware reads a real SHT30 at I²C address `0x44`, probes the bus on boot, runs one independent SensorTrust C11 context per channel, and applies the unmodified AdaptiveSense C detector and scheduler. Temperature and humidity are the only fields sent. No synthetic readings or soil values are generated.

## Configure and build

Use `idf.py menuconfig` → **Physical B1 configuration** to set Wi-Fi credentials and the PC's LAN host/port for A1 and A2. The generated `sdkconfig` is ignored by Git. The defaults contain no credentials or private LAN address. The gateways must listen on a LAN interface, for example `python3 -m gateway.gateway --id A1 --host 0.0.0.0`; the server and peer can stay on localhost. Keep the host firewall configured for ports 9201 and 9202.

```sh
cd firmware/b1
idf.py build
idf.py -p /dev/cu.YOUR_ESP32 flash monitor
```

Probe the physical address and pins from the `B1_NET SHT30_PROBE` line before treating samples as evidence. `B1_SAMPLE` prints the actual monotonic sample timestamp, read status, values, health score/flags, scheduler score/mode, next interval, and reason. `B1_NET` reports registration and disconnect events. `B1_STATS` prints bounded-queue drops and network counters every 10 seconds. Capture serial output to a local file for analysis.

With `LAB_MODE` enabled, the interval ladder is accelerated to 1–5 seconds; it does not represent deployment timing. The normal profile uses the upstream 5–60 second interval ladder. Humidity SensorTrust thresholds are integration settings and have not received the standalone SensorTrust hardware evaluation. SensorTrust flags can be DEGRADED without making the whole node unusable; a FAULT on either required channel sets `usable_for_control=false`. A test-only Kconfig option injects 150 °C after the real SHT30 read for samples 10–14, marks them `test_injected`, and is disabled by default.

Sensor readings are queued in a fixed 16-entry volatile FreeRTOS queue; when full, the oldest entry is dropped. Network and sensor run in separate tasks. The network task keeps reading the socket, registers with A1 then A2 on failure, handles `NODE_STATUS`, and refuses a generation below the highest accepted during this boot. The message ID is a random boot ID plus a monotonic counter. The envelope `timestamp` is uptime seconds and `timestamp_source=device_uptime`; the gateway assigns its receipt wall time. Generation and the telemetry queue are not persisted across reboot.

See `third_party/*/SOURCE.md` for exact upstream commits and licenses.
