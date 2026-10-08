# expired-command: FAIL

Does an expired command leave the actuator untouched?

- PASS: expired command rejected
- FAIL: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- FAIL: C1 executes trusted control
- FAIL: C2 zone continues
- FAIL: server records sensor history
