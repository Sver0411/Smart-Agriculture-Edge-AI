# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.128s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.332s `MESSAGE_MUTATED` nodes_to_gateway_a1 2c266d1f955e fault=age-commands timestamp 1791466137.5257978 -> 1791466107.5257978
- 0.535s `MESSAGE_MUTATED` nodes_to_gateway_a1 eb6f6b39d993 fault=age-commands timestamp 1791466137.7281952 -> 1791466107.7281952
- 0.939s `MESSAGE_MUTATED` nodes_to_gateway_a1 0c172e94bdc3 fault=age-commands timestamp 1791466138.132341 -> 1791466108.132341
- 1.344s `MESSAGE_MUTATED` nodes_to_gateway_a1 cf06bc298c09 fault=age-commands timestamp 1791466138.5369558 -> 1791466108.5369558
- 1.748s `MESSAGE_MUTATED` nodes_to_gateway_a1 d583f2302c6c fault=age-commands timestamp 1791466138.9412348 -> 1791466108.9412348
- 2.151s `MESSAGE_MUTATED` nodes_to_gateway_a1 229ddf34b4e1 fault=age-commands timestamp 1791466139.344322 -> 1791466109.344322
- 2.553s `MESSAGE_MUTATED` nodes_to_gateway_a1 26b54cfad3bb fault=age-commands timestamp 1791466139.746714 -> 1791466109.746714
- 3.158s `MESSAGE_MUTATED` nodes_to_gateway_a1 4199abfe6d88 fault=age-commands timestamp 1791466140.3515499 -> 1791466110.3515499
- 3.562s `MESSAGE_MUTATED` nodes_to_gateway_a1 bbbb6e87a2a7 fault=age-commands timestamp 1791466140.75572 -> 1791466110.75572
- 4.372s `MESSAGE_MUTATED` nodes_to_gateway_a1 5bd894de2b6c fault=age-commands timestamp 1791466141.565345 -> 1791466111.565345
- 4.778s `MESSAGE_MUTATED` nodes_to_gateway_a1 d8767e106c5f fault=age-commands timestamp 1791466141.970808 -> 1791466111.970808
- 5.182s `MESSAGE_MUTATED` nodes_to_gateway_a1 ebefbf7de73d fault=age-commands timestamp 1791466142.374666 -> 1791466112.374666
- 5.787s `MESSAGE_MUTATED` nodes_to_gateway_a1 d702ae2ee48f fault=age-commands timestamp 1791466142.980448 -> 1791466112.980448
- 7.202s `MESSAGE_MUTATED` nodes_to_gateway_a1 bfb07f6bbfc6 fault=age-commands timestamp 1791466144.395374 -> 1791466114.395374
- 8.416s `MESSAGE_MUTATED` nodes_to_gateway_a1 4fdcc63e3a61 fault=age-commands timestamp 1791466145.6095529 -> 1791466115.6095529
- 8.820s `MESSAGE_MUTATED` nodes_to_gateway_a1 2b4154e9276d fault=age-commands timestamp 1791466146.01348 -> 1791466116.01348
- 9.631s `MESSAGE_MUTATED` nodes_to_gateway_a1 bc9fca8e09bd fault=age-commands timestamp 1791466146.824311 -> 1791466116.824311
- 10.847s `MESSAGE_MUTATED` nodes_to_gateway_a1 8d28b17519e8 fault=age-commands timestamp 1791466148.039669 -> 1791466118.039669
- 11.655s `MESSAGE_MUTATED` nodes_to_gateway_a1 435885e863c7 fault=age-commands timestamp 1791466148.84846 -> 1791466118.84846
- 12.005s `PROCESS_EXIT` server pid=50001 exit=-15
- 12.006s `PROCESS_EXIT` gateway_a1 pid=50002 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=50003 exit=-15
- 12.009s `PROCESS_EXIT` sensor_b1 pid=50004 exit=-15
- 12.010s `PROCESS_EXIT` controller_c1 pid=50005 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b2 pid=50006 exit=-15
- 12.012s `PROCESS_EXIT` controller_c2 pid=50007 exit=-15

## Messages

- messages received: 1072
- messages forwarded: 1072
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=50001 running=False restarts=0
- gateway_a1: pid=50002 running=False restarts=0
- gateway_a2: pid=50003 running=False restarts=0
- sensor_b1: pid=50004 running=False restarts=0
- controller_c1: pid=50005 running=False restarts=0
- sensor_b2: pid=50006 running=False restarts=0
- controller_c2: pid=50007 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
