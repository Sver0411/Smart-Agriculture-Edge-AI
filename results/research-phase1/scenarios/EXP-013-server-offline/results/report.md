# server-offline: PASS

Does edge control continue and history replay after cloud recovery?

- PASS: history queued durably
- PASS: local control executes during outage
- PASS: all offline queues drained
- PASS: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
