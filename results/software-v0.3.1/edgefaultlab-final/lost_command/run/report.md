# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.152s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.360s `MESSAGE_DROPPED` nodes_to_gateway_a1 f0d03ef09a71 fault=drop-first-command
- 12.009s `PROCESS_EXIT` server pid=34840 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a1 pid=34841 exit=-15
- 12.015s `PROCESS_EXIT` gateway_a2 pid=34842 exit=-15
- 12.019s `PROCESS_EXIT` sensor_b1 pid=34843 exit=-15
- 12.021s `PROCESS_EXIT` controller_c1 pid=34844 exit=-15
- 12.023s `PROCESS_EXIT` sensor_b2 pid=34845 exit=-15
- 12.025s `PROCESS_EXIT` controller_c2 pid=34846 exit=-15

## Messages

- messages received: 1062
- messages forwarded: 1061
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=34840 running=False restarts=0
- gateway_a1: pid=34841 running=False restarts=0
- gateway_a2: pid=34842 running=False restarts=0
- sensor_b1: pid=34843 running=False restarts=0
- controller_c1: pid=34844 running=False restarts=0
- sensor_b2: pid=34845 running=False restarts=0
- controller_c2: pid=34846 running=False restarts=0

## Recovery

- drop-first-command: 0.256s (disrupted at 0.360s by MESSAGE_DROPPED, recovered at 0.616s via the command is executed after the ACK timeout and retry)

Recovery time: 0.256 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.616s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
