# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.132s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.331s `MESSAGE_DROPPED` nodes_to_gateway_a1 d17cb5b2bff9 fault=drop-first-command
- 12.006s `PROCESS_EXIT` server pid=50209 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=50210 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a2 pid=50211 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=50212 exit=-15
- 12.013s `PROCESS_EXIT` controller_c1 pid=50213 exit=-15
- 12.015s `PROCESS_EXIT` sensor_b2 pid=50214 exit=-15
- 12.016s `PROCESS_EXIT` controller_c2 pid=50215 exit=-15

## Messages

- messages received: 1076
- messages forwarded: 1075
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=50209 running=False restarts=0
- gateway_a1: pid=50210 running=False restarts=0
- gateway_a2: pid=50211 running=False restarts=0
- sensor_b1: pid=50212 running=False restarts=0
- controller_c1: pid=50213 running=False restarts=0
- sensor_b2: pid=50214 running=False restarts=0
- controller_c2: pid=50215 running=False restarts=0

## Recovery

- drop-first-command: 0.261s (disrupted at 0.331s by MESSAGE_DROPPED, recovered at 0.592s via the command is executed after the ACK timeout and retry)

Recovery time: 0.261 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.592s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
