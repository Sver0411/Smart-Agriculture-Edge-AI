# controller-unavailable: FAIL

Is unavailable C1 reported NOT_DISPATCHED, with no old command executed after reconnection?

- FAIL: server records unavailable controller outcome
- PASS: offline controller executes zero commands
- PASS: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- FAIL: C1 really reconnects after offline decision
- PASS: reconnected C1 never executes old undispatched command
- PASS: no unavailable command is later dispatched
- PASS: C2 zone continues
- FAIL: server records sensor history
