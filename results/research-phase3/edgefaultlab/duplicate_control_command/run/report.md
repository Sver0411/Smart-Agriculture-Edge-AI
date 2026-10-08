# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.059s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.359s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 416aac7310dd fault=duplicate-command copies=1
- 2.963s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 1cdb86b041b9 fault=duplicate-command copies=1
- 3.367s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 c482f172fbe8 fault=duplicate-command copies=1
- 12.005s `PROCESS_EXIT` server pid=11010 exit=-15
- 12.006s `PROCESS_EXIT` gateway_a1 pid=11011 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=11012 exit=-15
- 12.009s `PROCESS_EXIT` sensor_b1 pid=11013 exit=-15
- 12.010s `PROCESS_EXIT` controller_c1 pid=11014 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b2 pid=11015 exit=-15
- 12.012s `PROCESS_EXIT` controller_c2 pid=11016 exit=-15

## Messages

- messages received: 1095
- messages forwarded: 1098
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=11010 running=False restarts=0
- gateway_a1: pid=11011 running=False restarts=0
- gateway_a2: pid=11012 running=False restarts=0
- sensor_b1: pid=11013 running=False restarts=0
- controller_c1: pid=11014 running=False restarts=0
- sensor_b2: pid=11015 running=False restarts=0
- controller_c2: pid=11016 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 20 distinct payload.command_id value(s) in 20 matching message(s)
PASS commands still run at all - observed 20 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
