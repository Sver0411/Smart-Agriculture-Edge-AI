# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.126s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.531s `MESSAGE_DROPPED` nodes_to_gateway_a1 b73822f1e5c5 fault=drop-first-command
- 12.005s `PROCESS_EXIT` server pid=75544 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=75545 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=75546 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=75547 exit=-15
- 12.012s `PROCESS_EXIT` controller_c1 pid=75548 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b2 pid=75549 exit=-15
- 12.015s `PROCESS_EXIT` controller_c2 pid=75550 exit=-15

## Messages

- messages received: 1073
- messages forwarded: 1072
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=75544 running=False restarts=0
- gateway_a1: pid=75545 running=False restarts=0
- gateway_a2: pid=75546 running=False restarts=0
- sensor_b1: pid=75547 running=False restarts=0
- controller_c1: pid=75548 running=False restarts=0
- sensor_b2: pid=75549 running=False restarts=0
- controller_c2: pid=75550 running=False restarts=0

## Recovery

- drop-first-command: 0.264s (disrupted at 0.531s by MESSAGE_DROPPED, recovered at 0.795s via the command is executed after the ACK timeout and retry)

Recovery time: 0.264 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.795s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS at least one command was sent - observed 18 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
