# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.142s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.350s `MESSAGE_DROPPED` nodes_to_gateway_a1 9b938b9b4a4d fault=drop-first-command
- 12.007s `PROCESS_EXIT` server pid=92998 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=92999 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a2 pid=93000 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b1 pid=93001 exit=-15
- 12.020s `PROCESS_EXIT` controller_c1 pid=93002 exit=-15
- 12.031s `PROCESS_EXIT` sensor_b2 pid=93003 exit=-15
- 12.033s `PROCESS_EXIT` controller_c2 pid=93004 exit=-15

## Messages

- messages received: 1070
- messages forwarded: 1069
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=92998 running=False restarts=0
- gateway_a1: pid=92999 running=False restarts=0
- gateway_a2: pid=93000 running=False restarts=0
- sensor_b1: pid=93001 running=False restarts=0
- controller_c1: pid=93002 running=False restarts=0
- sensor_b2: pid=93003 running=False restarts=0
- controller_c2: pid=93004 running=False restarts=0

## Recovery

- drop-first-command: 0.255s (disrupted at 0.350s by MESSAGE_DROPPED, recovered at 0.606s via the command is executed after the ACK timeout and retry)

Recovery time: 0.255 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.606s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
