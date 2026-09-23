# v0.3 physical B1 evidence — HW1 only

Measurement code commit: `562304ce87fb96068583227744a59b395a1697c8`. The capture script checked `git status --porcelain` before recording and stored `git_dirty=false`. The ESP-IDF app descriptor identifies `v0.2-1-g562304c`; the built image was flashed and verified before capture. Firmware config SHA-256 and upstream source commits are in `hardware_metadata.json`. This directory is the later results commit.

## Hardware and read path

An ESP32-S3 QFN56 rev v0.2 was detected on the USB serial port. Physical flash is 16 MiB; the app was configured for 2 MiB. The package reports 8 MiB PSRAM, but PSRAM is disabled and runtime capacity is 0. The exact development-board model was not identified. ESP-IDF is v5.4.4 with xtensa-esp-elf-gcc 14.2.0.

The new firmware's boot-time I²C probe succeeded at SHT30 address `0x44` on SDA GPIO8 and SCL GPIO9. The 30 captured readings all passed the SHT30 CRC check; no synthetic fallback exists. Temperature ranged **26.789–26.861 °C**, humidity **55.169–55.476 %RH**, with **0 physical read failures**. BH1750 was not tested, and no light or soil-moisture value was generated.

## Local algorithms and timing

Both SensorTrust contexts reported `HEALTHY` on all 30 samples; no fault was injected in this run. Temperature uses the configuration from the standalone SensorTrust hardware study. Humidity thresholds are integration settings and have **not** been independently validated in that study.

AdaptiveSense selected next intervals of 2 s (2 samples), 4 s (2), and 5 s (26). Observed timestamp differences were approximately 2.04 s, 4.04 s, and 5.04 s; SHT30 read time contributes to the difference. All decisions were `STABLE`: the 2→4→5 s transition is the upstream scheduler's startup ladder. There was no physical perturbation or injected data, so this run does **not** demonstrate an environment-triggered `ACTIVE` or `ALERT` transition. The accelerated laboratory intervals are not deployment intervals. Energy and current were not measured.

App binary: 244,528 bytes. `idf.py size` reported 70,559/341,760 bytes DIRAM and 16,383/16,384 bytes IRAM in its memory-type summary. Boot free heap was 366,384 bytes, and the minimum printed during capture was 350,908 bytes. These are build/runtime figures, not a power measurement.

## Network and outstanding acceptance work

Wi-Fi credentials and LAN gateway hosts were intentionally absent, so the firmware printed `WIFI_UNCONFIGURED`. The captured stats report zero Wi-Fi connections, registrations, sensor messages, alerts, and failovers. The 16-entry volatile queue filled during this offline run: the last emitted stats at sample 28 recorded 12 drops. By sample 30, 14 drops are implied by 30 enqueues and zero dequeue, but that final count was not directly logged. These drops reflect the deliberately unconfigured network, not a demonstrated failover.

HW2 register/upload, HW3 A1→A2 failover, HW4 fault/ALERT-to-Server, and an environment-triggered AdaptiveSense response remain **unverified**. No gateway or server logs/CSV are presented as hardware evidence. Python protocol compatibility and host C tests are separate automated checks. v0.3 cannot be declared complete until the network and fault scenarios are run with a configured, reachable Wi-Fi/LAN setup.

## Files

- `raw/b1_serial.log`: sanitized serial capture (107 lines). The logger redacts MAC, LAN address, local username path and USB port patterns before writing.
- `physical_samples.csv`: all 30 samples, timestamps, channel states, scores and next intervals.
- `network_events.csv`: boot probe and unconfigured-network event; no gateway events.
- `hardware_metadata.json`: measurement provenance and physical/configured/runtime hardware distinctions.
- `build_size.json`: binary and section sizes from the measurement build.

This is a results record for an incomplete v0.3 acceptance, not a claim that real failover has already been demonstrated.
