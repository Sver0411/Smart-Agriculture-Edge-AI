# v0.3 Integration report

Date: 2026-10-04. Scope: Software Integration & Experimental Foundation.

## 1. What changed

The existing v0.2.1 protocol-hardening and physical-B1 histories were integrated into main first (`7fcf560`); firmware and existing positive/negative evidence were preserved. Subsequent software work is staged in tested commits on `v0.3-software-integration` and merged into main after remote CI acceptance.

- Four independent SensorTrust channels now implement RANGE/STUCK/SPIKE/DRIFT/MISSING, score/state, availability and evidence. A missing measurement is blocked before MISSING confirmation. HEALTHY valid data may control; DEGRADED/FAULT data is retained and alerted but cannot control.
- AdaptiveSense's upstream Python analyzer and scheduler now provide normalized EMA/STD/mean ROC, hysteresis, immediate escalation, one-level relaxation, interval ladders, upload decisions and heartbeat uploads. Suspect readings never update its environmental history. Socket receive and keepalive stay independent.
- Rule/logistic/tree/small-MLP engines share a versioned feature pipeline and predict API. Training/export are repeatable, inference has no sklearn/numpy runtime dependency. `train(..., rows=...)` is the supplied-data entry; supplied rows are explicitly unvalidated. The default control engine stays rule.
- Optional envelope fields preserve legacy compatibility. Sensor boot/sequence prevents reordered samples from creating fresh controls; retries preserve identity and update attempt. Policy validation is atomic.
- Controller command processing is serialized; NaN/Inf, absent IDs and malformed epochs are refused. Missing results after receipt become UNKNOWN; late results resolve that state without issuing another actuator execution.
- Server dedup and business writes share a transaction; invalid uploads do not poison message identity. Sensor/alert health evidence is preserved.
- Experiments run all seven roles on real host TCP sockets, with simulated sensor/actuator inputs, independent ports/DBs, raw events and machine assertions. EdgeFaultLab remains a separate repository/package.
- Config defaults come from validated `config/software.json`; legacy constants are aliases. Per-run overrides, seed and config hash are recorded. Metrics explicitly distinguish unmeasured values from observed zero.

## 2. Reused assets

| Project | Reviewed revision | Actual use |
|---|---|---|
| [SensorTrust](https://github.com/Sver0411/SensorTrust/tree/fad43a495abddb9029ef005d16a0909ca1de957c) | `fad43a4` | C detector semantics and fixed penalties ported to ChannelTrust/SensorTrust; multi-fault/recovery/time-based drift fixtures; existing frozen C host core matches upstream hash. |
| [AdaptiveSense](https://github.com/Sver0411/AdaptiveSense/tree/6e0d086cf14c81d2fb5dba8305e13a7dff2dae3b) | `6e0d086` | Direct MIT Python ChangeAnalyzer reuse; AdaptiveScheduler copied with adapted imports. Agriculture channel configuration and trust gate added. License/source retained under third_party/adaptive_sense. |
| [TinyEdgeBench](https://github.com/Sver0411/TinyEdgeBench/tree/359bacd153b38218179f4977b2f748696b9d5844) | `359bacd` | Training/feature/export/parity and small-model cost methodology adapted; new synthetic agriculture-policy fixtures and independently exported models. |
| [EventGuard-LoRa](https://github.com/Sver0411/EventGuard-LoRa/tree/f7b6e44597abe958d7e9d6d481265d0fae33b749) | `f7b6e44` | Logical identity versus transmission attempt, sequence/dedup accounting, seeded frame faults, audit manifests and negative-result preservation. No research strategy/code copied. |
| [EdgeFaultLab](https://github.com/Sver0411/EdgeFaultLab/tree/c7248239f456cc877114ca1e67c5949fb4a7b958) | `c724823` | Its real external ScenarioRunner and five smart_agriculture templates executed. Adapter remaps paths/ports, config, process startup and complete node roster; strengthens fallback assertions. |
| [EdgeSense-AIoT](https://github.com/Sver0411/EdgeSense-AIoT/tree/f6f004bbd7e92bf1ebc024790f71c12fa8249bfd) | `f6f004b` | Verification ladder and separate manifest/truth/raw/results workflow; machine metrics with null for not measured. No business implementation copied. |

## 3. What was not reused

No whole repository was imported. No SensorTrust FFI, AdaptiveSense MQTT/power drivers, TinyEdgeBench original dataset/labels/model parameters, EventGuard importance/copy-budget policies, EdgeFaultLab engine source, or EdgeSense backend/diagnosis logic was copied. These either solve a different problem, carry hardware assumptions, or would add runtime complexity without helping this software release. EdgeSense/EventGuard are design references, not relicensed source imports.

No hardware experiment, firmware build, flash operation, RF measurement, server/controller repository split, dashboard rewrite, broker or cluster dependency was introduced.

## 4. Architecture

```text
                          Server
                       /          \
                     A1 <--------> A2
                    /  \          /  \
                  B1   C1       B2   C2

B: source -> trust -> scheduling -> telemetry/alert
A: validity/health/order gate -> engine -> bounded command delivery
C: receipt ACK -> guard -> serialized simulated execution -> result
A -> Server: durable offline FIFO -> transactional dedup/history
```

Default engines are rules. Learned and INT8 references are selectable software artifacts; none is presented as an agriculture deployment model. Reliability stays inside the monorepo and the Server stays outside the local control dependency.

New-code verification levels are recorded in `VERIFICATION_STATUS.json`: host-tested and software experimentally evaluated. Existing firmware/evidence under `firmware/b1` and `results/v0.3` keeps its historical scope.

## 5. Tests

Actual locally executed full suites, with logs in `results/software-v0.3/validation`:

| Stage | Command | Result |
|---|---|---|
| Original physical branch baseline (`5a01dcd`) | `.venv/bin/python -m pytest tests/ -q` | 86 passed in 29.95s |
| Merged baseline | `.venv/bin/python -m pytest tests/ -q` | 94 passed |
| SensorTrust/config | `.venv/bin/python -m pytest tests/ -q` | 108 passed |
| AdaptiveSense | `.venv/bin/python -m pytest tests/ -q` | 120 passed |
| Decision engines | `.venv/bin/python -m pytest tests/ -q` | 130 passed |
| Protocol/controller/server | `.venv/bin/python -m pytest tests/ -q` | 143 passed |
| Experiment framework | `.venv/bin/python -m pytest tests/ -q` | 147 passed |
| Initial release acceptance | `.venv/bin/python -m pytest tests/ -q` | 154 passed |
| Recovery metrics correction / final main | `.venv/bin/python -m pytest tests/ -q` | 155 passed in 38.64s |

No original tests were deleted. Two early collection failures (an indentation mistake in the policy handler) are preserved in `failed-collection-01.log` / `failed-collection-02.log`; they were corrected before the protocol stage passed.

Additional executed checks:

- Host C compilation and SensorTrust Python/C shared-trace comparison: part of the full suite, no board involved. Vendored `sensor_trust.c` SHA-256 equals reviewed upstream (`84ff663157edb012af0290cf9f0f1d6400cee382f47ea272e8ec2089e59a2b90`). This tests the shared fixture, not every possible floating-point boundary.
- `.venv/bin/python -m ai.train --seed 42 --output ai/artifacts`: all three exported predictors match sklearn on all 240 synthetic held-out rows.
- Training replay into `/tmp/sa-v03-model-replay` reproduced logistic/tree/MLP/report bytes exactly.
- Supplied-data smoke check trains, exports and loads all three engines from 120 provided feature/label rows, with 24/24 export parity per model and explicit `user-provided-unvalidated` provenance.
- `.venv/bin/python -m ai.quantize`: FP32/INT8 weight reference comparison is below.
- `.venv/bin/python -m ai.benchmark --output results/software-v0.3/model_benchmark.json`: measured host prediction cost and JSON artifact sizes only.
- `.venv/bin/python demo.py --duration 5 --db /tmp/sa-v03-demo.db`: PASS; raw console retained in validation/demo.log.
- Targeted malformed-input and engine/export checks after the full suite: PASS; release-targeted.log.

| Model | Synthetic held-out policy agreement | Export parity | INT8-vs-FP32 disagreements |
|---|---:|---:|---:|
| logistic | 230/240 | 240/240 | 2/240 |
| tree | 240/240 | 240/240 | not measured |
| mlp | 240/240 | 240/240 | 0/240 |

These are synthetic policy-imitation checks, not real agriculture accuracy. INT8 here quantizes stored weights then dequantizes for host inference; bias/activations remain floating point. It is not an integer device kernel. Logistic approximation and quantization disagreements are retained as negative results.

Final main CI: **PASS** on committed source `9c0d94653cca8c23ee4058c1c878178731053051`: 155 tests passed in 37.29s, 17/17 internal scenarios passed, 5/5 independent EdgeFaultLab scenarios passed. [Final main acceptance run](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37142688673). Earlier [branch acceptance](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37141974396) passed 154 tests before the recovery metrics correction. Workflow uploads raw evidence even on failure. The earlier [main baseline merge run](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37139572527) also passed.

## 6. Experiments

Commands actually run:

```bash
.venv/bin/python -m experiments.runner --all --output results/software-v0.3/attempt-01
.venv/bin/python -m experiments.runner --all --output results/software-v0.3/final
.venv/bin/python -m experiments.edgefaultlab --edgefaultlab-root /tmp/smart-agriculture-v03-sources/EdgeFaultLab --output results/software-v0.3/edgefaultlab-attempt-01
.venv/bin/python -m experiments.edgefaultlab --edgefaultlab-root /tmp/smart-agriculture-v03-sources/EdgeFaultLab --output results/software-v0.3/edgefaultlab-attempt-02
```

Both internal suites passed all scenarios. The final run additionally uses actual-sample interval histograms and logical decision IDs, rather than treating uploads/retries as extra samples/decisions. Manifests record source commit, dirty state and raw/config hashes; a dirty flag is retained where source changes were present during a run. Remote CI is the clean committed-code acceptance run.

| Internal scenario | Machine verdict | Passed assertions |
|---|---|---:|
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

| Independent EdgeFaultLab scenario | Second-run verdict |
|---|---|
| gateway_failover | PASS |
| server_outage | PASS |
| duplicate_control_command | PASS |
| stale_command | PASS |
| lost_command | PASS |

EdgeFaultLab first run passed 4/5. Duplicate-command FAILED because startup raced and B1/C1 selected different owners; the expected EXECUTED result was absent. That failure is preserved with logs, raw events and assertions. Adapter startup delay and a zero-cooldown lab profile ensure the duplicate injection really reaches an executing control loop. Second run observed 3 duplicated commands and 18 distinct successful C1 command IDs without duplicate execution. Defaults outside the lab retain their safety cooldowns.

Metrics scope:

- messages_sent: successful host write/drain; delivered: decoded receiver frames, not durable storage.
- ACK/retries/failures are command delivery observations; control_executed comes from controller state, not ACK count.
- Logical command decisions and per-sample intervals are counted independently of transmissions/uploads.
- Host receive latency and inference latency are measured; recovery_time is null outside measured recovery scenarios.
- Hardware flash, device latency, energy and RF performance remain not measured.

After the initial main acceptance, gateway-recovery aggregation was corrected to retain counters from every gateway incarnation, including A1 before its restart. A regression checks that reported command counts include all distinct observed sent command IDs. Targeted experiment tests passed (5 tests in 6.59s); the complete suite then passed 155 tests. A fresh gateway-recovery run at clean source `9c0d946` passed, with evidence under `results/software-v0.3/metrics-correction/EXP-001-gateway-recovery`. Earlier experiment snapshots remain unchanged; their recovery counters predate this correction. Final main CI reran all 17 internal and 5 external scenarios with the corrected aggregation.

## 7. Current limitations

1. OfflineQueue deletes after TCP drain, with no server durable receipt ACK. Some process/connection crash windows can still lose uploads.
2. Ownership epoch, controller idempotency and outcome tracking are volatile. There is no across-restart exactly-once guarantee.
3. Two-peer heartbeat/epoch checks are not consensus. The split-brain tests verify stale/non-owner rejection; arbitrary partitions are not proven safe.
4. STUCK may flag a genuinely constant environment; DRIFT may flag a genuine ramp. Conservative DEGRADED control blocking has an availability cost. Thresholds need domain calibration.
5. Telemetry has no node-side durable retransmission; ordering checks prevent stale control but do not restore lost samples. Socket identity is not cryptographic authentication.
6. CONTROL_COMMAND TTL still assumes Unix wall-clock timestamps; cross-node synchronization and a device clock contract require the next integration phase.
7. Synthetic models only validate the pipeline; INT8 is a weight-storage reference, and new Python adapters are not fully C/config parity validated.
8. Host experiments use accelerated timings and an in-process frame injector; EdgeFaultLab additionally exercises separate processes/proxies. Neither is a hardware or RF evaluation.

## 8. Next phase

First design server durable receipt and persistent epoch/idempotency/result recovery. Then calibrate fault thresholds and collect separately labeled agriculture data. Establish explicit firmware configuration mapping and algorithm/model parity before device integration. Preserve the complete seven-role topology and rerun this software acceptance suite at each step.
