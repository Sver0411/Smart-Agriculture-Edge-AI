# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.012s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.093s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 bc6e43692c5e fault=duplicate-command copies=1
- 2.499s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 7f2022dc3b16 fault=duplicate-command copies=1
- 2.905s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 081eb333175d fault=duplicate-command copies=1
- 12.008s `PROCESS_EXIT` server pid=27250 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=27251 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a2 pid=27252 exit=-15
- 12.015s `PROCESS_EXIT` sensor_b1 pid=27253 exit=-15
- 12.017s `PROCESS_EXIT` controller_c1 pid=27254 exit=-15
- 12.019s `PROCESS_EXIT` sensor_b2 pid=27255 exit=-15
- 12.020s `PROCESS_EXIT` controller_c2 pid=27256 exit=-15

## Messages

- messages received: 944
- messages forwarded: 947
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=27250 running=False restarts=0
- gateway_a1: pid=27251 running=False restarts=0
- gateway_a2: pid=27252 running=False restarts=0
- sensor_b1: pid=27253 running=False restarts=0
- controller_c1: pid=27254 running=False restarts=0
- sensor_b2: pid=27255 running=False restarts=0
- controller_c2: pid=27256 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS commands still run at all - observed 18 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
