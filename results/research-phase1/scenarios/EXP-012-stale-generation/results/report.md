# stale-generation: PASS

Does a command from a deposed epoch remain rejected?

- PASS: A2 peer A1 OFFLINE
- PASS: ownership epoch synchronized across A2/B1/C1
- PASS: B1 and C1 owner A2
- PASS: deposed command rejected
- PASS: every sensor command preserves fixed zone membership
- PASS: A2 drives C1 from B1 after takeover
- PASS: A2 continues driving C2 from B2
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
