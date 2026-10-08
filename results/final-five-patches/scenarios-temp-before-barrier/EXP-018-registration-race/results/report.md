# registration-race: FAIL

Do B1/C1 contact A2 first, receive NOT_OWNER, then establish correct ownership at A1 without startup delays?

- PASS: A2 explicitly rejects B1 and C1 before takeover
- FAIL: correct B1/C1 initial owner at A1
- FAIL: registration does not bump initial epoch
- PASS: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
