# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.168s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.411s `MESSAGE_DROPPED` nodes_to_gateway_a1 7587a92c36c5 fault=drop-first-command
- 12.009s `PROCESS_EXIT` server pid=32896 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a1 pid=32897 exit=-15
- 12.015s `PROCESS_EXIT` gateway_a2 pid=32898 exit=-15
- 12.018s `PROCESS_EXIT` sensor_b1 pid=32899 exit=-15
- 12.020s `PROCESS_EXIT` controller_c1 pid=32900 exit=-15
- 12.022s `PROCESS_EXIT` sensor_b2 pid=32901 exit=-15
- 12.024s `PROCESS_EXIT` controller_c2 pid=32902 exit=-15

## Messages

- messages received: 1059
- messages forwarded: 1058
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=32896 running=False restarts=0
- gateway_a1: pid=32897 running=False restarts=0
- gateway_a2: pid=32898 running=False restarts=0
- sensor_b1: pid=32899 running=False restarts=0
- controller_c1: pid=32900 running=False restarts=0
- sensor_b2: pid=32901 running=False restarts=0
- controller_c2: pid=32902 running=False restarts=0

## Recovery

- drop-first-command: 0.260s (disrupted at 0.411s by MESSAGE_DROPPED, recovered at 0.671s via the command is executed after the ACK timeout and retry)

Recovery time: 0.260 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.671s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
