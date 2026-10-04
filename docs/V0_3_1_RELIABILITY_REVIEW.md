# v0.3.1 code review before hardening

Reviewed main `3697494` on 2026-10-04: README, v0.3 integration report, gateway/registry/ownership/offline queue, sensor/controller session and safety, server storage/dedup, protocol/reliability, experiment recorder/runner/EdgeFaultLab adapter, existing tests and recent Actions runs. Main acceptance run 37142688673 passed 155 tests, 17 internal scenarios and 5 external scenarios. Local baseline also passed 155 tests in 39.55s.

Confirmed issues:

- `_handle_register` overwrites seeded ownership; the inbound handler also admits node traffic without accepted registration. Controller `_register` does not check `accepted`. A remembered owner can be replaced at the same epoch.
- Dispatch has silent early returns for unavailable controller and lost ownership. Queuing actuator commands for later execution would be unsafe.
- Both online delivery and offline replay use TCP drain as success. Replay deletes before SQLite receipt. Reading receipt and flushing on the same coroutine would deadlock; receive must remain independent.
- Server sensor validation is partial; command/result/alert/heartbeat fallbacks can persist malformed business records. ACK/policy are mixed with durable upload dedup.
- Global sample quality blocks independent rule actions; learned features genuinely require all four inputs.
- Sensor alerts repeat every suspect sample. TransportRecorder attributes repeated delivery to first sent time, mixing logical and attempt latency.
- Peer, node expiry and command ACK timers use wall time. Result expiry and sampling already use monotonic time. TTL and audit timestamps need wall time.
- README claims Python 3.10+, CI runs 3.12 only. Local interpreter is 3.14; supported versions must be confirmed remotely.

Plan: ownership-aware registration and explicit rejection/redirect, explicit non-dispatch outcomes, message-specific semantic validation before dedup, separate PERSISTED_ACK after transaction commit and a durable outbox for every queueable upload, action dependency gates with strict learned-input gating, fault transition/reminder alerts, monotonic duration clocks and separate latency metrics. Preserve existing evidence and architecture. Add deterministic protocol regression tests and three complete-topology scenarios; remove ownership startup delays from the external adapter. Keep EdgeFaultLab independent at pinned c7248239f456cc877114ca1e67c5949fb4a7b958. No device actions.

Remaining design boundaries: two gateways are not consensus; no authentication; controller epochs and actuator IDs are volatile; command TTL requires synchronized wall clocks; synthetic models are not validated agriculture models. New durable receipts do not imply exactly-once actuators.
