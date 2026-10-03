# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.198s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.695s `MESSAGE_MUTATED` nodes_to_gateway_a1 d11d33f64ce5 fault=age-commands timestamp 1791048745.237293 -> 1791048715.237293
- 0.897s `MESSAGE_MUTATED` nodes_to_gateway_a1 66c4035567c5 fault=age-commands timestamp 1791048745.4397628 -> 1791048715.4397628
- 1.302s `MESSAGE_MUTATED` nodes_to_gateway_a1 202d58908f12 fault=age-commands timestamp 1791048745.8443918 -> 1791048715.8443918
- 1.707s `MESSAGE_MUTATED` nodes_to_gateway_a1 2f160d2a3e8f fault=age-commands timestamp 1791048746.2495072 -> 1791048716.2495072
- 2.112s `MESSAGE_MUTATED` nodes_to_gateway_a1 d37555ca1cff fault=age-commands timestamp 1791048746.654073 -> 1791048716.654073
- 2.516s `MESSAGE_MUTATED` nodes_to_gateway_a1 b8929ab2c9a7 fault=age-commands timestamp 1791048747.0581381 -> 1791048717.0581381
- 2.918s `MESSAGE_MUTATED` nodes_to_gateway_a1 70b40854884f fault=age-commands timestamp 1791048747.460358 -> 1791048717.460358
- 3.524s `MESSAGE_MUTATED` nodes_to_gateway_a1 d3843e84f25c fault=age-commands timestamp 1791048748.0666182 -> 1791048718.0666182
- 3.929s `MESSAGE_MUTATED` nodes_to_gateway_a1 196c4a7a608c fault=age-commands timestamp 1791048748.471602 -> 1791048718.471602
- 4.737s `MESSAGE_MUTATED` nodes_to_gateway_a1 0ad570896304 fault=age-commands timestamp 1791048749.279178 -> 1791048719.279178
- 5.143s `MESSAGE_MUTATED` nodes_to_gateway_a1 0b66a3b78aa0 fault=age-commands timestamp 1791048749.6849332 -> 1791048719.6849332
- 5.549s `MESSAGE_MUTATED` nodes_to_gateway_a1 433701852578 fault=age-commands timestamp 1791048750.0904279 -> 1791048720.0904279
- 6.157s `MESSAGE_MUTATED` nodes_to_gateway_a1 c6617a2e97ff fault=age-commands timestamp 1791048750.6985989 -> 1791048720.6985989
- 7.577s `MESSAGE_MUTATED` nodes_to_gateway_a1 4e5ede43df83 fault=age-commands timestamp 1791048752.1182039 -> 1791048722.1182039
- 8.791s `MESSAGE_MUTATED` nodes_to_gateway_a1 e29804ff6ea9 fault=age-commands timestamp 1791048753.333311 -> 1791048723.333311
- 9.197s `MESSAGE_MUTATED` nodes_to_gateway_a1 9dddcd2b5590 fault=age-commands timestamp 1791048753.738653 -> 1791048723.738653
- 10.008s `MESSAGE_MUTATED` nodes_to_gateway_a1 c29804cc1992 fault=age-commands timestamp 1791048754.549533 -> 1791048724.549533
- 11.225s `MESSAGE_MUTATED` nodes_to_gateway_a1 722c16624a72 fault=age-commands timestamp 1791048755.766527 -> 1791048725.766527
- 12.006s `PROCESS_EXIT` server pid=27336 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=27337 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a2 pid=27338 exit=-15
- 12.012s `PROCESS_EXIT` sensor_b1 pid=27339 exit=-15
- 12.014s `PROCESS_EXIT` controller_c1 pid=27340 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b2 pid=27341 exit=-15
- 12.017s `PROCESS_EXIT` controller_c2 pid=27342 exit=-15

## Messages

- messages received: 936
- messages forwarded: 936
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 18
- malformed messages: 0
- messages too large: 0
- messages matched: 18

## Processes

- server: pid=27336 running=False restarts=0
- gateway_a1: pid=27337 running=False restarts=0
- gateway_a2: pid=27338 running=False restarts=0
- sensor_b1: pid=27339 running=False restarts=0
- controller_c1: pid=27340 running=False restarts=0
- sensor_b2: pid=27341 running=False restarts=0
- controller_c2: pid=27342 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 18 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
