# EdgeFaultLab Run

Scenario: smart agriculture - lost command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.169s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=drop-first-command
- 0.400s `MESSAGE_DROPPED` nodes_to_gateway_a1 243c099d264c fault=drop-first-command
- 12.006s `PROCESS_EXIT` server pid=39249 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a1 pid=39250 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a2 pid=39251 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b1 pid=39252 exit=-15
- 12.015s `PROCESS_EXIT` controller_c1 pid=39253 exit=-15
- 12.017s `PROCESS_EXIT` sensor_b2 pid=39254 exit=-15
- 12.019s `PROCESS_EXIT` controller_c2 pid=39255 exit=-15

## Messages

- messages received: 1061
- messages forwarded: 1060
- messages dropped: 1
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 1

## Processes

- server: pid=39249 running=False restarts=0
- gateway_a1: pid=39250 running=False restarts=0
- gateway_a2: pid=39251 running=False restarts=0
- sensor_b1: pid=39252 running=False restarts=0
- controller_c1: pid=39253 running=False restarts=0
- sensor_b2: pid=39254 running=False restarts=0
- controller_c2: pid=39255 running=False restarts=0

## Recovery

- drop-first-command: 0.278s (disrupted at 0.400s by MESSAGE_DROPPED, recovered at 0.678s via the command is executed after the ACK timeout and retry)

Recovery time: 0.278 s

## Assertions

PASS the command is executed after the ACK timeout and retry - matched [payload.status='EXECUTED', type='CONTROL_RESULT'] at 0.678s (window 0.000s..8.000s)
PASS the retry executed the command exactly once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS at least one command was sent - observed 19 message(s) matching [type='CONTROL_COMMAND']

## Result

PASS
