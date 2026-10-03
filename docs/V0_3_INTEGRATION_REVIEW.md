# v0.3 Software integration design review

Review date: 2026-10-04. Review precedes algorithm changes. Source revisions are frozen in `integration_sources.json`.

## Baseline and architecture

Public main: `565b109` (v0.2, 84 tests). Working baseline: `5a01dcd` (B1 firmware/evidence branch, 86/86 host tests passed in 29.95s). The independent `4e320f9` v0.2.1 fixes are integrated first; firmware and historical evidence remain preserved. Target topology stays Server ↔ A1/A2 (peer heartbeat), with B1/C1 and B2/C2 as sibling zone nodes. All seven roles run on one workstation with asyncio TCP and SQLite. No hardware operations are part of this release.

## Code-level findings

- `common/messages.py`: stable newline JSON envelope and malformed-input tests; no sequence/version/attempt contract, accepts nonfinite timestamps, payload semantics vary. Add optional backward-compatible fields and bounded validation; do not replace transport.
- `common/config.py`: topology is complete, but timings and algorithm configuration are constants. Introduce a validated JSON source for system/node/policy/experiment settings, preserving constant aliases and constructor overrides.
- `common/reliability.py`: AckTracker retry budget is tested; Counters does not distinguish unmeasured metrics. Preserve it, add explicit observations and transport accounting.
- `sensor_node/sensor_trust.py`: field/range validator is a prototype. Stateful RANGE/STUCK/SPIKE/DRIFT/MISSING reference semantics need per-channel history, validity, score and state. Keep stateless compatibility functions.
- `sensor_node/adaptive_sense.py`: relative-change fast/slow prototype lacks normalized score, hysteresis, ladders and upload policy. Retain legacy functions for callers; runtime uses the new scheduler.
- `sensor_node/sensor_node.py`: mixes source and transport, and on the old branch is send-only. Integrate v0.2.1 concurrent RX/keepalive, separate source interface, emit health evidence to the gateway/server, and never feed suspect readings into environmental scoring.
- `gateway/gateway.py`: seven tasks already separate flows; preserve them. Sensor payload handling, model selection, command delivery and policy validation require explicit boundaries. Preserve physical partial-data compatibility. Commands from FAULT/DEGRADED readings are blocked conservatively; history and ALERT still upload.
- `gateway/registry.py`, `ownership.py`: tested receive-time liveness and takeover generation; epoch is memory-only. Two-node heartbeat cannot prove exclusive ownership during arbitrary network partitions. Keep limitation explicit; do not claim consensus.
- `gateway/offline_queue.py`: durable FIFO and IDs are good. v0.2.1 drain/reconnect patch fixes >100 replay. Successful TCP drain is not durable server receipt; disclose this remaining boundary.
- `controller_node/safety_guard.py`: TTL, epoch, owner, duration, cooldown/idempotency covered. Reject NaN/Inf and malformed generation. Process command concurrency can race before commit; serialize execution. ACK is receipt, never execution. Missing command_id must not silently become message_id.
- `server/`: SQLite and dedup are appropriate. Dedup-before-store can mark malformed uploads as processed. Validate payloads and make dedup/data transaction atomic. Preserve schema/history and health metadata.
- `demo.py`: full topology works; global random command loss is not reproducible, reused DBs can pollute results. Keep CLI, introduce isolated seeded experiment runs and structured assertions.
- `tests/`: existing unit/integration/failover coverage is useful and retained. Gaps: five temporal sensor faults, scheduler transitions, model export/switching, lost ACK/result, concurrency, sequence reorder, experiment failures.
- README describes Python sensing as placeholder and presents historical simulation numbers without a current run context. Replace current capability claims and link old hardware evidence with its original scope; preserve negative results.

## Reuse decisions

| Project | Direct reuse | Adaptation | Design reference | Excluded |
|---|---|---|---|---|
| SensorTrust | Frozen fault penalties/state thresholds | C11 detector semantics → Python per-channel reference | Observable fault fixtures, recovery and time-based drift | ctypes/cffi, hardware accuracy claims |
| AdaptiveSense | Python ChangeAnalyzer and pure scheduler transitions (MIT attribution) | Four agriculture channels, trust-aware scheduling, JSON config | Replay and config parity | MQTT/power/device drivers |
| TinyEdgeBench | None of its dataset/model parameters | Small model training/export and common feature ordering | Shared splits, deterministic training, serialized size and host latency | Original labels, claimed agriculture accuracy, hardware flash/INT8 claims |
| EventGuard-LoRa | No research policy/code | Stable logical identity, sequence/attempt accounting | Seeded injection, raw evidence, negative results | E220/RF/GPIO, importance/copy-budget policies |
| EdgeFaultLab | External package/scenario runner | CLI/config/port/path adapter and stronger assertions | System fault tests | Vendoring/copying its engine |
| EdgeSense-AIoT | No business code | Manifest/truth/raw/results and verification ladder | Separate truth from observed decisions | Firmware business logic and transferred validation claims |

## Implementation plan and boundaries

1. Merge proven hardening and record review/source provenance.
2. SensorTrust Python reference with five fault families; fault evidence persists, unhealthy data never controls actuators.
3. AdaptiveSense analyzer/state/ladder/upload scheduler; validity gates scoring, keepalive remains independent.
4. Rule/logistic/tree/small-MLP engines behind one decision API. Synthetic data only for software validation, reproducible seed and exported models; default stays rule.
5. Envelope/config validation, identity/sequence and explicit reliability metrics; lost execution result means unknown outcome, never automatic actuator re-execution.
6. Isolated complete-topology TCP experiment harness, deterministic faults, machine assertions and persisted raw evidence. EdgeFaultLab stays independent and its real runner is exercised.
7. Run all host tests/scenarios, commit each tested step, document exact results and limitations.

No broker, microservices, LLM, dashboard rewrite, repository split or topology reduction. New layers must have executable consumers and tests. Runtime remains standard-library Python; model training tooling can be optional. Verification for new work stops at host-tested and software experimentally evaluated.
