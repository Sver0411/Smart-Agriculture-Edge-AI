# persisted-ack-loss: FAIL

Does a committed upload retain its gateway copy after a lost persisted ACK and replay to one business row?

- PASS: committed receipt was dropped
- PASS: server deduplicates replay after ACK loss
- PASS: acknowledged row removed
- PASS: one committed business row for lost receipt
- PASS: row retained at moment of dropped ACK
- PASS: dedup row committed before dropped ACK
- FAIL: scenario runs without exception
