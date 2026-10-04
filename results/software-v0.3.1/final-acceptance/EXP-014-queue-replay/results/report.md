# queue-replay: PASS

Do 250 queued messages replay without any new telemetry trigger?

- PASS: history queued durably
- PASS: local control executes during outage
- PASS: all offline queues drained
- PASS: 250 logical queued samples stored
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
