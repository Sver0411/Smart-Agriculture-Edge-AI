# EdgeFaultLab Run

Scenario: smart agriculture - gateway failover
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.002s `FAULT_ACTIVATED` fault=kill-a1
- 2.002s `PROCESS_KILL` gateway_a1 pid=38923
- 2.003s `PROCESS_EXIT` gateway_a1 pid=38923 exit=-15
- 2.172s `MESSAGE_FORWARD_FAILED` nodes_to_gateway_a1 f71095ae607b
- 12.005s `PROCESS_EXIT` server pid=38922 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a2 pid=38924 exit=-15
- 12.010s `PROCESS_EXIT` sensor_b1 pid=38925 exit=-15
- 12.012s `PROCESS_EXIT` controller_c1 pid=38926 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b2 pid=38927 exit=-15
- 12.015s `PROCESS_EXIT` controller_c2 pid=38928 exit=-15

## Messages

- messages received: 767
- messages forwarded: 766
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=38922 running=False restarts=0
- gateway_a1: pid=38923 running=False restarts=0
- gateway_a2: pid=38924 running=False restarts=0
- sensor_b1: pid=38925 running=False restarts=0
- controller_c1: pid=38926 running=False restarts=0
- sensor_b2: pid=38927 running=False restarts=0
- controller_c2: pid=38928 running=False restarts=0

## Recovery

- kill-a1: 0.002s (disrupted at 2.002s by PROCESS_KILL, recovered at 2.004s via B1 reconnects to A2)

Recovery time: 0.002 s

## Assertions

PASS the mesh keeps reporting to the cloud after A1 dies - matched [type='SENSOR_DATA'] at 2.376s (window 2.000s..10.000s)
PASS failover does not execute a command twice - 5 distinct payload.command_id value(s) in 5 matching message(s)
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered
PASS sensor data reached the cloud at all - observed 34 message(s) matching [type='SENSOR_DATA']
PASS A2 uploads after A1 crash - matched [source='A2', type='SENSOR_DATA'] at 2.376s (window 2.000s..10.000s)
PASS B1 reconnects to A2 - matched [source='B1', type='NODE_REGISTER'] at 2.004s (window 2.000s..10.000s)

## Result

PASS
