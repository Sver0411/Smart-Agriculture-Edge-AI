# EdgeFaultLab Run

Scenario: smart agriculture - gateway failover
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.001s `FAULT_ACTIVATED` fault=kill-a1
- 2.001s `PROCESS_KILL` gateway_a1 pid=74955
- 2.003s `PROCESS_EXIT` gateway_a1 pid=74955 exit=-15
- 2.149s `MESSAGE_FORWARD_FAILED` nodes_to_gateway_a1 f99fad582e70
- 12.006s `PROCESS_EXIT` server pid=74954 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=74956 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=74957 exit=-15
- 12.011s `PROCESS_EXIT` controller_c1 pid=74958 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=74959 exit=-15
- 12.014s `PROCESS_EXIT` controller_c2 pid=74960 exit=-15

## Messages

- messages received: 768
- messages forwarded: 767
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=74954 running=False restarts=0
- gateway_a1: pid=74955 running=False restarts=0
- gateway_a2: pid=74956 running=False restarts=0
- sensor_b1: pid=74957 running=False restarts=0
- controller_c1: pid=74958 running=False restarts=0
- sensor_b2: pid=74959 running=False restarts=0
- controller_c2: pid=74960 running=False restarts=0

## Recovery

- kill-a1: 0.003s (disrupted at 2.001s by PROCESS_KILL, recovered at 2.004s via B1 reconnects to A2)

Recovery time: 0.003 s

## Assertions

PASS the mesh keeps reporting to the cloud after A1 dies - matched [type='SENSOR_DATA'] at 2.148s (window 2.000s..10.000s)
PASS failover does not execute a command twice - 4 distinct payload.command_id value(s) in 4 matching message(s)
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered
PASS sensor data reached the cloud at all - observed 34 message(s) matching [type='SENSOR_DATA']
PASS A2 uploads after A1 crash - matched [source='A2', type='SENSOR_DATA'] at 2.148s (window 2.000s..10.000s)
PASS B1 reconnects to A2 - matched [source='B1', type='NODE_REGISTER'] at 2.004s (window 2.000s..10.000s)

## Result

PASS
