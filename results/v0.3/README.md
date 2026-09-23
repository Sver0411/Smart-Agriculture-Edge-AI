# v0.3 hardware results

No formal v0.3 measurement has been recorded yet. Results must come from a clean measurement commit and a finite, captured hardware run. A real board and SHT30 have been detected during development, but that does not establish registration, delivery, failover, or the four required HW scenarios.

Store sanitized serial, gateway and server logs under `raw/`; derive CSV and figures from those logs. Record board revision, physical/configured/runtime flash and PSRAM, ESP-IDF/compiler, source commits, config hash, heap, app size, failover intervals, and sample counts. Never commit Wi-Fi credentials, MAC/USB serial, private LAN hosts, or unsanitized paths.
