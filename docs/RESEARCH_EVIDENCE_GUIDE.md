# Research Evidence Guide

An English reading guide to the original reports and raw evidence. Reviewed on **2026-10-08**, against main [`31d90ec`](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/commit/31d90ec3d87f5bd7a3ac4386d2746f30bd081475) and research [`d909aa4`](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/commit/d909aa4a39e8374d4f356aca2db62473889236b1). Each section identifies the source actually evaluated, which can predate those documentation snapshots.

Main and [research](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/tree/research) are separate development lines. Research-only delivery changes are unmerged. Python versions repeat the same suite; test counts are not added across environments or phases. All results below are existing records, not measurements rerun for this documentation update. Original reports, failed attempts, and logs remain unchanged.

[Main software](#a-main-branch-software-integration) · [Physical sensing](#b-physical-esp32-s3--sht30-evidence) · [Research Phase 1](#c-research-branch--phase-1) · [Research Phase 1.1](#d-research-branch--phase-11) · [README](../README.md)

## A. Main Branch Software Integration

**Objective.** Evaluate the seven-role, two-zone software prototype under communication and process faults while preserving local control independently of cloud availability. This is the 2026-10-08 main integration acceptance, with functional source `f204ad9` and archived CI at `002e26a`.

**Implementation / Method.** Server, A1/A2, B1/B2, and C1/C2 communicate over host TCP with simulated sensing and actuation. Tests exercise SensorTrust, AdaptiveSense, ownership, guarded commands, durable outbox replay, and transactional receipts. The review also fixes unsafe checkpoint fallback, an unbounded runtime command-ID set, and invalid replay intervals.

**Verified Results.** Each local Python 3.10/3.12/3.14 suite passed **350 tests**. All **20 internal scenarios** and **5 external EdgeFaultLab scenarios** passed. Faults include loss, duplication, delay, reordering, gateway failure/recovery, server outage, stale commands, and unavailable controllers. [CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37734482845) repeated the 350-test suite on Python 3.10/3.12 and the 20+5 scenarios on Python 3.12.

**Evidence and Reproducibility.** Read the [original integration review](BRANCH_INTEGRATION_REVIEW.md), [acceptance commands/environment](../results/main-integration-review/validation/acceptance.json), and [source hashes](../results/main-integration-review/validation/source-manifest.json). Inspect the [internal](../results/main-integration-review/software-scenarios/suite_summary.json) and [external](../results/main-integration-review/edgefaultlab/suite_summary.json) summaries, per-scenario raw events, and [archived CI metadata](../results/main-integration-review/validation/main-ci.json). The [Quick Start](../README.md#quick-start) uses fresh output directories and the reviewed external revision.

**Limitations.** This acceptance used no physical hardware. It does not establish RF performance, real-actuator safety, arbitrary-partition consensus, energy savings, or agricultural effectiveness. Synthetic model checks validate software workflows.

## B. Physical ESP32-S3 / SHT30 Evidence

**Objective.** Establish a limited physical B1 sensing record, labelled **HW1**. Measurement source is `562304ce87fb96068583227744a59b395a1697c8` (code dated 2026-09-23), with `git_dirty=false`. This historical firmware is distinct from subsequent upload and reliability revisions.

**Implementation / Method.** An ESP32-S3 QFN56 revision v0.2 reads an SHT30 at I²C address `0x44`, using SDA GPIO8 and SCL GPIO9. The exact development-board model was not identified. ESP-IDF v5.4.4 firmware records physical temperature/humidity, per-channel SensorTrust state, and AdaptiveSense decisions. No synthetic fallback or soil/light readings were used.

**Verified Results.** All **30 readings passed CRC**, with **zero physical read failures**. Temperature ranged 26.789–26.861 °C; humidity ranged 55.169–55.476 %RH. Both health contexts remained HEALTHY. All scheduler decisions were STABLE; the 2→4→5-second startup ladder was observed. This is an accelerated laboratory schedule, not deployment timing or evidence of a response to environmental events.

**Evidence and Reproducibility.** Start with the [HW1 report](../results/v0.3/README.md), [physical samples](../results/v0.3/physical_samples.csv), [sanitized serial capture](../results/v0.3/raw/b1_serial.log), and [hardware provenance](../results/v0.3/hardware_metadata.json). The [firmware README](../firmware/b1/README.md) explains the current driver, configuration, and build boundaries; reproduce historical measurements using the recorded source/configuration rather than assuming current firmware is identical.

**Limitations.** Wi-Fi was unconfigured; no gateway uploads or failover were observed. No faults were injected, and humidity thresholds lack independent calibration. Wireless control, E220, real actuators, current, energy, battery life, and a complete field deployment remain unverified. Build sizes and heap observations are not power measurements.

## C. Research Branch — Phase 1

**Objective.** Add bounded critical-data delivery to B1 without treating a successful TCP send as durable receipt. This is the **historical 2026-10-08 Phase 1** evaluation of `827cc393af34a1921613e9239785a625f191eafb`, including gateway changes at `ffb5615`; Phase 1.1 subsequently hardens its failure behavior.

**Implementation / Method.** A portable C outbox freezes logical identities and serialized messages, keeps HIGH records through a firmware NVS backend, and rejects admission rather than evicting pending critical data. Gateway receipt and outbox admission share a transaction. Upload baselines advance after a matching gateway durable acknowledgement; stale restored samples remain history-only. Existing Wi-Fi/TCP transport is retained.

**Verified Results.** The suite grew from 350 to **363 passing tests**; **20/20 internal scenarios** passed. A host C-serializer/TCP fixture dropped the first gateway ACK, then retried after cloud cleanup: final history contained **two samples and one alert**, without duplicate samples. ESP-IDF v5.4.4 compiled the ESP32-S3 firmware; it was not flashed in this evaluation.

**Evidence and Reproducibility.** Read the pinned [original report](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/docs/research/PHASE1_DEVELOPMENT_REPORT.md), [evidence index](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/results/research-phase1/README.md), and [manifest](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/results/research-phase1/manifest.json). They identify raw wire events, final regression logs, seed-42 scenarios, source hashes, and actual dirty-state provenance. Reproduction requires the research source and its environment.

**Limitations.** NORMAL records are volatile; NVS can fill before all 16 logical slots are used. Historical FAILED records could stall until reboot; five attempts were a per-boot budget. Host storage callbacks do not validate physical power cuts or Flash wear. E220, deep-sleep continuity, energy, and actuators were not tested.

## D. Research Branch — Phase 1.1

**Objective.** Harden Phase 1's persistence, retry, and acknowledgement behavior under storage failures, restart, and concurrency. The latest functional verification recorded at the reviewed research snapshot is `329f8b2f9325ac419a8a8b0ccf9ab854f55db360`, dated 2026-10-08; later documentation commits do not supply new measurements.

**Implementation / Method.** Failed records receive probes with 60–900-second backoff after five fast attempts. Uncertain saves quarantine slots; erase requires committed deletion. Portable v2 checkpoints use explicit lengths, little-endian fields, and CRC. Gateway write locking protects receipt capacity; durable audits track decision/dispatch uncertainty. Ordered acknowledgements preserve sample-time upload baselines, and metrics share one observation window.

**Verified Results.** Final local regression passed **378 tests**. A virtual-hour outage used 11 attempts, including six probes, and retained the HIGH record; 20,000 randomized state interleavings passed. [Final CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37768007288) passed 378 tests per Python version, 20 internal and 5 external scenarios, plus ESP-IDF v5.4.4 lab/light-sleep builds. Both firmware artifacts contain build, size, version, and manifest records.

**Evidence and Reproducibility.** The pinned [original report](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/docs/research/PHASE1_1_DEVELOPMENT_REPORT.md), [evidence index](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/results/research-phase1.1/README.md), and [source manifest](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/blob/d909aa4a39e8374d4f356aca2db62473889236b1/results/research-phase1.1/validation/source_manifest.json) distinguish development snapshots from exact-commit CI. Use their pytest, scenario, and public firmware-build commands on research. Preserved before-fix failures document defects, not unresolved final regressions.

**Limitations.** No board, physical power-cut, RF, or energy experiment occurred. Quarantine reduces capacity; indefinite outages do not guarantee delivery. Audits preserve uncertainty rather than exactly-once actuation. Full deep-sleep algorithm snapshots, E220 integration, physical NVS behavior, and actuator safety remain pending; these mechanisms are not merged into main.
