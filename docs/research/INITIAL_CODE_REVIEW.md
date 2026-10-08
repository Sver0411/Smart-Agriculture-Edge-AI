# Research branch — initial source audit and actionable backlog

- Audited on: 2026-10-08
- Repository: Sver0411/Smart-Agriculture-Edge-AI
- **Base `main` commit: `167e307ad220d2df2b3405ede8ac8f47220c13e8`**
- Scope: source-level inspection of the newly created `research` branch. **No local test execution, ESP-IDF build, radio measurements, or live hardware verification was performed in this audit.**
- Safety principle: main remains untouched; do not claim an implemented design or host simulation is verified hardware operation.

## Verified findings and proposed actions

| Priority | Source evidence | What the current code actually does | Recommended research implementation & acceptance evidence |
| --- | --- | --- | --- |
| P0 | `firmware/b1/main/b1_queue.c:3-11`, `firmware/b1/main/main.c:16-21` | B1 buffers upload-requested samples in a **volatile 16-entry FreeRTOS queue**, evicts the oldest when full, and loses pending data on reset. | Define explicit admission/eviction policy per importance; durable or wear-aware bounded storage for critical acquired samples; sequence/boot IDs; queue saturation + forced reset tests. Clearly report unrecoverable unsampled intervals. |
| P0 | `firmware/b1/main/b1_network.c:218-241`, `firmware/b1/main/b1_telemetry.c`, `sensor_node/runtime.py:36-48` | A successful `send`/sink return advances reporting or removes the sample from the queue, **without a documented durable gateway receipt**. A TCP write only means bytes were submitted locally. | Separate radio/send acceptance, gateway receipt ACK and cloud persisted ACK. Preserve the logical identity across retries; test lost ACK, mid-send disconnect, deduplication and bounded retries before advancing a confirmed-delivery baseline. Do not treat a mock send as end-to-end delivery. |
| P0 | `firmware/b1/main/main.c:19-24`, `firmware/b1/main/b1_sensor.c`, `firmware/b1/main/b1_runtime.c:6-16`, `common/field_transport.py:1-20` | Actual B1 runs separate sensor/network tasks; opt-in automatic **light sleep** retains RAM, and the E220 adapter is still missing. It is not a completed MCU deep-sleep/radio duty-cycle implementation. | Integrate a minimal, recoverable wake→read→evaluate→send/ACK→sleep firmware state machine with versioned state restoration; measure real current traces. Do not erase runtime contexts on reboot without conversion/version checks. Test cycle continuity and sleep/fault behavior before claiming battery-life improvements. |
| P0 | `controller_node/controller_node.py:229-315`, `controller_node/recent_commands.py` | Durable intent/command dedup exists, but actuation is simulated using `asyncio.sleep`; a physical valve or pump failure-safe pathway is not yet implemented. | Create hardware abstraction and independent maximum-on-time cut-off design; default outputs to safe state; test reset-while-on, stuck output, duplicate/expired/spoofed command and power failure using a safe test load. Cryptographic transport/device authentication remains necessary. |
| P1 | `gateway/ownership.py:64-106` | Timeout/epoch takeover and peer observation exist. The module docstring overstates sufficiency for all two-gateway situations; an asymmetric partition can still produce competing ownership beliefs. | Define a fail-closed partition policy, authenticated ownership/lease or explicit arbitration assumptions, and run asymmetric-partition/recovery tests. Never claim generic split-brain freedom from epoch counters alone. |
| P1 | `gateway/offline_queue.py:29-41,101-137` | HIGH/NORMAL is **admission reserve**, not replay priority: `peek()` always selects `ORDER BY queue_id` (global FIFO). Logical payload limits are not WAL/disk limits. | Benchmark critical-message recovery latency under large normal backlog; only add bounded priority replay if preserving fairness, ordering and persisted-ACK semantics. Test full disk, invalid row quarantine and restart. |
| P1 | `sensor_node/control_relevance.py:13-46`, `docs/DEPLOYMENT_SEMANTICS.md` | Local control-relevance margins and thresholds can be set, but actual field policy-version synchronization is not implemented. If A changes its control policy, B might use stale thresholds. | Introduce explicit policy version/expiry negotiation during communication windows and conservative stale-policy reporting; compare threshold-crossing detection with a changed A policy. |
| P1 | `config/profiles/deployment.json:4-45`, `sensor_node/adaptive_sense.py` | Duty-cycle timing and control-relevance rules are configured, but performance and calibration are not real agricultural measurements. | Compare fixed-rate, adaptive, relevance-gated and joint sensing/transmission on the same event traces; report miss rate, p95 detection latency, successful delivery, energy (J) and confidence intervals. Mark all estimated values as estimates. |
| P2 | `ai/`, `server/`, `docs/VERIFICATION_STATUS.json` | Model and cloud services are primarily host-tested/synthetic; no claim of demonstrated agronomic benefit is supported by this release. | Defer expanded AI/dashboard work until reliable data and actual hardware evidence exist. Use rule baseline, valid train/test split, independent holdout, shadow inference and signed/rollback-safe model activation. |

## Research direction

Recommended narrow question: **Under bounded battery capacity and unreliable radio links, can a control-relevant joint sampling and data-delivery policy lower *measured* energy while maintaining critical event recall, delivery reliability and detection latency?**

The full A/B/C/Server system is the experimental platform; do not treat every component as a separate novel contribution.

## Next implementation sequence (small reviewable changes)

1. Lock a reproducible host baseline using the current Git commit, Python versions and existing tests.
2. Define a B↔A delivery contract (identity, receive ACK, retries, persistence semantics) and write failure-injection tests **before** implementation.
3. Implement a bounded durable critical-sample buffer without discarding existing unacknowledged critical samples. Validate resets and flash wear assumptions.
4. Introduce a mockable E220 radio adapter and hardware test harness. Preserve existing TCP integration tests.
5. Implement/compile actual MCU sleep-state checkpoint/restore and conduct externally measured current profiling.
6. Add A failover partition and C safety test matrices; only enable real hardware actuation behind explicit safe configuration.
7. Run quantitative baselines and document positive **and negative** experimental results.

## Minimum evidence for a research-worthy milestone

- Exact commit/firmware hash, reproducible test invocation, device BOM and wiring.
- Sensor-event ground truth and clear distinction between **not observed** vs **observed but not delivered**.
- Per-run power traces or measured current integration, not upload count as an energy proxy.
- Detection recall, p95 delay, data delivery probability, retry count, and measured joules at comparable settings.
- Explicitly preserved unresolved risks (offline partitions, hardware stuck-on safety, corruption, wear).

## Review status

This document is an **audit/backlog**, not an implementation or verification report. Source locations above are based on the new branch at its creation from `main`. Changes should be limited to `research`, tested before merging or declaring success.
