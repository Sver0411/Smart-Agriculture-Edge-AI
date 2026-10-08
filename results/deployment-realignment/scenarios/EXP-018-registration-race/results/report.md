# registration-race: FAIL

Do B1/C1 contact A2 first, receive NOT_OWNER, then establish correct ownership at A1 without startup delays?

- PASS: A2 explicitly rejects B1 and C1 before takeover
- PASS: correct B1/C1 initial owner at A1
- PASS: registration does not bump initial epoch
- FAIL: scenario runs without exception
