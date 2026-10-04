# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.187s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.432s `MESSAGE_MUTATED` nodes_to_gateway_a1 c26c2811c2f1 fault=age-commands timestamp 1791088449.974344 -> 1791088419.974344
- 0.840s `MESSAGE_MUTATED` nodes_to_gateway_a1 cfb8eaf763ce fault=age-commands timestamp 1791088450.381782 -> 1791088420.381782
- 1.242s `MESSAGE_MUTATED` nodes_to_gateway_a1 10251c1d4483 fault=age-commands timestamp 1791088450.784329 -> 1791088420.784329
- 1.648s `MESSAGE_MUTATED` nodes_to_gateway_a1 2c8ec8d17279 fault=age-commands timestamp 1791088451.189597 -> 1791088421.189597
- 2.053s `MESSAGE_MUTATED` nodes_to_gateway_a1 8e9ce3c2fec5 fault=age-commands timestamp 1791088451.595565 -> 1791088421.595565
- 2.458s `MESSAGE_MUTATED` nodes_to_gateway_a1 1c8bdf5cdb94 fault=age-commands timestamp 1791088452.0001438 -> 1791088422.0001438
- 3.066s `MESSAGE_MUTATED` nodes_to_gateway_a1 ecbd5eaa20f2 fault=age-commands timestamp 1791088452.606956 -> 1791088422.606956
- 3.470s `MESSAGE_MUTATED` nodes_to_gateway_a1 00367b52a8b1 fault=age-commands timestamp 1791088453.0123782 -> 1791088423.0123782
- 4.283s `MESSAGE_MUTATED` nodes_to_gateway_a1 4e08733a2547 fault=age-commands timestamp 1791088453.82334 -> 1791088423.82334
- 4.687s `MESSAGE_MUTATED` nodes_to_gateway_a1 ab2aa92e6b7e fault=age-commands timestamp 1791088454.2285361 -> 1791088424.2285361
- 5.092s `MESSAGE_MUTATED` nodes_to_gateway_a1 d6d56ca50e4a fault=age-commands timestamp 1791088454.633836 -> 1791088424.633836
- 5.699s `MESSAGE_MUTATED` nodes_to_gateway_a1 01b3a62e71c7 fault=age-commands timestamp 1791088455.2412338 -> 1791088425.2412338
- 7.123s `MESSAGE_MUTATED` nodes_to_gateway_a1 62f4ee8527e6 fault=age-commands timestamp 1791088456.664196 -> 1791088426.664196
- 8.344s `MESSAGE_MUTATED` nodes_to_gateway_a1 313167176315 fault=age-commands timestamp 1791088457.884449 -> 1791088427.884449
- 8.747s `MESSAGE_MUTATED` nodes_to_gateway_a1 d7e5d1867060 fault=age-commands timestamp 1791088458.2887821 -> 1791088428.2887821
- 9.562s `MESSAGE_MUTATED` nodes_to_gateway_a1 4f701821af02 fault=age-commands timestamp 1791088459.102987 -> 1791088429.102987
- 10.779s `MESSAGE_MUTATED` nodes_to_gateway_a1 45f67754f4fa fault=age-commands timestamp 1791088460.319755 -> 1791088430.319755
- 11.591s `MESSAGE_MUTATED` nodes_to_gateway_a1 4238fb5a020f fault=age-commands timestamp 1791088461.132135 -> 1791088431.132135
- 11.998s `MESSAGE_MUTATED` nodes_to_gateway_a1 2362d6d700f5 fault=age-commands timestamp 1791088461.538486 -> 1791088431.538486
- 12.004s `PROCESS_EXIT` server pid=39157 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=39158 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=39159 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=39160 exit=-15
- 12.012s `PROCESS_EXIT` controller_c1 pid=39161 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b2 pid=39162 exit=-15
- 12.015s `PROCESS_EXIT` controller_c2 pid=39163 exit=-15

## Messages

- messages received: 1017
- messages forwarded: 1017
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=39157 running=False restarts=0
- gateway_a1: pid=39158 running=False restarts=0
- gateway_a2: pid=39159 running=False restarts=0
- sensor_b1: pid=39160 running=False restarts=0
- controller_c1: pid=39161 running=False restarts=0
- sensor_b2: pid=39162 running=False restarts=0
- controller_c2: pid=39163 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
