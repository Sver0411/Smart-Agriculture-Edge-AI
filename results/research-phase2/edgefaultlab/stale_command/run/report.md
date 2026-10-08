# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.113s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.320s `MESSAGE_MUTATED` nodes_to_gateway_a1 24678a1eb6f9 fault=age-commands timestamp 1791476409.089979 -> 1791476379.089979
- 0.722s `MESSAGE_MUTATED` nodes_to_gateway_a1 9d2dfe301d25 fault=age-commands timestamp 1791476409.492511 -> 1791476379.492511
- 1.127s `MESSAGE_MUTATED` nodes_to_gateway_a1 9e95f275c7e9 fault=age-commands timestamp 1791476409.896242 -> 1791476379.896242
- 1.528s `MESSAGE_MUTATED` nodes_to_gateway_a1 96c42bdc3073 fault=age-commands timestamp 1791476410.29833 -> 1791476380.29833
- 1.932s `MESSAGE_MUTATED` nodes_to_gateway_a1 dc9e0bb838e7 fault=age-commands timestamp 1791476410.702467 -> 1791476380.702467
- 2.336s `MESSAGE_MUTATED` nodes_to_gateway_a1 f44ea2a91540 fault=age-commands timestamp 1791476411.105945 -> 1791476381.105945
- 2.939s `MESSAGE_MUTATED` nodes_to_gateway_a1 d6d774c2bdd1 fault=age-commands timestamp 1791476411.710253 -> 1791476381.710253
- 3.343s `MESSAGE_MUTATED` nodes_to_gateway_a1 b8de5204726d fault=age-commands timestamp 1791476412.113575 -> 1791476382.113575
- 4.148s `MESSAGE_MUTATED` nodes_to_gateway_a1 ce837043a951 fault=age-commands timestamp 1791476412.919025 -> 1791476382.919025
- 4.555s `MESSAGE_MUTATED` nodes_to_gateway_a1 fce3416dc55e fault=age-commands timestamp 1791476413.3249779 -> 1791476383.3249779
- 4.959s `MESSAGE_MUTATED` nodes_to_gateway_a1 1797fe995b35 fault=age-commands timestamp 1791476413.729353 -> 1791476383.729353
- 5.565s `MESSAGE_MUTATED` nodes_to_gateway_a1 abf9ab5ad68a fault=age-commands timestamp 1791476414.3354251 -> 1791476384.3354251
- 6.977s `MESSAGE_MUTATED` nodes_to_gateway_a1 938eac57129e fault=age-commands timestamp 1791476415.747204 -> 1791476385.747204
- 8.186s `MESSAGE_MUTATED` nodes_to_gateway_a1 9153935614e7 fault=age-commands timestamp 1791476416.956836 -> 1791476386.956836
- 8.590s `MESSAGE_MUTATED` nodes_to_gateway_a1 53160ea684f8 fault=age-commands timestamp 1791476417.360301 -> 1791476387.360301
- 9.398s `MESSAGE_MUTATED` nodes_to_gateway_a1 d8f1f0cf96b7 fault=age-commands timestamp 1791476418.168652 -> 1791476388.168652
- 10.609s `MESSAGE_MUTATED` nodes_to_gateway_a1 8e85879f03eb fault=age-commands timestamp 1791476419.379801 -> 1791476389.379801
- 11.416s `MESSAGE_MUTATED` nodes_to_gateway_a1 1450184d4df4 fault=age-commands timestamp 1791476420.1867368 -> 1791476390.1867368
- 11.819s `MESSAGE_MUTATED` nodes_to_gateway_a1 04e51e275441 fault=age-commands timestamp 1791476420.589387 -> 1791476390.589387
- 12.005s `PROCESS_EXIT` server pid=75466 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=75467 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=75468 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=75469 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=75470 exit=-15
- 12.012s `PROCESS_EXIT` sensor_b2 pid=75471 exit=-15
- 12.014s `PROCESS_EXIT` controller_c2 pid=75472 exit=-15

## Messages

- messages received: 1084
- messages forwarded: 1084
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=75466 running=False restarts=0
- gateway_a1: pid=75467 running=False restarts=0
- gateway_a2: pid=75468 running=False restarts=0
- sensor_b1: pid=75469 running=False restarts=0
- controller_c1: pid=75470 running=False restarts=0
- sensor_b2: pid=75471 running=False restarts=0
- controller_c2: pid=75472 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
