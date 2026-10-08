# Physical B1 firmware

ESP32-S3 / ESP-IDF 5.4.4. This firmware reads a real SHT30 at I²C address `0x44`, probes the bus on boot, runs one independent SensorTrust C11 context per channel, and applies the adapted AdaptiveSense C detector and scheduler with shared JSON profile parameters. Temperature and humidity are the only fields sent. No synthetic readings or soil values are generated.

## Configure and build

Use `idf.py menuconfig` → **Physical B1 configuration** to set Wi-Fi credentials and the PC's LAN host/port for A1 and A2. The generated `sdkconfig` is ignored by Git. The defaults contain no credentials or private LAN address. The gateways must listen on a LAN interface, for example `python3 -m gateway.gateway --id A1 --host 0.0.0.0`; the server and peer can stay on localhost. Keep the host firewall configured for ports 9201 and 9202.

```sh
cd firmware/b1
idf.py build
idf.py -p /dev/cu.YOUR_ESP32 flash monitor
```

Probe the physical address and pins from the `B1_NET SHT30_PROBE` line before treating samples as evidence. `B1_SAMPLE` prints the actual monotonic sample timestamp, read status, values, health score/flags, scheduler score/mode, next interval, and reason. `B1_NET` reports registration and disconnect events. `B1_STATS` prints bounded-queue drops and network counters every 10 seconds. Capture serial output to a local file for analysis.

## Integration transport and timing

Wi-Fi/TCP is **Development / Integration Transport**, with real hardware integration value; it is not the final battery-powered field network. The target B↔A and A↔C transport is ESP32-S3 + E220 LoRa. There is no real E220 adapter or RF validation in this firmware yet.

Kconfig explicitly selects **lab** (default 1–5 s), **simulation** (5–60 s), or **deployment** (STABLE 20→40 min, ACTIVE 10→5 min, ALERT 5→2→1 min). The deployment heartbeat upload is 6 h. These are engineering defaults needing crop/noise/battery/field calibration. Selecting deployment timing still uses the integration Wi-Fi adapter; it does not turn this into a validated field runtime.

`config/profiles/*.json` and `config/physical_b1.json` are the source of policy parameters:

```sh
python3 scripts/generate_b1_profiles.py
python3 scripts/generate_b1_profiles.py --check
```

Run those commands from the repository root. Host tests check generated-header freshness and compare Python/C state, next interval, event and upload for shared traces. Temperature/humidity SensorTrust parameters retain the historical hardware-study/integration distinction. Soil/light are disabled, never fabricated. The test-only 150 °C injection remains disabled by default.

## Sampling, sending and power boundary

Every read updates local trust/scheduling. `upload_requested=false` never enters the 16-entry queue and also cannot invoke the transport send sink. Needed uploads include first valid sample, state/interval changes, event onset/recovery, meaningful delta, fault-signature changes/recovery and low-frequency heartbeat/reminder. Identical sustained faults do not upload every sample. The bounded volatile queue still drops the oldest admitted upload when full; failed sends may be requeued, without durable node-side delivery guarantees.

`b1_types.h` / `b1_policy` have no RTOS/socket dependency; `b1_telemetry.c` builds payloads/envelopes; `b1_transport.h` defines a sink; `b1_network.c` is the TCP adapter. The sensor task retains its static algorithm context between waits. The network task registers with a candidate Gateway, validates owner/generation (including same-epoch competition), and handles NODE_STATUS. Device timestamps are uptime; Gateway uses receipt wall time. B's generation remains per-boot, with NVS retention pending.

Wi-Fi modem power save is explicit. Optional `B1_LIGHT_SLEEP` uses IDF automatic light sleep; enable PM_ENABLE and FREERTOS_USE_TICKLESS_IDLE first. It preserves RAM contexts and is disabled by default. An associated TCP/Wi-Fi session can still wake often; full on-demand radio sleep requires the E220 adapter. Deep sleep is not enabled: RTC/NVS restoration must first preserve SensorTrust history, EMA, hysteresis/ladder, event duration, last-upload validity/time and owner/epoch, with a monotonic-clock translation contract. No current or battery lifetime has been measured for this change.

`B1_SAMPLE` now logs upload_requested and detected_event; untrusted environmental score is JSON null. `B1_STATS` counts sensor_samples independently of successful sensor_messages. Historical HW1 logs remain unchanged and do not validate this new firmware's upload/power behavior. This round's ESP-IDF build evidence is separate from flashing or hardware tests; see [deployment report](../../docs/DEPLOYMENT_REALIGNMENT_REPORT.md).

Final semantic patch: trusted temperature crossings of the local ventilation threshold (both directions) and profile margin entry request immediate upload. `sampling.upload_reasons` lists all triggers. The reference advances on successful queue admission, not policy evaluation; a rejected admission leaves the crossing pending. B1 has no soil channel. Threshold config is shared with Python, with a lightweight C setter for a future local policy exchange; no E220 policy protocol is implemented. See [five-patch evidence](../../results/final-five-patches/README.md).

See `third_party/*/SOURCE.md` for exact upstream commits and licenses.
