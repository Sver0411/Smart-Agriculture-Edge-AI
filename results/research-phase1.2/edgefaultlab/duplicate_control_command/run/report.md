# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.042s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.342s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 160dc5a8d8be fault=duplicate-command copies=1
- 2.949s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 615e711ad039 fault=duplicate-command copies=1
- 3.353s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 d3497f53db9b fault=duplicate-command copies=1
- 12.006s `PROCESS_EXIT` server pid=49759 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=49760 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=49761 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=49762 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=49763 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=49764 exit=-15
- 12.014s `PROCESS_EXIT` controller_c2 pid=49765 exit=-15

## Messages

- messages received: 1090
- messages forwarded: 1093
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=49759 running=False restarts=0
- gateway_a1: pid=49760 running=False restarts=0
- gateway_a2: pid=49761 running=False restarts=0
- sensor_b1: pid=49762 running=False restarts=0
- controller_c1: pid=49763 running=False restarts=0
- sensor_b2: pid=49764 running=False restarts=0
- controller_c2: pid=49765 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 20 distinct payload.command_id value(s) in 20 matching message(s)
PASS commands still run at all - observed 20 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
