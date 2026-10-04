# v0.3.1 Reliability Hardening & Protocol Correctness

Date: 2026-10-04. Software only; complete Server/A1/A2/B1/B2/C1/C2 topology retained.

## 1. Problems found / 2. Root cause

Review started at main `3697494`, following README, the v0.3 report, source, tests, raw experiments and Actions run 37142688673. Details: [pre-change review](V0_3_1_RELIABILITY_REVIEW.md).

| Problem | Actual root cause |
|---|---|
| registration ownership race | Gateway registration upserted owner=self instead of consulting the seeded zone/epoch; inbound node messages could also create socket associations without accepted registration. Controller ignored accepted=false. Same-epoch node adoption replaced remembered owners. |
| controller unavailable silent drop | Dispatch returned before tracking/uploading an unavailable or deposed command. |
| offline queue durable receipt gap | Both live upload and replay treated local TCP drain as success; replay deleted rows before server commit. |
| semantic validation gaps | Envelope validation was sound, but business inserts used default `?`/UNKNOWN values. Only a subset of sensor semantics was checked. |
| trust gating over-conservative | The aggregate worst channel state blocked both rule actions despite separate soil/temperature dependencies. |
| alert flooding | Every suspect sample emitted a new alert regardless of an unchanged fault signature. |
| metric ambiguity | Every receive used the first send timestamp for the identity, including retry delay and repeated receives. |
| elapsed-time clocks | ACK, peer and node expiry depended on wall time; cooldown did too. A peer never observed remained UNKNOWN forever. |
| additional correctness gaps | Malformed owner arrays could crash registration; extreme JSON integers could overflow numeric checks; an older in-flight execution commit could replace a newer owner. Frozen physical B1 health has score/flags without Python's valid field, requiring explicit compatibility. |

## 3. Implementation

### Ownership and registration

Registry zone ownership exists before connections. `_handle_register` checks known node type, target, current owner/role and supplied generation; it refreshes liveness/socket only on acceptance. Rejection replies carry accepted=false, NOT_OWNER, current owner and generation. B/C validate typed replies, follow an owner candidate hint, refuse competing same-generation ownership, and accept newer epochs. Each bounded candidate pass has reconnect backoff; a rejection never starts sampling/execution.

Heartbeat carries the gateway's owned-node epochs. Peer observations advance only known entries whose epoch is newer locally and no greater than the announcing gateway's epoch. Recovery demotes stale gateways and updates their registry; registration cannot reclaim nodes. Formal timeout takeover is the only runtime path assigning foreign zone ownership. A never-seen peer can time out after gateway startup. Startup delay was removed from the EdgeFaultLab adapter and internal roles start concurrently.

This provides the tested ownership boundaries, not consensus or proof against arbitrary partitions. Epoch and controller-owner memory remain volatile across reboot.

### Dispatch outcome

An unsent first attempt blocked by CONTROLLER_UNAVAILABLE, NOT_OWNER, STALE_GENERATION or EXPIRED creates a CONTROL_RESULT with NOT_DISPATCHED, command/controller/type/gateway/generation, issued_at and audit timestamp. A retry may follow an already executed command with lost ACK; blocking it produces UNKNOWN rather than a false no-execution claim. Both stop command delivery tracking and upload only history. No actuator command is placed in a long-lived execution queue.

### Server semantics and durable receipt

`server/validation.py` checks SENSOR_DATA, CONTROL_COMMAND, CONTROL_RESULT, ALERT, HEARTBEAT and policy ACK semantics. Fault sensor values (finite out-of-range values and null missing fields) remain evidence; malformed types do not. Legacy partial sensor records are retained. Required command/result identities, controller/type/status/duration/generation and failure reasons are checked. Alerts are serializable; heartbeat roster/status/epoch/role are checked. Policy ACK is a control-plane receipt and does not consume business dedup identity.

Order: envelope → semantic validation → SQLite transaction → dedup/business insert → commit → PERSISTED_ACK. Duplicate committed uploads receive another receipt. Failed validation or DB transaction produces no persisted receipt and restores counters; dedup is not poisoned. Heartbeats remain ephemeral uploads with committed history when received; outbox receipts cover SENSOR_DATA/CONTROL_COMMAND/CONTROL_RESULT/ALERT.

Every queueable `_deliver` stages into the local SQLite outbox before socket send, even online. A serialized FIFO flush registers message_id→queue_id/future/socket before sending; a separate receiver reads receipts while flushing waits. Only typed SERVER→gateway persisted=true receipts on the active connection resolve that row. Timeout/disconnect retain it; reconnect automatically replays. Duplicate/late ACKs cannot delete unrelated rows. Server commit + lost ACK yields replay, one business row and a renewed receipt. Constructor memory queues are test-only; standalone CLI uses file queues. Mixed deployments must upgrade Server/Gateway together: old servers cannot confirm, so new gateways retain copies.

### Trust, alerts, clocks and metrics

RuleEngine evaluates only trustworthy dependency fields: IRRIGATION requires soil_moisture; VENTILATION requires temperature. Missing/nonfinite/out-of-range or DEGRADED/FAULT dependency fields are excluded; healthy unrelated channels may still control. Learned engines require all four valid HEALTHY fields. Legacy aggregate-only health stays conservative. Frozen physical channel state/score/flags remains accepted when the numeric field is valid; the Python valid flag, when present, must be true. Global health and per-action evidence remain server history.

FaultNotifier sends initial suspect, state/validity/channel-fault signature changes, recovery and monotonic reminders (default 300s). Identical suspect samples do not flood alerts. It survives a socket reconnect within the node process; it is not persisted across node reboot.

Monotonic clocks govern peer/node expiry, ACK retries, result deadlines, sampling and cooldown. Protocol/DB audit timestamps and CONTROL_COMMAND TTL stay wall-clock based. Registry last_seen is audit wall time; a separate seen_monotonic governs expiry. Explicit test time overrides remain supported.

Metrics now expose attempt_transport_latency (matched successful socket drain→decode), logical_delivery_latency (first send request, including injected drops/retries→first decode), ack_latency (first request→first receipt ACK), and persisted_ack_latency (first request→SQLite receipt). Attempts match envelope attempt and FIFO sends when the attempt is reused. Unmatched timing is not measured, and duplicate logical delivery/ACK does not create extra completion observations. No host timing is RF/device latency. Compatibility metrics offline_queued/queue_replayed count all durable outbox staging/confirmed deletion, including online traffic; they are not outage-only counters.

## 4. Tests

Actual local full-suite command: `.venv/bin/python -m pytest tests/ -q` (Python 3.14.7). Logs: `results/software-v0.3.1/validation`.

| Stage | Verdict | Result | Raw log |
|---|---|---|---|
| Baseline | PASS | 155 passed in 39.55s | `baseline.log` |
| Ownership registration | PASS | 163 passed in 38.85s | `registration.log` |
| Undispatched outcome | PASS | 168 passed in 38.60s | `undispatched.log` |
| Server semantics | PASS | 191 passed in 39.85s | `semantic.log` |
| Durable receipt | PASS | 196 passed in 40.91s | `persist.log` |
| Action trust | PASS | 214 passed in 40.99s | `trust.log` |
| Fault notifications | PASS | 216 passed in 41.48s | `alerts.log` |
| Monotonic clocks | PASS | 219 passed in 40.76s | `clocks-fixed.log` |
| Latency metrics | PASS | 221 passed in 41.03s | `metrics.log` |
| Scenarios / adapter | PASS | 225 passed in 45.93s | `scenarios-fixed.log` |
| Malformed replies / in-flight ownership | PASS | 229 passed in 45.10s | `boundaries.log` |
| Legacy health compatibility | PASS | 230 passed in 44.92s | `final-tests.log` |

Final task lifecycle full suites: `.venv/bin/python -m pytest tests/ -q` passed **231 tests in 44.91s** on Python 3.14.7; `uv run --python 3.10 --with 'pytest>=7' python -m pytest tests/ -vv -o faulthandler_timeout=30` passed **231 tests in 45.27s** on Python 3.10.21. After adding an explicit controller registration completion barrier, the Python 3.10 experiment/shutdown subset passed **10 tests in 10.94s** (`python310-barriers.log`).

No original tests were deleted. Existing fallback-registration test was changed to assert rejection until takeover; the adapter test now asserts absence of startup delay. Duplicate execution testing explicitly isolates ownership changes, because the new absent-peer startup timeout legitimately advances generation.

Additional verification exposed a lifecycle boundary: a legacy asyncio timeout/cancellation race can return from an in-flight wait despite worker cancellation. Gateway workers now check the stopping flag before waiting for another item, and replay checks it too. A deterministic test emulates a swallowed cancellation and requires worker completion. Sensor/command queues now acknowledge task completion; controller-unavailable waits for TCP EOF, drained decoded decisions, persisted outcomes and an observed controller handshake before judging no late execution. These are observable progress barriers, not startup delays. CLI regression subprocesses have a hard 15s timeout.

Negative results retained: the first clock run had 1 failed / 218 passed (a duplicate test also crossed a bootstrap epoch change); corrected by isolating that test's peer timeout. The first scenario full suite had 1 failed / 224 passed (old startup-delay assertion); updated to the new contract. An initial new-scenario edit had a SyntaxError; its raw log is retained. These were corrected before the corresponding passing commit. First matrix run [37176556017](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37176556017) had a successful Python 3.12 job but the 3.10 job stalled and was cancelled; verbose diagnostics/time limits were added. Second run [37176895260](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37176895260) recorded 229 passed / 1 failed on Python 3.10 (short controller-unavailable observation), while 3.12 passed. A local 3.10 run stalled waiting on the CLI child process; its faulthandler log is preserved and the test processes were terminated. Task shutdown and completion barriers were then fixed and verified. We do not count these runs as successful matrix acceptance.

Final [matrix acceptance run 37177279953](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37177279953): **PASS**, source `e9cf7a5547b367d0b126767a18ff1d6f8aa21428`. Python 3.10 and 3.12 each passed 231 tests; Python 3.12 also passed all 20 internal and 5 independent external scenarios. Raw CI log is `validation/ci-acceptance.log`. Test-created experiment evidence is uploaded alongside full-suite evidence, including on failure. Main acceptance is recorded after merge.

## 5. Experiments

Executed local commands:

```bash
.venv/bin/python -m experiments.runner --all --output results/software-v0.3.1/final
.venv/bin/python -m experiments.runner --all --output results/software-v0.3.1/final-acceptance
.venv/bin/python -m experiments.runner --all --output results/software-v0.3.1/release
.venv/bin/python -m experiments.edgefaultlab --edgefaultlab-root /tmp/smart-agriculture-v03-sources/EdgeFaultLab --output results/software-v0.3.1/edgefaultlab-final
.venv/bin/python -m experiments.edgefaultlab --edgefaultlab-root /tmp/smart-agriculture-v03-sources/EdgeFaultLab --output results/software-v0.3.1/edgefaultlab-release
```

Local complete suite at `final`: 20/20 PASS; source `538a766` with README restoration uncommitted (dirty flag preserved). `final-acceptance` also passed 20/20 after the legacy compatibility patch. After the lifecycle/barrier fix, `release` passed **20/20**, including every original scenario, at source `e9cf7a5` (documentation/evidence bookkeeping edits uncommitted; dirty flag retained). Clean committed-code acceptance is the CI run. Raw/config/truth/results are retained; runtime timing overrides are now explicitly written into config.json. Earlier v0.3 evidence is unchanged.

| Internal scenario | Verdict | Assertions |
|---|---|---|
| normal | PASS | 5/5 |
| full-control-loop | PASS | 5/5 |
| packet-loss | PASS | 7/7 |
| ack-loss | PASS | 8/8 |
| duplicate-command | PASS | 6/6 |
| delayed-result | PASS | 7/7 |
| lost-result | PASS | 7/7 |
| reordered-messages | PASS | 7/7 |
| sensor-fault | PASS | 6/6 |
| gateway-failover | PASS | 9/9 |
| gateway-recovery | PASS | 10/10 |
| stale-generation | PASS | 9/9 |
| server-offline | PASS | 8/8 |
| queue-replay | PASS | 9/9 |
| policy-replay | PASS | 6/6 |
| split-brain | PASS | 6/6 |
| expired-command | PASS | 6/6 |
| registration-race | PASS | 8/8 |
| persisted-ack-loss | PASS | 12/12 |
| controller-unavailable | PASS | 9/9 |

Registration-race deliberately sends B1/C1 first to A2, observes two NOT_OWNER replies, then verifies A1 ownership at epoch 1 and real control execution. Persisted-ack-loss records the actual queue row and committed dedup record at the dropped receipt boundary, then checks replay dedup, one business row and deletion. Controller-unavailable stores non-dispatch history, stops the sensor, reconnects the controller and verifies no old command is sent or executed. No scenario depends on a startup delay for ownership correctness. CLI returns nonzero for any failed assertion.

## 6. EdgeFaultLab

Independent checkout at `c7248239f456cc877114ca1e67c5949fb4a7b958`. No code copied into this repo. The adapter remaps ports/paths/config and runs all seven roles via the external runner/proxies. No --startup-delay is used; zero cooldown and accelerated sampling are experiment configuration only, enabling nonvacuous command assertions.

| External scenario | Final local verdict | Revision |
|---|---|---|
| gateway_failover | PASS | c724823 |
| server_outage | PASS | c724823 |
| duplicate_control_command | PASS | c724823 |
| stale_command | PASS | c724823 |
| lost_command | PASS | c724823 |

This round's first, final and release external runs each passed 5/5; release uses source e9cf7a5. Negative v0.3 first-run evidence remains intact. Final remote acceptance reruns the independent templates at the same revision.

## 7. Remaining limitations

- No consensus protocol: simultaneous failures, arbitrary partitions and cross-restart epoch negotiation are not proven safe.
- No cryptographic identity, encryption or authenticated ownership/receipts.
- No real agriculture model validation; synthetic provenance and quantization disagreement evidence remain unchanged.
- No RF/hardware evaluation or firmware build in this round.
- No persistent actuator exactly-once guarantee across controller reboot; command IDs, owner/epoch and outcome memory are volatile. An already started actuator action cannot be undone by an ownership change.
- Wall clock still needed for command TTL; clock synchronization remains a deployment requirement.
- Node-side telemetry is best effort, and data in application task queues before durable outbox staging can be lost on process crash. Invalid historical rows can block FIFO replay; repair/quarantine policy is future work. SQLite disk exhaustion is not solved.
- Persisted ACK demonstrates the server's SQLite commit under the host environment; storage-device corruption/power-loss/RF behavior has not been evaluated.
- Fault thresholds need domain calibration; conservative blocking of an action's own degraded channels trades availability for safety.

## 8. Next phase

Design persistent epoch/actuator-idempotency/outcome recovery and invalid-outbox quarantine, then calibrate sensor thresholds and collect labeled agriculture data. Keep the complete topology and rerun this acceptance suite. README restores the supplied architecture diagram and keeps detailed evidence here.
