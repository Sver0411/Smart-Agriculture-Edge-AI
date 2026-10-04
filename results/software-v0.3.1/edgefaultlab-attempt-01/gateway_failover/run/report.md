# EdgeFaultLab Run

Scenario: smart agriculture - gateway failover
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.000s `FAULT_ACTIVATED` fault=kill-a1
- 2.000s `PROCESS_KILL` gateway_a1 pid=32475
- 2.003s `PROCESS_EXIT` gateway_a1 pid=32475 exit=-15
- 2.204s `MESSAGE_FORWARD_FAILED` nodes_to_gateway_a1 ecaf7e07244b
- 12.005s `PROCESS_EXIT` server pid=32474 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a2 pid=32476 exit=-15
- 12.009s `PROCESS_EXIT` sensor_b1 pid=32477 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=32478 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=32479 exit=-15
- 12.014s `PROCESS_EXIT` controller_c2 pid=32481 exit=-15

## Messages

- messages received: 716
- messages forwarded: 715
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=32474 running=False restarts=0
- gateway_a1: pid=32475 running=False restarts=0
- gateway_a2: pid=32476 running=False restarts=0
- sensor_b1: pid=32477 running=False restarts=0
- controller_c1: pid=32478 running=False restarts=0
- sensor_b2: pid=32479 running=False restarts=0
- controller_c2: pid=32481 running=False restarts=0

## Recovery

- kill-a1: 0.004s (disrupted at 2.000s by PROCESS_KILL, recovered at 2.005s via B1 reconnects to A2)

Recovery time: 0.004 s

## Assertions

PASS the mesh keeps reporting to the cloud after A1 dies - matched [type='SENSOR_DATA'] at 2.203s (window 2.000s..10.000s)
PASS failover does not execute a command twice - 6 distinct payload.command_id value(s) in 6 matching message(s)
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered
PASS sensor data reached the cloud at all - observed 29 message(s) matching [type='SENSOR_DATA']
PASS A2 uploads after A1 crash - matched [source='A2', type='SENSOR_DATA'] at 2.203s (window 2.000s..10.000s)
PASS B1 reconnects to A2 - matched [source='B1', type='NODE_REGISTER'] at 2.005s (window 2.000s..10.000s)

## Result

PASS
