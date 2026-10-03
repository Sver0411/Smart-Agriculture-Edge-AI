# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.214s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.411s `MESSAGE_DROPPED` nodes_to_gateway_a1 f638bedbaa58 fault=drop-first-command
- 12.008s `PROCESS_EXIT` server pid=26759 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a1 pid=26760 exit=-15
- 12.013s `PROCESS_EXIT` gateway_a2 pid=26761 exit=-15
- 12.015s `PROCESS_EXIT` sensor_b1 pid=26762 exit=-15
- 12.018s `PROCESS_EXIT` controller_c1 pid=26763 exit=-15
- 12.020s `PROCESS_EXIT` sensor_b2 pid=26764 exit=-15
- 12.022s `PROCESS_EXIT` controller_c2 pid=26765 exit=-15

## Messages

- messages received: 953
- messages forwarded: 952
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=26759 running=False restarts=0
- gateway_a1: pid=26760 running=False restarts=0
- gateway_a2: pid=26761 running=False restarts=0
- sensor_b1: pid=26762 running=False restarts=0
- controller_c1: pid=26763 running=False restarts=0
- sensor_b2: pid=26764 running=False restarts=0
- controller_c2: pid=26765 running=False restarts=0

## Recovery

- drop-first-command: 0.270s (disrupted at 0.411s by MESSAGE_DROPPED, recovered at 0.681s via the command is executed after the ACK timeout and retry)

Recovery time: 0.270 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.681s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 1 distinct payload.command_id value(s) in 1 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
