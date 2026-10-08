# queue-replay: FAIL

Do 250 queued messages replay without any new telemetry trigger?

- PASS: history queued durably
- PASS: local control executes during outage
- PASS: all offline queues drained
- PASS: 250 logical queued samples stored
- FAIL: scenario runs without exception
