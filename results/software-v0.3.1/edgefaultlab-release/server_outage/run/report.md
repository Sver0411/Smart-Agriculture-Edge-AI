# EdgeFaultLab Run

Scenario: smart agriculture - server outage
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.001s `FAULT_ACTIVATED` gateways_to_server fault=server-down
- 2.001s `LINK_DOWN` gateways_to_server fault=server-down
- 4.002s `LINK_UP` gateways_to_server
- 12.009s `PROCESS_EXIT` server pid=38990 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a1 pid=38991 exit=-15
- 12.014s `PROCESS_EXIT` gateway_a2 pid=38992 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b1 pid=38993 exit=-15
- 12.018s `PROCESS_EXIT` controller_c1 pid=38994 exit=-15
- 12.019s `PROCESS_EXIT` sensor_b2 pid=38995 exit=-15
- 12.021s `PROCESS_EXIT` controller_c2 pid=38996 exit=-15

## Messages

- messages received: 1019
- messages forwarded: 1019
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 0

## Processes

- server: pid=38990 running=False restarts=0
- gateway_a1: pid=38991 running=False restarts=0
- gateway_a2: pid=38992 running=False restarts=0
- sensor_b1: pid=38993 running=False restarts=0
- controller_c1: pid=38994 running=False restarts=0
- sensor_b2: pid=38995 running=False restarts=0
- controller_c2: pid=38996 running=False restarts=0

## Recovery

- server-down: 2.010s (disrupted at 2.001s by LINK_DOWN, recovered at 4.011s via uploads resume after the server comes back)

Recovery time: 2.010 s

## Assertions

PASS the local control loop kept executing during the outage - observed 19 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS uploads resume after the server comes back - matched [type='SENSOR_DATA'] at 4.011s (window 4.000s..12.000s)
PASS the outage did not cause a double execution - 19 distinct payload.command_id value(s) in 19 matching message(s)

## Result

PASS
