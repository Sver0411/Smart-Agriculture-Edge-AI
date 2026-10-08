# EdgeFaultLab Run

Scenario: smart agriculture - gateway failover
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.001s `FAULT_ACTIVATED` fault=kill-a1
- 2.002s `PROCESS_KILL` gateway_a1 pid=47094
- 2.005s `PROCESS_EXIT` gateway_a1 pid=47094 exit=-15
- 2.163s `MESSAGE_FORWARD_FAILED` nodes_to_gateway_a1 d135ebcda1fa
- 12.007s `PROCESS_EXIT` server pid=47093 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a2 pid=47095 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b1 pid=47096 exit=-15
- 12.015s `PROCESS_EXIT` controller_c1 pid=47097 exit=-15
- 12.017s `PROCESS_EXIT` sensor_b2 pid=47098 exit=-15
- 12.018s `PROCESS_EXIT` controller_c2 pid=47099 exit=-15

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

- server: pid=47093 running=False restarts=0
- gateway_a1: pid=47094 running=False restarts=0
- gateway_a2: pid=47095 running=False restarts=0
- sensor_b1: pid=47096 running=False restarts=0
- controller_c1: pid=47097 running=False restarts=0
- sensor_b2: pid=47098 running=False restarts=0
- controller_c2: pid=47099 running=False restarts=0

## Recovery

- kill-a1: 0.006s (disrupted at 2.002s by PROCESS_KILL, recovered at 2.008s via B1 reconnects to A2)

Recovery time: 0.006 s

## Assertions

PASS the mesh keeps reporting to the cloud after A1 dies - matched [type='SENSOR_DATA'] at 2.166s (window 2.000s..10.000s)
PASS failover does not execute a command twice - 5 distinct payload.command_id value(s) in 5 matching message(s)
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered
PASS sensor data reached the cloud at all - observed 34 message(s) matching [type='SENSOR_DATA']
PASS A2 uploads after A1 crash - matched [source='A2', type='SENSOR_DATA'] at 2.166s (window 2.000s..10.000s)
PASS B1 reconnects to A2 - matched [source='B1', type='NODE_REGISTER'] at 2.008s (window 2.000s..10.000s)

## Result

PASS
