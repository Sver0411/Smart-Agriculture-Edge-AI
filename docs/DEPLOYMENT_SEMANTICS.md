# Deployment Semantics & Edge Autonomy contract

Date: 2026-10-06. Extends v0.3.1; historical reports and hardware records retain their original scope. README's **Project North Star — Do Not Drift** is a permanent design constraint.

**Current-source reading note (2026-10-09).** The phase descriptions below record the original deployment contract. The prepared research source now includes bounded LoRa framing, the B1 E220 UART adapter, experimental RTC/NVS snapshots and durable sensor/result receipts. In `gateway-durable` mode, upload baselines advance after a matching committed gateway ACK; `legacy-write` retains the earlier best-effort contract. PERSISTED_ACK scopes distinguish gateway sensor admission, gateway result admission and cloud storage. Controller completed IDs remain protected through their original command expiry, and confirmed result replay retains original wire content. Gateway/controller board endpoints, authenticated field sessions and physical sleep/power validation remain pending; deployment entry points stay fail-closed. Use the [current evidence guide](RESEARCH_EVIDENCE_GUIDE.md#e-phase-123-stabilization-and-ar-1), [AR-1 boundaries](architecture/AR1_SENSOR_PIPELINE.md#remaining-architecture-debt) and [transport/sleep commissioning profile](../firmware/b1/EXPERIMENTAL_TRANSPORT_SLEEP.md) for the implemented semantics. Historical text below is retained rather than recast as a new experiment.

## Invariants

- Two fixed Zones: B1/C1 and B2/C2. Ownership may move; membership never moves.
- A1/A2 keep the existing heartbeat, OwnershipManager, registry, epoch, takeover and STANDBY mechanisms. Recovery is not an automatic failback.
- Cloud is outside `B → A → C → CONTROL_RESULT`. ACK means receipt; CONTROL_RESULT means execution outcome; PERSISTED_ACK means Cloud SQLite commit.
- B senses locally. A sample can update trust/history/scheduler without becoming a communication event.
- C performs validation, safe execution and reporting; it has no AI.

## Configuration / Upload Decision Parity

`config/software.json` remains the host system baseline. `config/profiles/{simulation,lab,deployment}.json` provides separate sampling, detector windows, event debounce, health reminder, upload heartbeat and Cloud reconnect/replay parameters. A profile file is not a complete field-network configuration. `SensorNode` is a host TCP simulator and refuses deployment mode. `SensorRuntime` is a host-tested duty-cycle logic consumer; an actual radio/MCU adapter is pending.

Physical B1 has only temperature/humidity. `config/physical_b1.json` retains its historical SensorTrust parameters, disables absent soil/light channels, and keeps its separate noise floors. `scripts/generate_b1_profiles.py` translates validated JSON to `b1_profiles.h`. Generated parameters live outside the algorithm. Python's detector history now has the same bounded capacity as C: `min(64, floor(variety_window / min_interval) + 2)`; sampling faster than the configured minimum is an accelerated experiment and may truncate history.

Shared trace tests compile actual C components for all three profiles. They compare state, next interval, detected_event and upload_requested, both for the four-channel core and the actual physical B1 trust wrapper. Inputs are float32-equivalent; score comparisons use a documented tolerance. Coverage: stable/noise, slow drift, sudden change, confirmed onset, recovery, range/read faults, low-frequency upload heartbeat and meaningful delta. Missing channels do not acquire a last-upload value of zero and spuriously trigger delta upload when they first appear.

Event reporting includes confirmed onset and recovery. Sensor faults suspend environmental scoring, use cautious configured sampling, upload on changed health signature or reminder, and reset the environmental baseline on recovery. SensorTrust contexts retain their own history. A spike clearing to a persistent RANGE fault is a changed signature and legitimately creates another upload.

### Control-relevant communication gate — host tested / firmware implemented

`ControlRelevanceGate` is a threshold communication gate, not a DecisionEngine. It compares trusted current channels with the last successfully reported/admitted sample using current local thresholds. Soil uses `<`, temperature uses `>`; both directions, including equality boundaries, request immediate upload even if event/delta/state/heartbeat do not. Profile margin 0 disables proximity reporting; positive margin reports entry from outside into the inclusive threshold±margin band once, rather than every sample inside it. Deployment defaults are soil 2 / temperature 0.5, simulation/lab 0; these need calibration.

All trigger names are retained in `upload_reasons`, including CONTROL_THRESHOLD_CROSSING / CONTROL_MARGIN_ENTRY and existing scheduler/health reasons. Untrusted channels cannot create a normal crossing reason. An unrelated channel fault does not hide a trusted temperature crossing; environmental scoring remains suspended as before.

Python TCP/runtime advance the relevance baseline only after the send succeeds; B1 advances it only after queue admission succeeds. A failed admission/report leaves the crossing pending. Queue admission is best effort and can later be dropped; it is not a persisted end-to-end receipt. B1 has no soil sensor, so C implements temperature relevance only. Shared tests compare C/Python crossing/reasons, including queue rejection and unrelated humidity fault.

Local thresholds start from validated policy config. Python `set_policy` and C `b1_policy_set_temperature_threshold` expose lightweight updates; this patch does not add a policy distribution protocol to B. A field adapter must exchange compatible threshold/policy version at a necessary communication window when A changes policy. Unknown/stale local thresholds cannot promise complete control relevance, especially for learned DecisionEngines; this gate is not a substitute for reporting freshness or Gateway safety policy.

`upload_requested` has one meaning: this sample should enter the transmission path. The C policy copies the scheduler bit (plus health transition/reminder) to `b1_sample_t`; `b1_queue_sample` rejects suppressed samples before any queue operation; `b1_transmit_sample` guards again before message construction/sink invocation. Sensor samples and successfully sent sensor messages are separate counters. C host tests invoke the actual policy/queue/telemetry code with FreeRTOS/cJSON sink stubs; this is dispatch evidence, not proof of RF delivery or serialization. The existing physical protocol TCP tests and ESP-IDF build provide separate checks.

A failed physical read still carries temperature/humidity keys with JSON null, plus trust/fault evidence. The former empty `data` object was rejected by Server semantic validation and could leave that unacknowledged row blocking FIFO replay. Host tests check the C null-field dispatch and the Gateway → Server durable acceptance independently; real-device serialization/transport is still untested in this round.

## B runtime / transport

`b1_types.h` and `b1_policy` are pure business logic. `b1_telemetry.c` constructs health/sampling payloads and envelope identity without a socket. `b1_transport.h` defines a payload-consuming send sink; `b1_network.c` supplies the Wi-Fi/TCP integration adapter. Future E220 work replaces the adapter, not SensorTrust or AdaptiveSense. Both success/failure paths of a sink consume the cJSON payload.

Python shares `sensor_payload` between the host TCP simulator and `SensorRuntime`. The latter calls `wake → send telemetry/event → sleep` only when a communication decision is true, and puts the mock radio to sleep even if transmission raises an error. It has no periodic TCP NODE_STATUS. Its caller supplies the next wake time and MCU sleep; the runtime object survives between cycles. Discovery, radio registration and ownership adoption remain adapter responsibilities and are not implemented by the mock.

Phase 1 firmware keeps one static policy in RAM. `vTaskDelay(next_interval)` allows scheduler idle; Wi-Fi uses modem power save. Optional `B1_LIGHT_SLEEP` uses ESP-IDF automatic light sleep with PM_ENABLE and FREERTOS_USE_TICKLESS_IDLE, allowing both tasks and Wi-Fi to cooperate. It is disabled by default. The integration TCP receiver can wake frequently and still keeps Wi-Fi associated; this is not the final battery runtime. Duty-cycled E220 radio plus MCU sleep needs a real adapter and current measurements.

Phase 2 must explicitly retain/checkpoint:

| State | Why it survives sleep |
|---|---|
| SensorTrust channel rings, last valid/spike reference, invalid counts, drift streak | fault continuity |
| EMA, channel timestamp/history rings | elapsed-time change detection |
| state, ladder positions/counts, last interval | hysteresis / escalation / relaxation |
| event potential start / active flag | debounce and duration |
| last upload time, values and validity mask | heartbeat / meaningful delta |
| last admitted/reported trusted values, relevance thresholds/margins/version | control crossing continuity |
| fault signature / reminder time | no repeated fault floods |
| boot/sequence and owner/highest epoch | routing, ordering and stale-owner refusal |

A deep-sleep reboot cannot reuse raw monotonic timestamps or struct pointers. RTC retained state / NVS must have version, checksum, bounded serialization and a clock translation contract; restore configuration pointers and account for elapsed sleep. Queue drop/network failure is not a confirmed radio delivery. B telemetry remains best effort, with a bounded volatile queue and no durable end-to-end receipt.

## Field radio / gateway coordination contract — planned

Targets: ESP32-S3 + E220 for B↔A and A↔C. A1↔A2 heartbeat/ownership must have a local link independent of Internet, Cloud and Wi-Fi AP. The current host TCP `_connect_peer` is not that field adapter.

Preserve type/source/target/message_id/boot sequence/epoch across radio framing, retry and fragmentation; preserve ACK/result distinction and TTL safety. Define RF frame budget, reassembly timeout, checksum, duplicates and retry budget before implementing fragmentation. No JSON payload is assumed to fit in one radio packet.

A sleeping B need not prove online every few seconds. Gateway must distinguish expected sleep / stale measurements / missing expected report; host NODE_TIMEOUT must not be copied to field liveness. Ownership must not be inferred solely from a silent B. **B belongs to a Zone, not permanently to a Gateway.** Field uplinks use source_node_id, zone_id, sequence, boot/session id and payload. `common.field_contract.ZoneUplink` validates fixed B1/Zone1 and B2/Zone2 and gates processing on ownership of both B and its fixed C. A2 may hear B1 before takeover but cannot control C1; after takeover it can process the exact same Zone1 packet. B neither changes membership nor maintains Gateway heartbeat/health probes. TCP primary/fallback remains host integration behavior; field Zone uplinks do not require B first rebinding its destination to A2. Any adapter registration/threshold/session exchanges take place in a necessary communication window. C validates the newer owner before control. Failover latency includes B wake/report and local handshake windows; RF timing/partition safety remains untested.

### Offline command freshness — designed / host model tested

Wall-clock time supports history/logs, but is not the sole safety basis for offline control TTL. The field contract combines confirmed owner and highest epoch, Gateway boot/session, receiver boot/session, monotonic command sequence, command_id, a receiver-initiated unique receive-window challenge, local monotonic expiry and a bounded retry window. `FieldFreshnessGuard` tests this contract without any Unix clock input. Existing TCP SafetyGuard wall-time TTL is unchanged; the model is not a new LoRa codec or wire protocol.

The receiver opens a unique window **before** command arrival. The packet echoes that context; receiving a delayed packet cannot renew its own validity. Local elapsed time must satisfy both command TTL and configured retry bound. Reject old generation, non-owner, stale Gateway/receiver session, old window, replayed sequence and expired local TTL. An unknown session must be confirmed locally against persisted highest epoch; command claims never establish their own owner/session. Receiver reboot creates a new boot/session and invalidates old windows. Gateway reboot requires a new confirmed session. Offline local handshake does not require NTP. Handshake authentication, monotonic clock wrap/MCU implementation and RF latency budgets remain field work; no arbitrary replay/partition security is claimed from this host model.

Retries preserve the original command_id, sequence, sessions and receive-window context; neither endpoint rewraps an expired command in a new window. A new window permits new decisions, not deferred actuator execution of old history.

## Gateway Cloud connectivity / storage

ONLINE: Cloud session available with no replay backlog. DEGRADED: transient failure or a connected session still draining history. OFFLINE: repeated failed connection attempts/no usable Cloud link. The reconnect schedule saturates at the final configured step; deployment uses 5/15/30/60/300 seconds, unlike accelerated simulation. A successful persisted receipt or valid policy response confirms recovery. Explicit CRITICAL uploads request one early retry subject to monotonic cooldown (default 300s). This flag is preserved through telemetry/alert forwarding; no new agricultural critical-condition classifier is invented.

Upload ingestion persists before transmission. A single background flush waits for Cloud receipts; the independent upload worker continues admitting history, and local sensor/command workers continue. Reconnect triggers replay without a new sample. Replay interval is configured (deployment 0.2s per confirmed row). IDs, FIFO, at-least-once semantics and server dedup remain. Commands in the outbox are history, never deferred actuator execution.

Default outbox limits: 10,000 messages / 16 MiB serialized payload. **Critical capacity is reserved**: HIGH may use the total, NORMAL is refused when total depth/payload would consume the 1,000-row / 1,677,722-byte reserve. Both reserve values are configurable; custom smaller bounds scale the configured reserve unless explicitly supplied. HIGH includes CONTROL_RESULT, CRITICAL evidence, COMMAND_DELIVERY_FAILED, CONTROL_RESULT_TIMEOUT, GATEWAY_FAILOVER and serious SENSOR_FAULT. Routine telemetry is NORMAL; routine heartbeat remains non-durable as before. Existing databases migrate the priority column without altering IDs or FIFO.

Admission priority does not reorder replay: global FIFO (and thus FIFO within each priority), message_id, at-least-once and PERSISTED_ACK deletion remain. Repeated IDs share one outstanding row. Total capacity full explicitly rejects any new row, increments per-priority metrics and latches Gateway local CAPACITY_REJECTED state/log, also exposed in heartbeat metadata. No admitted row is evicted, especially unconfirmed HIGH/results. This bounds logical queue growth, not SQLite page/WAL/physical disk usage. New history may be lost when full without stopping local control. Priority replay, disk/WAL quota, invalid-row quarantine and power-loss endurance remain future work. Metrics/local alert latch are process-local; pre-admission application queues remain volatile.

## Host restart checkpoints — NVS pending

`StateStore` is a small two-slot SQLite checkpoint interface with canonical JSON, SHA-256 and updated_at. The same interface is intended for a future NVS backend; none is present today.

Slot identity is part of recovery validation: when slot 0 is missing but slot 1 remains, epoch and recent-command loads fail closed. They never silently select the previous slot. Only policy explicitly allows previous-slot recovery. Loss of all slots still requires the provisioning/recovery rules described below.

Policy: validate complete effective policy and version → commit checkpoint → activate. A failed write leaves the current policy/version intact. Reboot without Cloud loads last-known-good; checksum/schema/semantic corruption falls back to the previous valid policy or the safe compiled default. Direct EdgeDecider calls retain legacy partial/unversioned compatibility; Gateway SERVER_POLICY requires an explicit version and SERVER route.

Gateway: checkpoint local generation, peer generation, role and four node owners/epochs. Reload nodes as OFFLINE and start STANDBY until peer evidence resolves recovery or a formal peer timeout performs a newer-epoch takeover. Previously demoted gateways remain STANDBY on equal/stale heartbeats. Commit a takeover before notification/heartbeat publication. An epoch write/read failure disables control and peer epoch publication; it cannot fall back to an older epoch.

Controller: persist highest accepted generation/owner before simulated execution or adoption. Reboot remembers old-command rejection and conservatively restarts a full cooldown. Default actuator state is OFF in the future hardware adapter. CLI uses files; constructors without paths remain isolated, volatile test instances.

`RecentCommandStore` adds a configured bounded window (default64, schema version1): owner/epoch/TTL validation → recent-ID check → persist INTENT → execute → persist completed result → CONTROL_RESULT. A crash or result-write failure leaves a durable INTENT, which blocks repeat execution after reboot without claiming success. Result persistence failure returns UNKNOWN/STATE_UNAVAILABLE and disables further actuation in that process. Critical checksum/schema or intent-write failures fail closed; neither epoch nor recent commands falls back to a previous slot. Completed oldest entries may leave the bounded window; unresolved intents are never evicted, and a window full of unresolved intents refuses new execution. Retention beyond this window and actual actuator outcome reconciliation are not solved: no permanent across-reboot exactly-once guarantee. Field session/sequence/freshness bounds must prevent retrying commands outside the retained window. Loss/deletion of the entire file/flash cannot be distinguished from first provisioning by this abstraction and requires device provisioning/recovery rules. ESP32 mapping is NVS, still pending hardware validation.

The controller removes durably evicted completed IDs from its live SafetyGuard set after successful admission; the live and durable windows therefore have the same retention bound. Failed admission cannot remove existing IDs. Standalone SafetyGuard callers retain responsibility for their own ID retention.

Two-peer ownership is still not consensus. Arbitrary partitions, simultaneous faults and flash loss require additional field safety work, not stronger claims based on these host tests.
