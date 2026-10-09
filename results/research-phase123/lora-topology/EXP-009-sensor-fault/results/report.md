# sensor-fault: PASS

Does a broken B1 channel block C1 while the other zone continues?

- PASS: every sensor command preserves fixed zone membership
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 never executes on faulty B1
- PASS: fault evidence stored
- PASS: C2 zone continues
- PASS: server records sensor history
