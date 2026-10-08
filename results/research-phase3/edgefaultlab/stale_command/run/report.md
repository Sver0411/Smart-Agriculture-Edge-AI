# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.120s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.130s `MESSAGE_MUTATED` nodes_to_gateway_a1 63bda5c1333c fault=age-commands timestamp 1791477620.213305 -> 1791477590.213305
- 0.333s `MESSAGE_MUTATED` nodes_to_gateway_a1 d9e7793b529a fault=age-commands timestamp 1791477620.415651 -> 1791477590.415651
- 0.736s `MESSAGE_MUTATED` nodes_to_gateway_a1 34eec36af685 fault=age-commands timestamp 1791477620.8194292 -> 1791477590.8194292
- 1.140s `MESSAGE_MUTATED` nodes_to_gateway_a1 98fffea1951b fault=age-commands timestamp 1791477621.223177 -> 1791477591.223177
- 1.543s `MESSAGE_MUTATED` nodes_to_gateway_a1 4c5f8000db84 fault=age-commands timestamp 1791477621.625607 -> 1791477591.625607
- 1.947s `MESSAGE_MUTATED` nodes_to_gateway_a1 96b937b418c0 fault=age-commands timestamp 1791477622.0302458 -> 1791477592.0302458
- 2.351s `MESSAGE_MUTATED` nodes_to_gateway_a1 4e38ec302031 fault=age-commands timestamp 1791477622.4337761 -> 1791477592.4337761
- 2.959s `MESSAGE_MUTATED` nodes_to_gateway_a1 9817794cf700 fault=age-commands timestamp 1791477623.041804 -> 1791477593.041804
- 3.362s `MESSAGE_MUTATED` nodes_to_gateway_a1 00622cb36774 fault=age-commands timestamp 1791477623.445199 -> 1791477593.445199
- 4.170s `MESSAGE_MUTATED` nodes_to_gateway_a1 eada3a81f757 fault=age-commands timestamp 1791477624.2526562 -> 1791477594.2526562
- 4.573s `MESSAGE_MUTATED` nodes_to_gateway_a1 6cf58a71368f fault=age-commands timestamp 1791477624.655683 -> 1791477594.655683
- 4.976s `MESSAGE_MUTATED` nodes_to_gateway_a1 b7450bb5ad9d fault=age-commands timestamp 1791477625.058798 -> 1791477595.058798
- 5.608s `MESSAGE_MUTATED` nodes_to_gateway_a1 e2ccdf4f3f61 fault=age-commands timestamp 1791477625.667381 -> 1791477595.667381
- 7.001s `MESSAGE_MUTATED` nodes_to_gateway_a1 e46fe1fa2d6b fault=age-commands timestamp 1791477627.0834298 -> 1791477597.0834298
- 8.213s `MESSAGE_MUTATED` nodes_to_gateway_a1 d10766d7051f fault=age-commands timestamp 1791477628.295851 -> 1791477598.295851
- 8.616s `MESSAGE_MUTATED` nodes_to_gateway_a1 1da7469e92fb fault=age-commands timestamp 1791477628.699332 -> 1791477598.699332
- 9.426s `MESSAGE_MUTATED` nodes_to_gateway_a1 039b28ccc6b2 fault=age-commands timestamp 1791477629.508296 -> 1791477599.508296
- 10.639s `MESSAGE_MUTATED` nodes_to_gateway_a1 d83a17377a31 fault=age-commands timestamp 1791477630.721866 -> 1791477600.721866
- 11.451s `MESSAGE_MUTATED` nodes_to_gateway_a1 671d486163d0 fault=age-commands timestamp 1791477631.532913 -> 1791477601.532913
- 11.855s `MESSAGE_MUTATED` nodes_to_gateway_a1 046b95ffc7de fault=age-commands timestamp 1791477631.937665 -> 1791477601.937665
- 12.005s `PROCESS_EXIT` server pid=11146 exit=-15
- 12.006s `PROCESS_EXIT` gateway_a1 pid=11147 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a2 pid=11148 exit=-15
- 12.009s `PROCESS_EXIT` sensor_b1 pid=11149 exit=-15
- 12.010s `PROCESS_EXIT` controller_c1 pid=11150 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b2 pid=11151 exit=-15
- 12.012s `PROCESS_EXIT` controller_c2 pid=11152 exit=-15

## Messages

- messages received: 1084
- messages forwarded: 1084
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 20
- malformed messages: 0
- messages too large: 0
- messages matched: 20

## Processes

- server: pid=11146 running=False restarts=0
- gateway_a1: pid=11147 running=False restarts=0
- gateway_a2: pid=11148 running=False restarts=0
- sensor_b1: pid=11149 running=False restarts=0
- controller_c1: pid=11150 running=False restarts=0
- sensor_b2: pid=11151 running=False restarts=0
- controller_c2: pid=11152 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 20 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
