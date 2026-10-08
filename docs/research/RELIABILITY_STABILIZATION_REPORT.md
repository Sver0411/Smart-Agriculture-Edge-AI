# Research reliability stabilization

## Scope and provenance

Baseline: `d1a70000a87ab6cf96762f10e4865a862ce43694`, fetched from `origin/research` on 2026-10-09 (Asia/Shanghai). PR #4 was verified merged on 2026-10-08 at 17:21:26 UTC. `origin/main` was `9ebc707ec013be56ae1b32f40279063822c0f738`; main and research history were not modified. Work is on `fix/research-reliability-stabilization`.

Seven roles, fixed B1/C1 and B2/C2 zones, local autonomy, SensorTrust, AdaptiveSense, ControlRelevanceGate, SafetyGuard, NVS HIGH retention, scoped PERSISTED_ACK, E220 prototype and experimental sleep remain intact. This report concerns host reliability and firmware compilation. It makes no physical RF, latency, power or exactly-once actuator claim.

Evidence: [selected original failures and manifests](../../results/research-reliability-stabilization/), including original CI events/configuration/manifest/summary/injection plan, baseline reproductions, failed development tests and their corrected validations. The original failed artifact ZIP SHA256 was independently verified: `d737712da74141c514da07aee1642b3fb3cd70f39dd611da25a9518c31a41e87` (artifact 11566653901). Full repeated-run provenance and logs are emitted into isolated directories and uploaded by CI; source/configuration/result hashes identify the actual tree, including an explicit dirty flag where applicable.

## Findings and fixes

| Priority / classification | Confirmed behavior | Fix and verification boundary |
| --- | --- | --- |
| P0 / FIXED AND VERIFIED (focused host tests) | Initial peer heartbeat could arrive after the experiment's 0.6 s failure detector; a pre-injection takeover satisfied the old recovery wait. An obsolete peer's later timeout could bump an already fenced epoch again. | Enroll a healthy topology before workload/fault injection; wait for OFFLINE plus equal A2/B1/C1 epochs and owners with a deadline; do not repeat an active higher-epoch takeover with no peer-owned nodes. Old-command rejection remains asserted. |
| P1 / FIXED AND VERIFIED (SQLite and socket fault tests) | Executed results had no durable resend/ACK lifecycle; queue-full rejection was ignored by C. | Reuse the command checkpoint for bounded pending results, atomic completion/result admission, stable result IDs, scoped durable ACKs and capped resend. SQLite receipt/outbox commit precedes ACK; retained receipts survive cloud dequeue and gateway reboot. |
| P1 / FIXED AND VERIFIED (restart tests) | Server broadcast incremented a RAM-only counter. Restart after version 100 published version 1. | Persist policy content, version and checksum together; allocate versions only for actual validated content changes with an atomic compare-and-update. Repeated broadcast/unchanged content does not create a version. |
| P1 / FIXED AND VERIFIED (fail-closed boundary) | `profile=deployment` could use lab enrollment; B/C/cloud identity declarations and LoRa CRC did not authenticate those links. | Refuse deployment constructors/CLI before opening resources. Even a valid peer HMAC key cannot authorize deployment while other links lack sessions. Lab/simulation remain available; nonce/session/sequence/route/epoch negative tests preserve ownership. |
| P2 / FIXED AND VERIFIED (host confirmation tests) | Simulated B advanced its upload baseline at successful write. | Explicit `legacy-write` compatibility contract and opt-in `gateway-durable`: HIGH file-backed pending evidence, NORMAL RAM-only, scoped ACK before baseline advancement, old-boot ACK retires history without confirming a new-boot baseline. |
| P2 / FIXED AND VERIFIED (portable C / compile scope) | Ordinary E220 task checked the queue once per 60 s. | Empty-to-nonempty or HIGH admission notifies the sole UART task. A portable deadline gate coalesces notifications, enforces 60–300 s unavailable backoff, and observes committed ACK progress rather than queue depth. FIFO within the existing bounded outbox preserves NORMAL opportunities. |
| P2 / FIXED AND VERIFIED (host fault tests) | A finite DeliveryWindow retained FAILED entries without a recovery path. | Keep finite experiments explicitly finite; opt-in long-running mode uses capped low-frequency probes at the same identity and capacity. ACK loss / receiver restart / long outage tests verify recovery; FRAME_ACCEPTED and MESSAGE_REASSEMBLED cannot release durable evidence. |

### P0: exact CI failure and reproducibility

The only failed assertion in [merged run 37815924817](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37815924817) was **`A2 peer A1 OFFLINE`**. Synchronized epoch, B1/C1 owner A2, and C1 `STALE_GENERATION` rejection all passed. This was not an observed old-epoch actuator execution.

Raw TCP events show A2 advertising epoch 2 / OFFLINE at 0.694 s, **before** the intended A1 crash at 0.925 s. A1's first heartbeat reached A2 at 0.699 s; its epoch was still 1 and its role STANDBY. Another obsolete heartbeat arrived at 0.922 s. The old recovery wait accepted B1/C1 takeover while A2 still reported ONLINE. A later timeout produced an unnecessary epoch 3. In [premerge run 37813375669](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37813375669), the corresponding TCP first heartbeat arrived at approximately 0.121 s and the scenario passed; simulated LoRa was approximately 0.120 s. The code did not change at merge in these paths: this evidence supports a scheduling/load-sensitive race, not a merge conflict or a demonstrated fencing breach.

The unmodified baseline scenario passed once locally: the aggregate CI race was not deterministically reproduced by that run. A separate deterministic baseline reproduction does reproduce epoch 2 → late obsolete heartbeat → epoch 3. Both observations are retained, rather than presenting a stochastic PASS as proof of absence. Initial focused verification ran stale-generation 10 times, failover 3, recovery 3, split-brain and controller-unavailable once, all PASS. Final repeat results are recorded in the regression section.

No fixed sleep was increased to mask the race. The existing observation window remains; state/deadline checks replace assumptions about startup/recovery. Frame faults start after initial peer enrollment, so the existing asymmetric partition test still injects its one-way heartbeat outage and observes demotion/takeover.

### Durable control-result contract

`ACK` confirms command receipt only. `NODE_STATUS / RESULT_RECEIVED` confirms ingress only. `PERSISTED_ACK / RESULT_DURABLY_STORED`, with scope `CONTROL_RESULTS`, contract `controller-result-durable-v1`, persisted=true and the original result ID, confirms a **file-backed gateway SQLite** transaction. `RESULT_REJECTED` (queue, capacity, validation or storage failure) never confirms durability. No TCP write or radio frame ACK serves as a durable receipt.

A persistent C uses the existing recent-command checkpoint, schema 2; schema 1 remains readable. Intent commits before the simulated actuator step. Known completion and its immutable result are committed together before sending. The original serialized result (including timestamp) stays in the bounded completed-command entry after ACK, so a later duplicate command/reboot cannot recreate conflicting content at the same result ID. Takeover retargets only the transport copy. An interrupted intent becomes UNKNOWN after reboot; an already cached pending UNKNOWN retains its identity. The bounded default 64-entry window cannot evict unresolved intent or unconfirmed outcomes. Completed IDs also remain protected until the original timestamped command has passed its SafetyGuard TTL. A small-window regression confirmed that ACK-only eviction could otherwise permit a still-fresh original command to execute again; TTL retention now blocks that replay. Legacy checkpoint migration conservatively retains entries for a full TTL. Backpressure prevents another action and recovers only after confirmations and safe command expiry free capacity. Genuine state failures disable further execution. Retry uses the same result/command ID, with per-session 1/2/4/8/16/30 s capped intervals. A historical result may follow a new owner at its original epoch; it is audit evidence, never permission to execute. Future/invalid epochs are rejected. Real TCP tests drop the first durable result ACK and verify one execution, one cloud EXECUTED row, replay dedup and reboot protection. The external adapter retains the original assertion metadata and tests command-ID uniqueness on an opt-in ACTUATOR_EXECUTED observation emitted only by the actual host execution branch. Reliable EXECUTED result retransmissions are separately checked for exact identity/content consistency and independent observed execution. A deliberate broken-fencing test produces two execution events despite identical cached result frames, proving this observation detects the prohibited second action.

Gateway result receipts and cloud outbox are in one SQLite transaction (`BEGIN IMMEDIATE`, synchronous FULL). Validation occurs before consuming a result identity. Duplicate receipts do not requeue an already synchronized row. Separate result receipt capacity defaults to 100000 and is observable in queue stats; full capacity rejects admission and retains all existing identities. Auxiliary sensor-audit failure cannot prevent original result delivery. Queue pressure, disk failure and a crash after commit but before ACK leave the C copy retryable. These guarantees assume the relevant persistent storage survives; physical action followed by a crash before observable completion remains UNKNOWN.

### Durable policies and legacy state

First creation persists the configured initial head (default 1; the regression starts at 100). Restart restores that exact version and content. SHA256 covers both version and canonical content, preventing unnoticed positive version corruption. A real configuration update validates, commits version+1, then activates; failed writes leave the old live head. A SQL compare-and-update rejects a second publisher allocating from stale state. Gateway replay/order checks remain enabled; its last valid local policy continues during cloud outage.

An old schema has no authoritative record of the highest published policy version. Migration adds the new table while **disabling publication**, retaining history service and gateway local policy. Missing/corrupt heads also disable publication; no fallback to an older publication version and no arbitrary version jump is allowed. Operators must restore the exact policy head from a trusted server backup/publication record before enabling updates. A gateway's lower observed version alone is insufficient to infer the highest server publication. Whole-file database corruption may prevent server startup; it does not reset field policy or authorize control.

### Security inventory and migration gate

| Link | Lab/simulation capability | Deployment status |
| --- | --- | --- |
| A ↔ A | Explicit session enrollment; optional >=32-byte out-of-band shared-key HMAC, signed challenge/heartbeat, nonce and increasing 32-bit sequence | Deployment refuses lab mode/missing key, and still refuses operation until all remaining links authenticate |
| B ↔ A | Registered identity, ownership/boot/freshness checks; durable upload contract is not identity authentication | NOT READY: device session authentication missing |
| A ↔ C | Accepted registration, epoch/owner SafetyGuard, command idempotency and durable result receipts | NOT READY: gateway/controller session authentication missing |
| A ↔ Server | Route/semantic validation, transactional dedup and persisted policy/receipts | NOT READY: mutual session authentication missing |
| E220 | B1 UART/AUX/mode driver, CRC/framing/bounded reassembly; physical A/C endpoints missing | NOT READY: authenticated framing and commissioned endpoints missing |

HMAC is integrity/authentication, not encryption. CRC detects accidental corruption, not a hostile source. Keys are external files, never Git configuration. Gateway/server/controller `--profile deployment` fails closed; simulated SensorNode already rejects deployment, and `SensorRuntime(physical=True)` refuses the unauthenticated adapter. Timing profiles and the experimental B1 firmware are research configurations, not secure commissioned deployments.

Concrete follow-up: (1) commission A/C hardware endpoints; (2) issue separate device/role keys out of band, with key IDs and revocation; (3) authenticate both sides with fresh challenge/session nonces and signed role/source/target/zone/epoch binding before accepting registration; (4) authenticate every application frame with session/sequence and payload integrity, including receipts and results; (5) re-enroll after reboot/sequence exhaustion, reject replay before ownership mutation, and cap enrollment work; (6) use TLS where suitable for cloud TCP confidentiality and authenticated compact radio frames for E220; (7) add negative/rotation/restart/partition tests before enabling a secure deployment flag. This migration spans host and missing MCU endpoints and is deliberately not claimed complete here.

### Sensor and radio semantics

Ordinary simulation defaults to `legacy-write`: it records a telemetry **attempt**, preserving historical algorithm experiments. Reliable host simulation requires `--delivery-mode gateway-durable --state-db PATH`. Acquisition time/sequence and original reading/trust are frozen for pending reports; rejection/drop/ACK loss does not advance ControlRelevanceGate or AdaptiveSense upload baseline. New samples still update event history. Reboot creates a new boot identity, retains HIGH, drops NORMAL, and treats old pending age as unknown. This matches the B1 NVS HIGH / RAM NORMAL / scoped receipt boundary and avoids treating recovered historical samples as fresh actuator input. A reliable duty-cycle adapter must explicitly implement `receive_confirmation(timeout)`; mock writes do not imply confirmation. A whole-process reboot still rebuilds temporal algorithms unless an independently validated snapshot/elapsed-time provider is supplied.

Notifications do not access UART; only the ordinary network task runs radio windows. Experimental Deep Sleep returns from app startup before creating that task and keeps its own window. AUX/BUSY bounds and existing registration, retry and NVS semantics remain. Notifications during backoff only recheck the deadline; successful windows coalesce arrivals for at least 2 s, pending ACK progress schedules a later opportunity, and lack of progress grows backoff to at most 300 s. The portable C test covers wake opportunity, unavailable backoff, coalescing, rollback and overflow. C host timing is not physical RF latency/current.

`DeliveryWindow(recovery_interval=None)` is the historical finite host experiment. Exhausted entries remain bounded retained evidence, and INCOMPLETE stays INCOMPLETE. `recovery_interval=60` opts into long-running low-frequency probes with a 300 s default cap, without new rapid bursts or identity changes. It is an in-memory state machine; B1 NVS provides firmware persistence, while reliable host B saves HIGH through StateStore. SimulatedLoRa is a finite host fault adapter, not a production RF endpoint.

## Experiment-data handling

A conservative reviewed inventory of the **4769 previously tracked results files** classified A=933 original/unclassified-unique evidence, B=3224 report-referenced, C=274 failure evidence and D=338 exact-byte duplicate candidates. E=0 / F=0 are separately classified temporary CI/build outputs in that historical tracked set. There are 143 identical-byte groups, but equal bytes do not prove interchangeable experiment context. **No historical results were deleted.** B/C have precedence over duplicate classification. The initial automatic classifier treated 20 `.bin` files as F; inspection showed they were snapshot/outbox input fixtures, so the classifier and reviewed inventory now retain them as A/D scientific evidence. Both the preliminary summary and corrected review are retained. Full reviewed inventory SHA256 is `a7ff98845c19873abebc64f48a146fcf3c7758892f665731122b44e0bb3c4da8`; the summary and reproducible inventory tool are included. Subsequent inventory adds this task's selected evidence and records its own revision/hash.

A/B/C remain in Git. D/E/F are retained conservatively; new redundant runs, CI outputs and builds go to isolated `.research-runs/`, temporary directories and Actions artifacts instead of another bulk result commit. Default new topology/stabilization/inventory outputs are ignored, refuse overwrite, and include configuration/source/raw hashes. Original failure selection is explicitly versioned. There are no broken historical links from removal. `common/field_transport.py` now distinguishes host framing, the implemented B1 E220 driver, missing A/C endpoints and pending physical validation. Both README architecture diagrams and the Chinese README remain.

## Regression commands and current status

Run commands from repository root; each output directory must be fresh. Full Python suites are sequential on one machine because existing e2e tests use fixed ports 9201/9202.

```sh
python -m pytest tests/ -q -o faulthandler_timeout=60
python -m experiments.runner --all --output .research-runs/tcp-NEW
python -m experiments.reliability_stabilization --output .research-runs/repeats-NEW
python -m experiments.runner --all --transport simulated-lora --output .research-runs/lora-NEW
python -m experiments.lora_harness --seed 42 --output .research-runs/comparison-NEW
python -m experiments.snapshot_harness --output .research-runs/snapshot-NEW
python -m experiments.phase123_integration --seed 42 --output .research-runs/integration-NEW
python -m experiments.edgefaultlab --edgefaultlab-root .external/edgefaultlab --output .research-runs/external-NEW
python -m experiments.evidence_inventory --output .research-runs/inventory-NEW.json
# Export ESP-IDF v5.4.4; repeat with all four profiles:
bash scripts/ci_build_b1.sh lab /tmp/agri-idf-lab-NEW
```

EdgeFaultLab is pinned at `c7248239f456cc877114ca1e67c5949fb4a7b958`. No restricted EventGuard-LoRa source was copied. Unit tests compile/run production C with ASan/UBSan where applicable. Actions runs the same complete matrix on both branch push and PR, preserves failure artifacts and records source/toolchain provenance before tests.

The complete local matrix below ran on clean source `2e3280b17b7a4edc139aee7afaf1a671b856a993` (`dirty=false`). [Final selected validation evidence](../../results/research-reliability-stabilization/validation/final/) includes the source/configuration hashes, exact experiment command arguments, suite summaries, raw pytest logs and four firmware manifests. Full local outputs are in `/tmp/agri-stabilization-verified`; complete CI experiment outputs and failures are retained as Actions artifacts. The subsequent report/evidence and inventory-classification correction does not change controller, gateway, server, sensor or firmware behavior, and triggers the same complete push/PR CI again.

| Validation | Actual result on tested source |
| --- | --- |
| Python 3.10.21 | PASS: 582 tests, 123.68 s |
| Python 3.12.14 | PASS: 582 tests, 82.86 s |
| Full original TCP scenarios | PASS: 20/20 |
| Repeated stabilization scenarios | PASS: 20/20 — stale-generation 10, failover 3, recovery 3, split-brain 1, controller-unavailable 1, server-offline 1, queue-replay 1 |
| Full host simulated LoRa topology | PASS: 20/20 |
| Seeded radio comparison | PASS: 56/56 safety checks; delivery **43 COMPLETE / 13 INCOMPLETE**, with retained unconfirmed evidence |
| Actual C sleep/snapshot oracle | PASS: 19/19 cases, 2800 observations across seven signal cases |
| Cross-phase integration | PASS: 10/10 |
| External EdgeFaultLab | PASS: 5/5; actual execution observations and immutable replay checks, with original assertion metadata retained |
| C Host / applicable ASan and UBSan | PASS within both full pytest suites; local Apple clang 17.0.0 (`clang-1700.0.13.5`) |
| Fresh public ESP-IDF v5.4.4 | PASS: lab 831152 bytes; light-sleep 848736; lora-prototype 329120; deep-sleep-experimental 350464; ESP32-S3 / Xtensa GCC 14.2.0 (`esp-14.2.0_20260121`) |
| Branch push Actions, source `2e3280b` | PASS: [run 37823781299](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37823781299), all six jobs |
| PR Actions, source `2e3280b` | PASS: [run 37824116529](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37824116529), all six jobs; complete scenario steps executed successfully |
| Physical E220 / A/C endpoints / current / sleep hardware | NOT RUN: hardware unavailable; PENDING HARDWARE VALIDATION |

Both CI runs execute pytest under Python 3.10 and 3.12, the complete experiment matrix under 3.12, and all four firmware profiles. The branch artifacts identify Python 3.10.22 / 3.12.15, Ubuntu GCC 13.3.0 for host C, ESP-IDF v5.4.4 and Xtensa GCC 14.2.0 for firmware. The local and CI patch versions differ and are recorded rather than conflated. Branch CI pytest was 582/582 on each interpreter (80.19 s / 66.69 s); all seven CI experiment suites match the PASS counts above. No failed core experiment was skipped to obtain success. Artifact IDs and published SHA256 digests, downloaded source manifests and job/step conclusions are in the selected final evidence. [PR #5 checks](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/pull/5/checks) track the latest report/evidence revision; both push and PR workflows must stay successful before merge.

| Regression coverage | Test files |
| --- | --- |
| Initial enrollment, obsolete-peer fencing and original fault scenarios | `test_stabilization_reproductions.py`, `test_registration_ownership.py`, `test_phase12.py` |
| Result durability, SQLite admission/rollback, recovery, immutable replay, capacity/TTL and real socket ACK loss | `test_result_delivery.py`, `test_result_delivery_e2e.py`, `test_execution_observation.py` |
| Policy restart/migration/corruption/concurrent publishers | `test_server_policy_persistence.py` |
| Deployment refusal, authentication/replay/route/epoch rejection | `test_deployment_security.py` |
| Scoped sensor confirmation, loss, rejection and reboot | `test_sensor_report_confirmation.py` |
| Radio recovery, deadline/backoff/coalescing and ACK-progress semantics | `test_lora_retry_lifecycle.py`, `test_b1_radio_schedule.py`, `c_host/b1_radio_schedule.c` |

A later confirmed-result/reboot replay regression also failed: the result ID was stable but its timestamp was regenerated after pending ACK removal. The complete original wire representation is now retained with the completed entry; the regression confirms equal content and successful gateway dedup after restart. Failed development tests are retained. The first ownership unit fixture mistakenly used 10 s against the configured 12 s timeout; it was corrected to explicitly configure 1 s. Original P1 reproductions failed because the required persistent retry window/policy-update API did not exist; a separate unmodified-code reproduction confirmed actual version 100→1 and missing result resend state. The first full suite had three failures: capacity tests must ACK completed results before eviction; initial healthy enrollment must precede asymmetric injection; legacy result compatibility/auxiliary-audit handling required a product fix. Assertions about safety and original outcome upload remain. The first complete local matrix passed TCP/repeats/LoRa/comparison/snapshot/integration but failed the external duplicate-command assertion: replayable EXECUTED reports were counted as actions. The adapter now observes the actual execution branch while preserving uniqueness/nonvacuity; it also verifies result replay content. The first branch CI run 37821602482 compiled firmware successfully but failed all four firmware jobs at provenance generation because container Git rejected checkout ownership. A repository-specific per-command safe.directory fixes provenance without globally trusting repositories. The first external observation-metadata attempt was rejected by EdgeFaultLab's strict scenario schema; original assertions now live in a separate evidence file. A small-capacity replay test then confirmed ACK-only eviction could forget a still-fresh executed command; protecting completed IDs through TTL fixes it and preserves bounded backpressure. These failures and their sources are retained. The first socket ACK-loss test installed its ContextVar interceptor after task creation, so the gateway had no fault injector; installing it before tasks makes the intended ACK actually drop. That corrected test passes and asserts both a dropped ACK and a deduplicated retry.

## Remaining limits and merge judgment

DESIGN LIMITATION: heartbeat failure detection is not distributed consensus under arbitrary/asymmetric partitions. Generation fencing acts after a controller observes a higher epoch. Exactly-once physical outcomes remain impossible across unobservable crash windows. Bounded receipt ledgers require capacity monitoring and a future proven retirement/restore protocol; they are not silently pruned. Old server policy publication state may require authoritative recovery. Legacy-write sensor simulation intentionally has weaker confirmation semantics. Recent-command dedup is bounded and relies on the existing trusted host timestamp/TTL contract: confirmed entries can be evicted only after their original command expiry. Reusing an evicted ID with newly fabricated content/timestamps and arbitrary wall-clock rollback are outside this isolated-lab identity contract; secure deployment remains refused.

UNVERIFIED RISK: long-term flash wear, prolonged capacity pressure with field duty cycles, hostile-environment framing and partition authority beyond the current experiment model. These are not labeled confirmed bugs without evidence.

PENDING HARDWARE VALIDATION: A/C physical RF endpoints, E220 AUX/BUSY/wiring/airtime and reset behavior, RTC elapsed calibration and retention, GPIO holds, NVS power-cut behavior, battery/current/temperature variation and measured HIGH latency/energy. Software PASS and IDF builds do not satisfy these gates.

Merge judgment: **READY FOR RESEARCH**, subject to successful checks on the final PR head. The complete local matrix and both push/PR CI at the tested implementation revision passed. No confirmed unresolved P0/P1 bug remains in these tested host paths. The deployment gate is intentionally closed, and hardware/design limits above remain explicit research work. A research merge does not approve field deployment. PR #5 targets `research`; it is not automatically merged, and `main` / `research` history is unchanged by this task.
