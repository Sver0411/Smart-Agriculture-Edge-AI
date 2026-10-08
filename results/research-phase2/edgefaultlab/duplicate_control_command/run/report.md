# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.089s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.184s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 c3b804093b0a fault=duplicate-command copies=1
- 2.587s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 c68668d8e3a3 fault=duplicate-command copies=1
- 3.204s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 abd2e40d928c fault=duplicate-command copies=1
- 12.006s `PROCESS_EXIT` server pid=75232 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=75233 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=75234 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=75235 exit=-15
- 12.012s `PROCESS_EXIT` controller_c1 pid=75236 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=75237 exit=-15
- 12.014s `PROCESS_EXIT` controller_c2 pid=75238 exit=-15

## Messages

- messages received: 1076
- messages forwarded: 1079
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=75232 running=False restarts=0
- gateway_a1: pid=75233 running=False restarts=0
- gateway_a2: pid=75234 running=False restarts=0
- sensor_b1: pid=75235 running=False restarts=0
- controller_c1: pid=75236 running=False restarts=0
- sensor_b2: pid=75237 running=False restarts=0
- controller_c2: pid=75238 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS commands still run at all - observed 18 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
