# Smart Agriculture Edge AI v0.3.1

[English](README.md) | [简体中文](README.zh-CN.md)

The first research phase on the `research` branch adds a bounded B1 buffer for critical data, stable message identities, and durable acknowledgements from the gateway. Its software evidence and hardware verification boundaries are documented in the [development report](docs/research/PHASE1_DEVELOPMENT_REPORT.md).

**Reliability Hardening & Protocol Correctness**

A distributed smart agriculture system that brings together trustworthy sensing, adaptive sampling, interchangeable edge decision engines, guarded control, gateway takeover, offline history replay, and reproducible fault experiments. All seven roles can run on a single computer. The node runtimes require only the Python standard library.

## Project North Star — Do Not Drift

**This section defines a lasting design constraint. Future README revisions must preserve its meaning and strength.**

The project is built for farms where devices run on batteries and connectivity is weak, intermittent, or entirely unavailable. Its central goal is:

> Let each node sense, assess, and act locally. Spend communication energy only when the information justifies it, then synchronize with the cloud when connectivity returns.

```text
Sense locally
    ↓
Evaluate locally
    ↓
Transmit only when necessary
    ↓
Decide locally
    ↓
Act locally
    ↓
Sync when connectivity allows
    ↓
Learn from accumulated field data

Cloud unavailable ≠ Farm unavailable
```

The cloud is an enhancement layer. It must never become a prerequisite for the farm's real-time control loop. Gateway A makes local decisions and Controller C executes them safely. The cloud stores history, handles synchronization, supplies policy improvements, and supports future offline training.

## Two Agricultural Zones and Gateway Ownership

Zone 1 always pairs **B1 with C1**; Zone 2 always pairs **B2 with C2**. Each zone has a complete Sensor B, Gateway A, and Controller C. A1 and A2 exchange heartbeats, and synchronize with the cloud when a connection is available. The architecture below shows the normal deployment of both zones. Both are integral parts of the system.

| Operating state | Zone 1 | Zone 2 |
|---|---|---|
| Normal operation | B1 → A1 → C1 | B2 → A2 → C2 |
| A1 fails | B1 → A2 → C1 | B2 → A2 → C2 |
| A2 fails | B1 → A1 → C1 | B2 → A1 → C2 |

**Gateway ownership can move; zone membership cannot.** The B1→C1 and B2→C2 mappings in `CONTROLLER_OF_SENSOR` remain fixed. Takeover uses the existing OwnershipManager, heartbeat timeout, generation/epoch, registration, and stale-command rejection mechanisms. A recovered gateway enters STANDBY. There is no automatic failback.

```text
                                      ┌─────────────────────────────┐
                                      │        Cloud Server         │
                                      │                             │
                                      │  • Sensor History           │
                                      │  • Node / Gateway Status    │
                                      │  • Control History          │
                                      │  • Alerts                   │
                                      │  • Policy Management        │
                                      │  • Deduplication            │
                                      │  • SQLite Persistence       │
                                      └──────────────┬──────────────┘
                                                     │
                                   telemetry / policy / replay
                                                     │
                        ┌────────────────────────────┴────────────────────────────┐
                        │                                                         │
                        ▼                                                         ▼
              ┌──────────────────────┐                                 ┌──────────────────────┐
              │      Gateway A1      │◄──── Heartbeat / Ownership ────►│      Gateway A2      │
              │                      │      Generation / Failover    │                      │
              │  • Node Registry     │                                 │  • Node Registry     │
              │  • Sensor Quality    │                                 │  • Sensor Quality    │
              │    Gate              │                                 │    Gate              │
              │  • Edge AI /         │                                 │  • Edge AI /         │
              │    DecisionEngine    │                                 │    DecisionEngine    │
              │  • ACK / Retry       │                                 │  • ACK / Retry       │
              │  • Dedup / Sequence  │                                 │  • Dedup / Sequence  │
              │  • Offline Queue     │                                 │  • Offline Queue     │
              │  • Local Autonomy    │                                 │  • Local Autonomy    │
              │  • Failover Control  │                                 │  • Failover Control  │
              └─────────┬────────────┘                                 └─────────┬────────────┘
                        │                                                         │
              ┌─────────┴──────────┐                                    ┌─────────┴──────────┐
              │                    │                                    │                    │
              ▼                    ▼                                    ▼                    ▼
     ┌─────────────────┐  ┌─────────────────┐                  ┌─────────────────┐  ┌─────────────────┐
     │    Sensor B1    │  │  Controller C1  │                  │    Sensor B2    │  │  Controller C2  │
     │                 │  │                 │                  │                 │  │                 │
     │ Physical / Sim  │  │ Command RX      │                  │ Physical / Sim  │  │ Command RX      │
     │ Sensors         │  │      ↓          │                  │ Sensors         │  │      ↓          │
     │      ↓          │  │ Receipt ACK     │                  │      ↓          │  │ Receipt ACK     │
     │ SensorTrust     │  │      ↓          │                  │ SensorTrust     │  │      ↓          │
     │      ↓          │  │ Safety Guard    │                  │      ↓          │  │ Safety Guard    │
     │ Health / Fault  │  │      ↓          │                  │ Health / Fault  │  │      ↓          │
     │      ↓          │  │ Owner / Epoch   │                  │      ↓          │  │ Owner / Epoch   │
     │ AdaptiveSense   │  │ TTL / Cooldown  │                  │ AdaptiveSense   │  │ TTL / Cooldown  │
     │      ↓          │  │ Idempotency     │                  │      ↓          │  │ Idempotency     │
     │ Sampling /      │  │      ↓          │                  │ Sampling /      │  │      ↓          │
     │ Upload Policy   │  │ Actuator        │                  │ Upload Policy   │  │ Actuator        │
     │      ↓          │  │ Execution       │                  │      ↓          │  │ Execution       │
     │ SENSOR_DATA /   │  │      ↓          │                  │ SENSOR_DATA /   │  │      ↓          │
     │ ALERT           │  │ CONTROL_RESULT  │                  │ ALERT           │  │ CONTROL_RESULT  │
     └────────┬────────┘  └────────▲────────┘                  └────────┬────────┘  └────────▲────────┘
              │                    │                                    │                    │
              └─────── Zone 1 ────┘                                    └─────── Zone 2 ────┘
```

A1/A2 are edge gateways, B1/B2 are sensor nodes, and C1/C2 control the corresponding zones. Sensors and controllers sit alongside one another: B1 readings always govern C1, including after gateway takeover. The server, controllers, and gateway reliability mechanisms are all part of this repository.

## From a Reading to a Control Result

```text
SensorSource → SensorTrust → AdaptiveSense → SENSOR_DATA / ALERT
                                               ↓
Gateway: quality gate → DecisionEngine → CONTROL_COMMAND
                                               ↓
Controller: ACK → SafetyGuard → simulated execution → CONTROL_RESULT
                                               ↓
Gateway: live upload / SQLite OfflineQueue → Server: atomic dedup + history
```

- **SensorTrust** tracks RANGE, STUCK, SPIKE, DRIFT, and MISSING faults independently for each channel. It reports `health_score`, `fault_flags`, and a HEALTHY/DEGRADED/FAULT classification. DRIFT is measured as a rate of change per second. Reading validity is separate from the fault score: an invalid reading cannot authorize control, even before MISSING has been confirmed.
- **Trust requirements follow the action.** Rule-based irrigation needs trustworthy soil moisture; ventilation needs trustworthy temperature. A fault in an unrelated channel does not block an independent action. Logistic, Tree, and MLP require all four channels to be valid and HEALTHY. Overall health and fault history are still recorded. ALERT messages are sent when health or the fault signature changes, with reminders every 300 seconds and a notification on recovery.
- **AdaptiveSense** uses normalized EMA/STD/ROC scores and a STABLE/ACTIVE/ALERT state machine. Escalation is immediate; relaxation proceeds in stages with hysteresis and interval ladders. Upload triggers include the first valid sample, state or interval changes, event onset or recovery, meaningful changes in valid data, and a low-frequency upload heartbeat. Faulty readings are excluded from environmental change scoring, and the environmental baseline is rebuilt on recovery.
- **Sampling and connection maintenance serve different purposes.** Python SensorNode is the Host Simulation Profile. Socket reception, second-scale NODE_STATUS messages, and sampling run independently so that protocol behavior, CI, takeover, and fault injection can be tested. A battery-powered field node is intended to communicate intermittently and avoid online heartbeats every few seconds. **Simulation timing ≠ Deployment timing.**
- **DecisionEngine** gives Rule, Logistic, Tree, and MLP the same `predict(sample, policy)` interface. Rule is the default. The other models are reproducible references trained to imitate a synthetic policy with a fixed seed, supporting training, export, and engine-switching tests. They have not been validated as agricultural control models using real field data. Feature order and version are fixed in `ai/features.py`.

## Reliability and Safety

- B/C registration establishes the owner and generation. SensorNode and Controller accept gateway NODE_STATUS updates and reject inconsistent sources or stale generations.
- Heartbeats, ACK and result timeouts, node liveness timeouts, and cooldowns use monotonic time. `last_seen`, protocol timestamps, and database records retain wall-clock time. Client timestamps do not determine liveness.
- CONTROL_COMMAND keeps a stable `message_id`/`command_id`, uses a finite ACK retry budget, and is handled idempotently by the controller. Retries increment `attempt` while preserving the logical message identity.
- A command ACK confirms receipt. CONTROL_RESULT reports the execution outcome. If no result arrives after an ACK, the outcome becomes UNKNOWN and an alert is raised. A late result can resolve the uncertainty; a missing result is never repaired by executing the command again.
- Controllers process commands serially. SafetyGuard checks the command type, `command_id`, TTL, generation, owner, duplicates, maximum duration, and cooldown. Concurrent copies of one command execute only once.
- A gateway heartbeat timeout initiates takeover and advances the generation. The recovered former gateway remains STANDBY until ownership is explicitly changed.
- SENSOR_DATA, CONTROL_COMMAND, CONTROL_RESULT, and ALERT uploads enter a SQLite outbox before delivery. Their identities are preserved during FIFO replay, and rows are removed only after a separate `PERSISTED_ACK`. A lost acknowledgement leaves the local copy intact; after reconnection, the server deduplicates it and acknowledges it again.
- If a controller is unavailable, ownership has been lost, or a command has expired, an unsent command is recorded as `NOT_DISPATCHED` with a reason. A retry that might already have been sent is recorded as `UNKNOWN` when delivery cannot continue. Actuator commands are never held for execution at some later date.
- The server validates each upload's business semantics, then writes its deduplication record and business history in one SQLite transaction. The durable acknowledgement is sent after commit. Invalid uploads do not consume an identity.
- `SERVER_POLICY` validates its version and parameters atomically, persists locally, and is then activated. The last known good policy can be loaded after a restart while the cloud is offline. Checkpoints contain `policy_version`, the payload, SHA-256, and `updated_at`. Corruption falls back to the previous valid policy or compiled defaults. The policy ACK confirms receipt; the server does not guarantee policy retries based on that ACK.

### Protocol Compatibility

TCP messages are newline-delimited JSON. The original six-field envelope remains supported:

```json
{"type":"SENSOR_DATA","source":"B1","target":"A1","timestamp":1234567890.0,"message_id":"sample-001","payload":{}}
```

Optional fields are `protocol_version:1`, `sequence`, `attempt`, and `generation`. Messages without them follow the legacy protocol. New simulated sensors identify logical samples with a boot ID and sequence number. Reordered or duplicated old readings can remain in the audit history, but cannot trigger new control.

Parsing rejects non-finite or overflowing numbers, incorrect field types, unsupported versions, and oversized frames. Gateway and server upgrades must be coordinated: a new gateway retains its outbox copies if an old server cannot provide durable acknowledgements. The protocol does not provide identity authentication.

## Running the System

Use Python 3.10 or later. CI verifies Python 3.10 and 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python demo.py --duration 30
.venv/bin/python -m pytest tests/ -q
```

Each role also has its own CLI:

```bash
python -m server.server --port 9100 --db server.db
python -m gateway.gateway --id A1 --engine rule
python -m gateway.gateway --id A2 --engine rule
python -m sensor_node.sensor_node --id B1
python -m sensor_node.sensor_node --id B2
python -m controller_node.controller_node --id C1
python -m controller_node.controller_node --id C2
```

The demo retains the normal, failover, and server-offline scenarios, along with stale-command and duplicate-command injection options. Formal experiments use their own configurations, ports, and databases.

## Configuration and Timing Profiles

`config/software.json` defines the software baseline and complete topology. `common/settings.py` validates it, while `common/config.py` retains compatibility constants. Set `SMART_AGRICULTURE_CONFIG=/path/config.json` to select a baseline for independent processes. Constructor overrides and experimental `runtime_overrides` are recorded in the experiment configuration.

Profiles in `config/profiles/` configure sampling and uploads separately from cloud reconnection:

| Profile | STABLE | ACTIVE | ALERT | Upload heartbeat in stable conditions |
|---|---|---|---|---|
| simulation | 20→40→60 s | 15→10→5 s | 5 s | 60 s |
| lab | 2→4→5 s | 2→1 s | 1 s | 300 s |
| deployment | 20→40 min | 10→5 min | 5→2→1 min | 6 h |

Deployment values are **engineering defaults**. They need calibration against crop characteristics, sensor noise, environmental dynamics, battery measurements, and field trials. Thresholds, EMA windows, event duration, and fault reminders are configurable as well. A deployment profile changes the behavior of the system beyond a single sleep interval.

`config/physical_b1.json` explicitly preserves the historical temperature/humidity SensorTrust settings. Run `python scripts/generate_b1_profiles.py` to generate B1's C parameters, or use `--check` to detect stale generated configuration.

Python/C Upload Decision Parity tests feed identical inputs to both implementations and compare state, next interval, detected event, and upload request for every sample. Coverage includes stable conditions, gradual change, sudden change, event onset and recovery, sensor faults, periodic uploads, and large deltas. These shared traces provide test evidence, not a mathematical proof across every floating-point boundary.

## Experiments and Verification Evidence

```bash
python -m experiments.runner --all --output results/software-v0.3.1/my-run
python -m experiments.runner --scenario ack-loss --output results/software-v0.3.1/ack-loss-run

git clone https://github.com/Sver0411/EdgeFaultLab ../EdgeFaultLab
python -m experiments.edgefaultlab --edgefaultlab-root ../EdgeFaultLab --output results/software-v0.3.1/efl-run
```

For formal reproduction, check out the reviewed EdgeFaultLab revision listed in `docs/integration_sources.json`. EdgeFaultLab remains an independent project; this repository supplies the configuration, CLI, and port adapter. Failed runs return a nonzero exit code.

Each internal experiment saves `config.json`, `manifest.json`, `truth/injection_plan.json`, `raw/events.jsonl`, `results/metrics.json`, `results/summary.json`, and a report. Existing output directories are never overwritten. Metrics distinguish `null / not measured` from `0 / observed`. TCP reception, receipt acknowledgements, execution outcomes, and persistence are measured separately.

The following results belong to the historical v0.3/v0.3.1 runs. Subsequent deployment-semantics work is documented in the [deployment realignment report](docs/DEPLOYMENT_REALIGNMENT_REPORT.md).

- The 155 tests from the v0.3 baseline were retained. v0.3.1 passed **231 tests**, with successful Python 3.10/3.12 [CI runs](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37177748586). Commands and evidence are in the [reliability report](docs/V0_3_1_RELIABILITY_REPORT.md).
- **20/20 internal scenarios passed**: the original 17, plus registration-race, persisted-ack-loss, and controller-unavailable.
- All five independent EdgeFaultLab scenarios passed after removing the adapter's startup delay. The initial v0.3 failures and subsequent regression records were preserved.
- Shared Python/C SensorTrust traces continued to pass on the host. No hardware was operated during that work.
- All three FP32 exports matched their trainers' predictions on 240 held-out samples. Four training/export files were reproduced byte for byte with the same seed.
- The INT8 weight-storage reference differed from FP32 on 2/240 Logistic predictions and 0/240 MLP predictions. Activations and biases remain floating point, and weights are dequantized before inference. There is no integer inference kernel or device-level result yet.

The new software capabilities have been **host-tested / software experimentally evaluated**. Historical B1 firmware and experiment records remain available in [firmware/b1](firmware/b1/README.md) and [results/v0.3](results/v0.3/README.md). Their verification scope is separate from these software results.

## Offline Model Tools

Only offline training requires the additional dependencies. Running the nodes does not require sklearn or numpy.

```bash
pip install -r requirements-training.txt
python -m ai.train --seed 42 --output ai/artifacts
python -m ai.quantize --output ai/artifacts/int8
python -m ai.benchmark --output model_benchmark.json
```

`ai.train.train(..., rows=feature_label_rows)` accepts externally supplied feature/label rows and labels the output `user-provided-unvalidated`. This provides an entry point for future datasets. Model exports record the training/holdout split, data hash, seed, feature version, and source.

Logistic made 10/240 policy-imitation errors on the synthetic holdout set. That negative result is retained; it does not measure agricultural effectiveness. Host latency and JSON size must not be presented as MCU latency, flash consumption, or energy measurements.

## Sensor B's Physical Deployment Profile

> Sense locally and communicate only when information is worth the energy.

```text
Wake → Read Sensors → SensorTrust → AdaptiveSense → Update local state
    → Decide next sampling interval → Decide whether transmission is necessary
        ├── NO  → Sleep
        └── YES → Wake radio → LoRa → A → Radio sleep → Sleep
```

**Sampled != transmitted.** B1's `upload_requested` now reaches the sample, transmission queue, and transmission guard. A stable reading no longer enters the queue automatically. Communication events include the first valid sample, important state changes, confirmed event onset or recovery, large deltas, health/fault changes, low-frequency health reports, and configured critical conditions. An unchanged fault signature does not cause every faulty sample to be transmitted.

**Low-Power Communication:** a control-relevant threshold crossing requests an immediate upload. The lightweight ControlRelevanceGate compares trustworthy channels with their last successfully reported or admitted values. It detects both directions of crossing for soil `< threshold` and temperature `> threshold`. A configurable profile margin can also request a report when a value enters the threshold's neighborhood. `upload_reasons` retains every trigger. Untrusted channels follow the sensor-fault path; an unrelated fault does not hide a trustworthy temperature crossing. Gateway A remains responsible for the control decision.

The ESP32 Wi-Fi/TCP implementation in `firmware/b1` is a **Development / Integration Transport**. It retains its value for hardware integration while keeping sensing logic independent of sockets. `b1_telemetry.c` builds business payloads, `b1_transport.h` provides the sink interface, and `b1_network.c` implements the TCP/Wi-Fi adapter.

Python `SensorRuntime` and `MockFieldTransport` test the radio wake/send/sleep flow on the host. The Python TCP SensorNode accepts only simulation and lab profiles. Combining deployment's minute-scale sampling with second-scale online keepalive does not establish a battery-powered deployment.

In Phase 1, state stays in RAM between samples while the task waits for its next wake-up. Wi-Fi integration uses modem power save and offers opt-in ESP-IDF automatic light sleep. Keeping TCP associated still incurs protocol traffic. On-demand E220 wake-up and complete radio sleep remain future work.

Phase 2 will define RTC-retained state and NVS checkpoints before introducing deep sleep. It must retain SensorTrust history, EMA and time history, hysteresis and ladder state, event duration, fault signature, last upload, and the ownership epoch. Resetting the algorithms after every sleep would break continuity. See the [deployment contract](docs/DEPLOYMENT_SEMANTICS.md). No current, energy, or battery-life conclusion is claimed for this work.

The target field platform is **ESP32-S3 + E220 LoRa**, covering B↔A and A↔C. A1↔A2 coordination must also work independently of the internet, the cloud, and a Wi-Fi access point. The E220 adapter, framing, wireless registration, ownership notifications, and heartbeat transport remain **planned / host-tested contracts**, without hardware validation.

**Field LoRa Semantics:** B belongs to a zone, not permanently to a gateway. Uplinks carry `source_node_id`, `zone_id`, sequence, boot/session identity, and the payload. Only the current zone owner may control its fixed C node. Gateway logic detects failover; B is not expected to listen continuously to both gateways or send frequent probes.

TCP fallback supports host integration. The eventual LoRa uplink can address the zone, so B can keep its zone identity without first changing a destination gateway. Necessary local policy and epoch exchanges occur during communication windows. Their final timing still requires hardware verification.

## Gateway A's Local Autonomy and Weak-Link Synchronization

The local path remains receive B → validate / Trust Gate → DecisionEngine → CONTROL_COMMAND → C → CONTROL_RESULT. Cloud reconnection and outbox replay run in separate tasks. Slow cloud receipts do not block local persistence of new history or the B→A→C loop.

Cloud connectivity has ONLINE, DEGRADED, and OFFLINE states. Deployment reconnection backs off through 5/15/30/60/300 seconds; simulation and lab have their own settings. After reconnection, replay is throttled according to configuration, and each row still requires its own PERSISTED_ACK before deletion. An explicit CRITICAL event can request one early reconnect, subject to cooldown.

Gateway heartbeats carry connectivity state and outbox depth, byte usage, oldest-record age, and rejection counts into cloud history. The host TCP heartbeat implementation does not establish that the field system will keep operating after its Wi-Fi access point is disconnected.

**Offline Queue:** capacity is reserved for critical records. Of the default 10,000 messages / 16 MiB, 1,000 messages / 1,677,722 bytes are reserved for HIGH traffic. NORMAL admission stops at that reserve boundary; HIGH can use the remaining total capacity. CONTROL_RESULT, CRITICAL events, command-delivery failures, gateway takeover, and severe sensor faults receive HIGH priority.

When total capacity is exhausted, new admission is explicitly rejected and recorded in priority metrics, logs, and local alert state. Previously admitted messages are retained. FIFO order, stable identities, deduplication, and PERSISTED_ACK semantics remain intact.

**Controller Safety:** recent command IDs must survive restart before real actuators are deployed. The host RecentCommandStore keeps a configurable bounded window, defaulting to 64. It persists INTENT before simulated execution, then persists the result. Corruption or failure to write the intent defaults to DO NOT EXECUTE. An incomplete intent also blocks replay after restart, but does not prove successful execution. A future ESP32 controller will need an NVS backend; this has not been verified on a board.

**Time Semantics:** wall-clock time alone is insufficient to establish the freshness of an offline control command. The planned LoRa contract combines owner/epoch, gateway and receiver boot sessions, command sequence/identity, a receive window issued in advance by the receiver, and monotonic expiry/retry bounds. The host contract can validate fresh commands without wall-clock time; TCP retains its compatible timestamp TTL. Starting a new TTL when an old packet arrives does not make it fresh. See the [five patches and their evidence](results/final-five-patches/README.md).

## Cloud Responsibilities and Learning from Field Data

The cloud already provides a TCP receiver, SQLite history, atomic deduplication with PERSISTED_ACK, and policy push. **An HTTP API and Web Dashboard are still missing.**

The next read-only API should expose zone status, latest readings and history curves, gateway ownership and connectivity, alerts, control history, and outbox/replay status. It must distinguish stale data from a low-power node that is expected to be asleep. The design is documented in [cloud boundaries](docs/CLOUD_BOUNDARIES.md). This work introduces no broker, microservices, or Kubernetes.

Logistic, Tree, and MLP remain synthetic policy-imitation models: **they are not validated agricultural intelligence**. The intended future workflow is:

```text
Field Data → Cloud DB → Dataset Builder → Versioned Dataset
    → RTX GPU Offline Training → Candidate Model → Evaluation
    → Model Registry → Approved Deployment
```

Retraining will be batched or scheduled. Receiving one sample must never trigger a new training run. External rows are currently accepted by the software training interface, but field labels, versioned datasets, RTX GPU training, evaluation approval, a model registry, and automated deployment remain unimplemented.

## Verification Levels

**Designed** means a contract has been defined. **Host Tested** means host tests have been run. **Software Experimentally Evaluated** means the complete software system has been exercised under faults. **Firmware Implemented** refers to firmware source/build evidence. **Hardware Tested** requires evidence from real devices. **Pending** identifies remaining work. Several levels can apply to one capability; none substitutes for another.

| Capability | Current evidence | Remaining work or boundary |
|---|---|---|
| SensorTrust | Host Tested / Firmware Implemented; historical HW1 normal readings | Field calibration of fault thresholds |
| AdaptiveSense | Host Tested / Software Experimentally Evaluated / Firmware Implemented | Hardware verification of the revised semantics; real environmental events |
| B upload policy | Host Tested per sample in Python/C and through queue/sink / Firmware Implemented | Radio uploads with the revised firmware |
| Physical SHT30 | Hardware Tested: 30 historical reads with valid CRC | No board flashed during this work; channels beyond temperature/humidity untested |
| B low-power runtime | Designed / Host Tested with mock / Firmware Implemented with opt-in light sleep | Radio duty cycle, current, and battery measurements |
| B↔A LoRa | Designed / Host Tested message/sleep contract | E220 adapter and RF tests |
| A DecisionEngine | Host Tested / Software Experimentally Evaluated | MCU port and agricultural effectiveness |
| A1/A2 heartbeat | Host Tested / Software Experimentally Evaluated | Local wireless hardware link |
| Gateway failover | Host Tested / Software Experimentally Evaluated | Complete hardware demonstration; no automatic failback |
| A↔C LoRa | Designed | E220 adapter and RF tests |
| C actuator | Host Tested safety guard / simulated execution | Real relay, pump, and fan operation |
| Cloud offline replay | Host Tested / Software Experimentally Evaluated | Long-term storage and power-loss tests |
| Dashboard | Designed | HTTP API and frontend |
| Training on real data | Designed; synthetic tools Host Tested | Field data, labels, GPU training, and registry |

Historical hardware claims remain limited to the [HW1 record](results/v0.3/README.md). They cannot be reused as evidence for the revised upload policy, LoRa, power consumption, or failover.

## Roadmap — Gateway Failure Hardware Demonstration

One of the next stage's most important system-level hardware experiments is:

```text
Normal: B1 → A1 → C1   and   B2 → A2 → C2
Power off A1
    ↓
A2 detects local heartbeat timeout
    ↓
A2 persists a newer epoch and takes ownership of Zone 1
    ↓
B1 → A2 → C1   while   B2 → A2 → C2 continues
Restore A1
    ↓
A1 sees newer generation → remains STANDBY
```

Run the demonstration with the internet and cloud disconnected, and verify that coordination also works independently of the Wi-Fi access point. Record the zone, owner/generation, ACK, and execution outcome for every sample and command. Inject an old A1 command and confirm that C1 rejects it.

This experiment follows completion of the E220 link, NVS support, B's sleep behavior, and C's actuator integration. It is **Pending**; no hardware result is claimed. Camera input, Tiny Vision, YOLO, and image uploads are outside the scope of this work.

## Current Limitations

- The CLI uses a file-backed outbox. The constructor's default in-memory queue is suitable only for software tests. Durable acknowledgements protect uploads admitted to the outbox; upstream delivery and in-memory task queues before admission have no general persistence guarantee. Outbox limits are configured by message count and payload bytes. Full capacity rejects new admission with metrics, while previously admitted, unacknowledged history is retained without TTL eviction. Physical disk capacity, WAL growth, and a corrupt first FIFO row still require operational handling.
- The host gateway persists ownership, generation, and peer epoch. On recovery it starts in STANDBY and aligns with its peer. The controller persists its highest generation/owner and recent intents/results before simulated execution, then conservatively waits a full cooldown after restart. Corrupt critical state disables control rather than reverting to an older value. The ESP32 controller NVS backend remains unimplemented. The bounded recent-command window cannot provide permanent idempotency, and a crash can leave the actual outcome UNKNOWN. Actuator execution is not guaranteed exactly once across restarts.
- Dual-gateway heartbeats and owner/generation checks do not form a consensus protocol. The split-brain scenario checks rejection of stale generations and non-owner commands within the same epoch. It does not establish exclusive control under every possible network partition.
- STUCK cannot distinguish a truly constant environment from a frozen sensor. DRIFT can also reflect a real, sustained environmental change. Actions relying on DEGRADED channels are blocked, and thresholds still need agricultural calibration.
- Legacy sensor telemetry remains best effort. Sequence checks prevent stale readings from triggering control; they do not themselves provide sensor-side persistence or retransmission. The B1 research delivery work referenced at the top has its own explicitly documented scope.
- Authentication, encryption, cross-node clock synchronization, and deployment calibration are absent. TCP CONTROL_COMMAND timestamps still require Unix wall-clock time. The host model for future field freshness has been tested, but is not yet integrated into wireless firmware.
- Model tests establish the software workflow. INT8 results cover a weight-storage reference only. Full C inference parity, real-data effectiveness, device resource consumption, and energy use remain unmeasured.

## Documentation and Next Steps

[v0.3.1 reliability report](docs/V0_3_1_RELIABILITY_REPORT.md) · [code review](docs/V0_3_1_RELIABILITY_REVIEW.md) · [v0.3 integration and reuse report](docs/V0_3_INTEGRATION_REPORT.md)

The [branch integration review and latest software verification](docs/BRANCH_INTEGRATION_REVIEW.md) records checkpoint, command-window, and configuration fixes made before the development line was integrated into the main line. Historical test and experiment reports retain their original scope.

Next priorities are field E220 communication, NVS epoch handling, real power measurements, and the Gateway Failure Hardware Demonstration described above. The complete two-zone topology remains a permanent part of the project.

MIT licensed. Directly reused AdaptiveSense Python files retain their MIT license notices and source attribution.
