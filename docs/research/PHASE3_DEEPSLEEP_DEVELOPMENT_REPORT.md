# Phase 3 — Portable algorithm snapshot and controlled Deep Sleep

Checkpoint C is based on Phase 2 `37c0cc4`. This implements actual ESP-IDF Deep Sleep execution, but the physical board and E220 were unavailable. Current, battery lifetime, RTC retention on a board, module wake/shutdown timing and field reliability remain pending. The engineering boundary is visible in the default configuration and logs.

## State classification

| State | Storage / restore behavior |
|---|---|
| UART/I2C handles, task state, receiver slots, peer session nonce | Reinitialize each boot |
| SensorTrust health/history/last-valid/spike/drift/missing counters | Versioned RTC algorithm snapshot |
| AdaptiveSense 4-channel history, EMA, event debounce, hysteresis state, interval/rung counters | Same RTC snapshot, including all history slots |
| Confirmed upload values/time/sequence, fault signature, control threshold/margin | Same snapshot; intent never advances confirmation |
| HIGH outbox records and original full identities | Existing NVS v2 checkpoint, unchanged format and migration tests |
| Highest observed owner/generation | Separate 16-byte CRC-protected NVS journal, committed only on changes |
| Boot counter ranges | Existing NVS u64 boot_counter reserves 256 values; RTC lease consumes them without one Flash write per wake |
| Runtime boot identity | New on every wake; counters prevent reuse and random nonce supplements identity |
| Missing/corrupt RTC or unknown elapsed time | Safely rebuild algorithm baseline; keep HIGH NVS and generation |
| Current ownership authorization | Gateway registration must confirm before business transmission |

Ordinary startup still uses the original TCP/LoRa tasks. Deep Sleep is opt-in and defaults off. RTC is volatile across power loss. NVS is not populated with every ordinary algorithm sample.

## Snapshot schema 1

`b1_snapshot.c/h` is portable C11; no ESP-IDF dependency. The serialized record is **5070 bytes** with current 64-slot limits. A 6000-byte cap reserves headroom. The 16-byte header contains magic `B1AS`, u16 version, u16 total length, configuration CRC32 and full-record CRC32 (CRC field zeroed during calculation). Integer fields use explicit u8/u16/u32/u64 little-endian widths; floats use IEEE754 binary32/binary64. There are no pointers or structure padding on wire.

The configuration fingerprint serializes every SensorTrust/CD/AS mathematical parameter, ladder lengths/contents/confirmation counts and timing profile. Dynamic control threshold/margin are state fields. A mismatched profile or unknown version is rejected rather than silently interpreted. This first algorithm schema has no historical schema to migrate; unknown schemas degrade safely. Existing NVS v1→v2 outbox migration remains tested independently.

Each SensorTrust channel includes all 64 `(value,timestamp_ms)` slots, ring capacity/count/head, initialized flag, invalid count, last-valid observation/time, pending spike reference/count, drift streak/direction and latest health/flags/score. The detector includes four full 64-slot `(time,value)` arrays with lengths/capacities, EMA validity/value, previous timestamp flags, event start/active and truncation flag. The scheduler includes state/interval, all ladder positions/rung counts, sample count, actual confirmed-upload time/values/validity and previous event/interval state. Policy fields include fault state/signature/reminder time, trust transition, threshold/margin/report value and confirmed sequence/time. Identity stores previous boot, sequence, highest generation/owner, saved logical time, planned sleep and counter lease.

Decode validates bounds, active timestamps, counters, finite values, CRC and profile before committing outputs. It rebinds cfg pointers to the destination policy. It rejects an epoch below the durable minimum. Encode rejects inconsistent state; corrupt restore never clears an outbox. CRC detects corruption; it does not authenticate retained state.

## Time and confirmation

A valid trusted elapsed interval resumes a **logical algorithm clock** using saved logical time plus measured elapsed. No reset esp_timer value is subtracted from a previous boot timestamp. The portable restore oracle supplies known elapsed time. Firmware's weak `b1_deep_elapsed` provider defaults to false; a commissioned/calibrated board source can supply measured elapsed plus an error bound. The planned sleep interval is never treated as a measurement. The maximum accepted error is configurable.

With the default provider, a timer wake restores sequence/epoch/provenance but logs `B1_RESTORE_TIME_UNKNOWN` and initializes a safe new algorithm baseline. This controlled mode does not claim full board-level temporal continuity. It may request an initial upload each wake until a trustworthy elapsed-time source is commissioned; that behavior is explicit, not described as an energy improvement.

Every wake receives a new boot ID. Frozen HIGH records keep their old boot/sample/message IDs; send age is UNKNOWN and the gateway may save them as history but cannot authorize control. A late old-boot ACK may retire old HIGH evidence and cannot advance the current policy's confirmed baseline. Current-boot records use runtime acquisition age on wire; only a validated durable ACK is translated back to logical policy time. Sequence advances across valid RTC wakes; exhaustion halts with a conservative backoff instead of wrapping.

## Real firmware path

`deep-sleep-experimental` enables B1's real E220 path and creates a dedicated 24 KiB task. NVS HIGH restore runs at startup before formal sampling; the task checks reset/wake cause, validates RTC before any clock-provider call, restores policy before physical SHT30 acquisition, obtains a new identity, confirms epoch, samples/evaluates, conditionally communicates with a bounded ACK window, consumes confirmation, saves state, shuts down I2C/UART, holds radio M0/M1 in mode 3, arms a timer and calls `esp_deep_sleep_start`.

Communication is bounded by the configured window plus finite driver initialization/shutdown timeouts. Failures are logged. Storage/epoch/snapshot/peripheral shutdown failure enters an awake 60-second backoff loop with no rapid wake-reset cycle; HIGH evidence is preserved. Firmware never commands physical actuators. Board pin compatibility, radio mode-3 current and output hold behavior still require measurements.

The [ESP-IDF v5.4.4 sleep documentation](https://github.com/espressif/esp-idf/blob/v5.4.4/docs/en/api-reference/system/sleep_modes.rst) is the platform reference. RTC retention, GPIO hold and peripheral shutdown must be checked on the commissioned ESP32-S3 board.

## Executed evidence

`experiments.snapshot_harness` runs the real C SensorTrust/AdaptiveSense/B1 policy under ASan/UBSan. Seven 400-sample traces compare each restored state/decision with an uninterrupted oracle, yielding 2800 matching observations. The event trace produced 40 active-event observations and six recoveries; RANGE/MISSING/SPIKE/STUCK/DRIFT traces exercise their actual history/counters. Raw input, health, state, upload reason and oracle-match events are retained.

All 17 snapshot cases passed: healthy/event/range/missing/stuck/drift/spike continuity, unknown time, sequence exhaustion, epoch CRC/rollback, every truncated byte length, per-byte corruption, unknown schema, incompatible profile, invalid capacity, clock overflow and counter lease. The lease test consumes 256 unique counters, renews a range, abandons a range after cold boot and rejects counter overflow.

Existing outbox tests cover NVS corruption/migration, uncertain save, ACK ordering/loss, HIGH retry/restart and old-boot confirmation rejection. Complete Python regressions and all four public firmware profiles are logged in `results/research-phase3/validation`; precise final totals/hashes are appended after execution. Initial compiler format failure and the interrupted resource-contended regression remain retained.

The first successful Deep Sleep link used 6032 bytes RTC SLOW and 132 bytes RTC FAST, within the reported 8192-byte regions. That is link-time capacity evidence, not real RTC retention or current measurement.

## Remaining work

P1 board gate: commission a trusted elapsed-time provider and quantify its error; measure wake reason/retention/GPIO/radio/AUX timing under resets and power cuts; measure sensor/radio idle current and full wake-window energy. P2: evaluate snapshot wear/capacity on actual NVS, NORMAL-data retention policy, real RF MTU/retry optimization and watchdog recovery under injected peripheral faults. Generic hostile radio authentication and arbitrary asymmetric partition consensus remain separate deployment requirements. No measured energy saving is claimed.

Final Checkpoint C results: Python 3.10 **513 passed / 102.18 s**; Python 3.12 **513 passed / 95.70 s**. Original TCP 20/20 and EdgeFaultLab 5/5 passed. All four IDF v5.4.4 profiles passed; per-profile binary SHA256/size and exact source hashes are recorded in the validation manifests. Deep Sleep binary is 350384 bytes, SHA256 `a128342bbcbfc1086696d86a5f744be7649c3a7607bac98a5b5a4f7b12e9c07a`. Hardware measurement items remain pending.
