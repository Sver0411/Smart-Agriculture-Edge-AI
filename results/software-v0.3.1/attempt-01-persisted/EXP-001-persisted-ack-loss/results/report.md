# persisted-ack-loss: PASS

Does a committed upload retain its gateway copy after a lost persisted ACK and replay to one business row?

- PASS: committed receipt was dropped
- PASS: server deduplicates replay after ACK loss
- PASS: acknowledged row removed
- PASS: one committed business row for lost receipt
- PASS: row retained at moment of dropped ACK
- PASS: no logical command reported executed twice on control link
- PASS: both sensor zones sampled
- PASS: C1 executes trusted control
- PASS: C2 zone continues
- PASS: server records sensor history
- PASS: planned frame fault exercised
