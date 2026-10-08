# lost-result: FAIL

Does missing CONTROL_RESULT remain explicitly UNKNOWN without blind reexecution?

- PASS: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- FAIL: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
- FAIL: planned frame fault exercised
- FAIL: missing result is UNKNOWN
