# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.163s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.374s `MESSAGE_MUTATED` nodes_to_gateway_a1 8197aa890d48 fault=age-commands timestamp 1791438566.788378 -> 1791438536.788378
- 0.576s `MESSAGE_MUTATED` nodes_to_gateway_a1 2cbce7f587b9 fault=age-commands timestamp 1791438566.99055 -> 1791438536.99055
- 0.992s `MESSAGE_MUTATED` nodes_to_gateway_a1 902a2e4eb32d fault=age-commands timestamp 1791438567.4067829 -> 1791438537.4067829
- 1.395s `MESSAGE_MUTATED` nodes_to_gateway_a1 b2a5d6cfc2b0 fault=age-commands timestamp 1791438567.8101618 -> 1791438537.8101618
- 1.801s `MESSAGE_MUTATED` nodes_to_gateway_a1 a02b7aa143f4 fault=age-commands timestamp 1791438568.2151968 -> 1791438538.2151968
- 2.205s `MESSAGE_MUTATED` nodes_to_gateway_a1 7d11a2434aca fault=age-commands timestamp 1791438568.620379 -> 1791438538.620379
- 2.609s `MESSAGE_MUTATED` nodes_to_gateway_a1 dc37d867faec fault=age-commands timestamp 1791438569.023665 -> 1791438539.023665
- 3.217s `MESSAGE_MUTATED` nodes_to_gateway_a1 09126eb7075d fault=age-commands timestamp 1791438569.631644 -> 1791438539.631644
- 3.620s `MESSAGE_MUTATED` nodes_to_gateway_a1 409a7611e229 fault=age-commands timestamp 1791438570.035014 -> 1791438540.035014
- 4.432s `MESSAGE_MUTATED` nodes_to_gateway_a1 01fa597db275 fault=age-commands timestamp 1791438570.846837 -> 1791438540.846837
- 4.838s `MESSAGE_MUTATED` nodes_to_gateway_a1 dc436ebcfce1 fault=age-commands timestamp 1791438571.252039 -> 1791438541.252039
- 5.245s `MESSAGE_MUTATED` nodes_to_gateway_a1 9e182f9e0637 fault=age-commands timestamp 1791438571.6594381 -> 1791438541.6594381
- 5.851s `MESSAGE_MUTATED` nodes_to_gateway_a1 a3567aae7815 fault=age-commands timestamp 1791438572.2657568 -> 1791438542.2657568
- 7.271s `MESSAGE_MUTATED` nodes_to_gateway_a1 d076a7e0d9f5 fault=age-commands timestamp 1791438573.686199 -> 1791438543.686199
- 8.485s `MESSAGE_MUTATED` nodes_to_gateway_a1 38ccf014e89f fault=age-commands timestamp 1791438574.899853 -> 1791438544.899853
- 8.893s `MESSAGE_MUTATED` nodes_to_gateway_a1 ff614d462871 fault=age-commands timestamp 1791438575.307325 -> 1791438545.307325
- 9.702s `MESSAGE_MUTATED` nodes_to_gateway_a1 4d516717a84d fault=age-commands timestamp 1791438576.116677 -> 1791438546.116677
- 10.921s `MESSAGE_MUTATED` nodes_to_gateway_a1 9b94a29c6b40 fault=age-commands timestamp 1791438577.334663 -> 1791438547.334663
- 11.728s `MESSAGE_MUTATED` nodes_to_gateway_a1 2acfbb3ac91b fault=age-commands timestamp 1791438578.1430469 -> 1791438548.1430469
- 12.009s `PROCESS_EXIT` server pid=47524 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a1 pid=47525 exit=-15
- 12.013s `PROCESS_EXIT` gateway_a2 pid=47526 exit=-15
- 12.015s `PROCESS_EXIT` sensor_b1 pid=47527 exit=-15
- 12.017s `PROCESS_EXIT` controller_c1 pid=47528 exit=-15
- 12.019s `PROCESS_EXIT` sensor_b2 pid=47529 exit=-15
- 12.020s `PROCESS_EXIT` controller_c2 pid=47530 exit=-15

## Messages

- messages received: 1060
- messages forwarded: 1060
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=47524 running=False restarts=0
- gateway_a1: pid=47525 running=False restarts=0
- gateway_a2: pid=47526 running=False restarts=0
- sensor_b1: pid=47527 running=False restarts=0
- controller_c1: pid=47528 running=False restarts=0
- sensor_b2: pid=47529 running=False restarts=0
- controller_c2: pid=47530 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
