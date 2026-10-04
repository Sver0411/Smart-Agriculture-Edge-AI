# gateway-recovery: PASS

Does recovered A1 enter STANDBY?

- PASS: A2 peer A1 OFFLINE
- PASS: ownership epoch synchronized across A2/B1/C1
- PASS: B1 and C1 owner A2
- PASS: deposed command rejected
- PASS: recovered gateway standby
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
