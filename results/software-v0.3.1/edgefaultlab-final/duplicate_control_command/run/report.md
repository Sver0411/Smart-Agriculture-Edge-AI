# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.052s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.367s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 3c2f35a0c9f3 fault=duplicate-command copies=1
- 2.972s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 74f3dca81345 fault=duplicate-command copies=1
- 3.378s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 a312a1b5d9b9 fault=duplicate-command copies=1
- 12.007s `PROCESS_EXIT` server pid=34703 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=34704 exit=-15
- 12.014s `PROCESS_EXIT` gateway_a2 pid=34705 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b1 pid=34706 exit=-15
- 12.018s `PROCESS_EXIT` controller_c1 pid=34707 exit=-15
- 12.020s `PROCESS_EXIT` sensor_b2 pid=34708 exit=-15
- 12.022s `PROCESS_EXIT` controller_c2 pid=34709 exit=-15

## Messages

- messages received: 1088
- messages forwarded: 1091
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=34703 running=False restarts=0
- gateway_a1: pid=34704 running=False restarts=0
- gateway_a2: pid=34705 running=False restarts=0
- sensor_b1: pid=34706 running=False restarts=0
- controller_c1: pid=34707 running=False restarts=0
- sensor_b2: pid=34708 running=False restarts=0
- controller_c2: pid=34709 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 20 distinct payload.command_id value(s) in 20 matching message(s)
PASS commands still run at all - observed 20 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
