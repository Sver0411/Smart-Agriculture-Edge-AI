# split-brain: PASS

Does a controller reject a non-owner at the same epoch?

- PASS: non-owner cannot execute
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
