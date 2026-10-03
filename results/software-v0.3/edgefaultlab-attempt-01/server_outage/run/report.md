# EdgeFaultLab Run

Scenario: smart agriculture - server outage
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.001s `FAULT_ACTIVATED` gateways_to_server fault=server-down
- 2.001s `LINK_DOWN` gateways_to_server fault=server-down
- 4.002s `LINK_UP` gateways_to_server
- 12.007s `PROCESS_EXIT` server pid=26353 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=26354 exit=-15
- 12.013s `PROCESS_EXIT` gateway_a2 pid=26355 exit=-15
- 12.015s `PROCESS_EXIT` sensor_b1 pid=26356 exit=-15
- 12.017s `PROCESS_EXIT` controller_c1 pid=26357 exit=-15
- 12.019s `PROCESS_EXIT` sensor_b2 pid=26358 exit=-15
- 12.021s `PROCESS_EXIT` controller_c2 pid=26359 exit=-15

## Messages

- messages received: 923
- messages forwarded: 923
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=26353 running=False restarts=0
- gateway_a1: pid=26354 running=False restarts=0
- gateway_a2: pid=26355 running=False restarts=0
- sensor_b1: pid=26356 running=False restarts=0
- controller_c1: pid=26357 running=False restarts=0
- sensor_b2: pid=26358 running=False restarts=0
- controller_c2: pid=26359 running=False restarts=0

## Recovery

- server-down: 2.003s (disrupted at 2.001s by LINK_DOWN, recovered at 4.005s via uploads resume after the server comes back)

Recovery time: 2.003 s

## Assertions

PASS the local control loop kept executing during the outage - observed 1 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS uploads resume after the server comes back - matched [type='SENSOR_DATA'] at 4.005s (window 4.000s..12.000s)
PASS the outage did not cause a double execution - 1 distinct payload.command_id value(s) in 1 matching message(s)

## Result

PASS
