# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.185s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.689s `MESSAGE_DROPPED` nodes_to_gateway_a1 a962b02f69c0 fault=drop-first-command
- 12.007s `PROCESS_EXIT` server pid=27425 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=27426 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a2 pid=27427 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b1 pid=27428 exit=-15
- 12.016s `PROCESS_EXIT` controller_c1 pid=27429 exit=-15
- 12.018s `PROCESS_EXIT` sensor_b2 pid=27430 exit=-15
- 12.020s `PROCESS_EXIT` controller_c2 pid=27431 exit=-15

## Messages

- messages received: 928
- messages forwarded: 927
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=27425 running=False restarts=0
- gateway_a1: pid=27426 running=False restarts=0
- gateway_a2: pid=27427 running=False restarts=0
- sensor_b1: pid=27428 running=False restarts=0
- controller_c1: pid=27429 running=False restarts=0
- sensor_b2: pid=27430 running=False restarts=0
- controller_c2: pid=27431 running=False restarts=0

## Recovery

- drop-first-command: 0.267s (disrupted at 0.689s by MESSAGE_DROPPED, recovered at 0.956s via the command is executed after the ACK timeout and retry)

Recovery time: 0.267 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.956s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS at least one command was sent - observed 18 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
