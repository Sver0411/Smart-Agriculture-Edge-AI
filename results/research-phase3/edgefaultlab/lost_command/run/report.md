# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.135s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.149s `MESSAGE_DROPPED` nodes_to_gateway_a1 07c4bfe207d9 fault=drop-first-command
- 12.005s `PROCESS_EXIT` server pid=11430 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a1 pid=11431 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=11432 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=11433 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=11434 exit=-15
- 12.012s `PROCESS_EXIT` sensor_b2 pid=11435 exit=-15
- 12.013s `PROCESS_EXIT` controller_c2 pid=11436 exit=-15

## Messages

- messages received: 1082
- messages forwarded: 1081
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=11430 running=False restarts=0
- gateway_a1: pid=11431 running=False restarts=0
- gateway_a2: pid=11432 running=False restarts=0
- sensor_b1: pid=11433 running=False restarts=0
- controller_c1: pid=11434 running=False restarts=0
- sensor_b2: pid=11435 running=False restarts=0
- controller_c2: pid=11436 running=False restarts=0

## Recovery

- drop-first-command: 0.293s (disrupted at 0.149s by MESSAGE_DROPPED, recovered at 0.442s via the command is executed after the ACK timeout and retry)

Recovery time: 0.293 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.442s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 20 distinct payload.command_id value(s) in 20 matching message(s)
PASS at least one command was sent - observed 20 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
