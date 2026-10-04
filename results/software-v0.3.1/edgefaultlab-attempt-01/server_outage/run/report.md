# EdgeFaultLab Run

Scenario: smart agriculture - server outage
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.002s `FAULT_ACTIVATED` gateways_to_server fault=server-down
- 2.002s `LINK_DOWN` gateways_to_server fault=server-down
- 4.002s `LINK_UP` gateways_to_server
- 12.006s `PROCESS_EXIT` server pid=32593 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=32594 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a2 pid=32595 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=32596 exit=-15
- 12.013s `PROCESS_EXIT` controller_c1 pid=32597 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b2 pid=32598 exit=-15
- 12.016s `PROCESS_EXIT` controller_c2 pid=32599 exit=-15

## Messages

- messages received: 1027
- messages forwarded: 1027
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=32593 running=False restarts=0
- gateway_a1: pid=32594 running=False restarts=0
- gateway_a2: pid=32595 running=False restarts=0
- sensor_b1: pid=32596 running=False restarts=0
- controller_c1: pid=32597 running=False restarts=0
- sensor_b2: pid=32598 running=False restarts=0
- controller_c2: pid=32599 running=False restarts=0

## Recovery

- server-down: 2.005s (disrupted at 2.002s by LINK_DOWN, recovered at 4.007s via uploads resume after the server comes back)

Recovery time: 2.005 s

## Assertions

PASS the local control loop kept executing during the outage - observed 19 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS uploads resume after the server comes back - matched [type='SENSOR_DATA'] at 4.007s (window 4.000s..12.000s)
PASS the outage did not cause a double execution - 19 distinct payload.command_id value(s) in 19 matching message(s)

## Result

PASS
