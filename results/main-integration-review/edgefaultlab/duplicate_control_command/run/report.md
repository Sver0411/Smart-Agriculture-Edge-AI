# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.053s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.146s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 027d2bdf8fe2 fault=duplicate-command copies=1
- 2.553s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 d3ed839f9aea fault=duplicate-command copies=1
- 3.156s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 2a02d1df9b18 fault=duplicate-command copies=1
- 12.006s `PROCESS_EXIT` server pid=47374 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=47375 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a2 pid=47376 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=47377 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=47378 exit=-15
- 12.012s `PROCESS_EXIT` sensor_b2 pid=47379 exit=-15
- 12.013s `PROCESS_EXIT` controller_c2 pid=47380 exit=-15

## Messages

- messages received: 1070
- messages forwarded: 1073
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=47374 running=False restarts=0
- gateway_a1: pid=47375 running=False restarts=0
- gateway_a2: pid=47376 running=False restarts=0
- sensor_b1: pid=47377 running=False restarts=0
- controller_c1: pid=47378 running=False restarts=0
- sensor_b2: pid=47379 running=False restarts=0
- controller_c2: pid=47380 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 18 distinct payload.command_id value(s) in 18 matching message(s)
PASS commands still run at all - observed 18 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
