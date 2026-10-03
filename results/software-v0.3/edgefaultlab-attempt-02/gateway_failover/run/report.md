# EdgeFaultLab Run

Scenario: smart agriculture - gateway failover
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.002s `FAULT_ACTIVATED` fault=kill-a1
- 2.002s `PROCESS_KILL` gateway_a1 pid=27076
- 2.006s `PROCESS_EXIT` gateway_a1 pid=27076 exit=-15
- 2.177s `MESSAGE_FORWARD_FAILED` nodes_to_gateway_a1 15d529a72986
- 12.007s `PROCESS_EXIT` server pid=27075 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a2 pid=27077 exit=-15
- 12.012s `PROCESS_EXIT` sensor_b1 pid=27078 exit=-15
- 12.014s `PROCESS_EXIT` controller_c1 pid=27079 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b2 pid=27080 exit=-15
- 12.018s `PROCESS_EXIT` controller_c2 pid=27081 exit=-15

## Messages

- messages received: 645
- messages forwarded: 644
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=27075 running=False restarts=0
- gateway_a1: pid=27076 running=False restarts=0
- gateway_a2: pid=27077 running=False restarts=0
- sensor_b1: pid=27078 running=False restarts=0
- controller_c1: pid=27079 running=False restarts=0
- sensor_b2: pid=27080 running=False restarts=0
- controller_c2: pid=27081 running=False restarts=0

## Recovery

- kill-a1: 0.006s (disrupted at 2.002s by PROCESS_KILL, recovered at 2.009s via B1 reconnects to A2)

Recovery time: 0.006 s

## Assertions

PASS the mesh keeps reporting to the cloud after A1 dies - matched [type='SENSOR_DATA'] at 2.011s (window 2.000s..10.000s)
PASS failover does not execute a command twice - 4 distinct payload.command_id value(s) in 4 matching message(s)
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered
PASS sensor data reached the cloud at all - observed 34 message(s) matching [type='SENSOR_DATA']
PASS A2 uploads after A1 crash - matched [source='A2', type='SENSOR_DATA'] at 2.011s (window 2.000s..10.000s)
PASS B1 reconnects to A2 - matched [source='B1', type='NODE_REGISTER'] at 2.009s (window 2.000s..10.000s)

## Result

PASS
