# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: FAIL

## Faults

- 2.000s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 12.006s `PROCESS_EXIT` server pid=26491 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=26492 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=26493 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=26494 exit=-15
- 12.012s `PROCESS_EXIT` controller_c1 pid=26495 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=26496 exit=-15
- 12.015s `PROCESS_EXIT` controller_c2 pid=26497 exit=-15

## Messages

- messages received: 742
- messages forwarded: 742
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=26491 running=False restarts=0
- gateway_a1: pid=26492 running=False restarts=0
- gateway_a2: pid=26493 running=False restarts=0
- sensor_b1: pid=26494 running=False restarts=0
- controller_c1: pid=26495 running=False restarts=0
- sensor_b2: pid=26496 running=False restarts=0
- controller_c2: pid=26497 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 0 distinct payload.command_id value(s) in 0 matching message(s)
FAIL commands still run at all - observed 0 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT'] but expected at least 1
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

FAIL
