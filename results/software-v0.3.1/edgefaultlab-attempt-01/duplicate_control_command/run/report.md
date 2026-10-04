# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.064s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.364s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 a7c42c873cfa fault=duplicate-command copies=1
- 2.970s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 262c94a1d74e fault=duplicate-command copies=1
- 3.376s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 eab446301617 fault=duplicate-command copies=1
- 12.006s `PROCESS_EXIT` server pid=32677 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=32678 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a2 pid=32679 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b1 pid=32680 exit=-15
- 12.015s `PROCESS_EXIT` controller_c1 pid=32681 exit=-15
- 12.017s `PROCESS_EXIT` sensor_b2 pid=32682 exit=-15
- 12.018s `PROCESS_EXIT` controller_c2 pid=32683 exit=-15

## Messages

- messages received: 1084
- messages forwarded: 1087
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=32677 running=False restarts=0
- gateway_a1: pid=32678 running=False restarts=0
- gateway_a2: pid=32679 running=False restarts=0
- sensor_b1: pid=32680 running=False restarts=0
- controller_c1: pid=32681 running=False restarts=0
- sensor_b2: pid=32682 running=False restarts=0
- controller_c2: pid=32683 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 20 distinct payload.command_id value(s) in 20 matching message(s)
PASS commands still run at all - observed 20 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
