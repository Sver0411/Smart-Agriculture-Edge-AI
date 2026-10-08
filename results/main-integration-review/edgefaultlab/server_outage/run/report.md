# EdgeFaultLab Run

Scenario: smart agriculture - server outage
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.002s `FAULT_ACTIVATED` gateways_to_server fault=server-down
- 2.002s `LINK_DOWN` gateways_to_server fault=server-down
- 4.001s `LINK_UP` gateways_to_server
- 12.007s `PROCESS_EXIT` server pid=47235 exit=-15
- 12.008s `PROCESS_EXIT` gateway_a1 pid=47236 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a2 pid=47237 exit=-15
- 12.011s `PROCESS_EXIT` sensor_b1 pid=47238 exit=-15
- 12.013s `PROCESS_EXIT` controller_c1 pid=47239 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b2 pid=47240 exit=-15
- 12.015s `PROCESS_EXIT` controller_c2 pid=47241 exit=-15

## Messages

- messages received: 1004
- messages forwarded: 1004
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=47235 running=False restarts=0
- gateway_a1: pid=47236 running=False restarts=0
- gateway_a2: pid=47237 running=False restarts=0
- sensor_b1: pid=47238 running=False restarts=0
- controller_c1: pid=47239 running=False restarts=0
- sensor_b2: pid=47240 running=False restarts=0
- controller_c2: pid=47241 running=False restarts=0

## Recovery

- server-down: 3.712s (disrupted at 2.002s by LINK_DOWN, recovered at 5.715s via uploads resume after the server comes back)

Recovery time: 3.712 s

## Assertions

PASS the local control loop kept executing during the outage - observed 20 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS uploads resume after the server comes back - matched [type='SENSOR_DATA'] at 5.715s (window 4.000s..12.000s)
PASS the outage did not cause a double execution - 20 distinct payload.command_id value(s) in 20 matching message(s)

## Result

PASS
