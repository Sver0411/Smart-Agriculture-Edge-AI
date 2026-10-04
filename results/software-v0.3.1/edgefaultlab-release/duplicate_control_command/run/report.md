# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.015s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.068s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 5e989ed8e1da fault=duplicate-command copies=1
- 2.473s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 868ce94f4f29 fault=duplicate-command copies=1
- 3.078s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 896c360ed2a0 fault=duplicate-command copies=1
- 12.009s `PROCESS_EXIT` server pid=39072 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a1 pid=39073 exit=-15
- 12.015s `PROCESS_EXIT` gateway_a2 pid=39074 exit=-15
- 12.017s `PROCESS_EXIT` sensor_b1 pid=39075 exit=-15
- 12.018s `PROCESS_EXIT` controller_c1 pid=39076 exit=-15
- 12.020s `PROCESS_EXIT` sensor_b2 pid=39077 exit=-15
- 12.022s `PROCESS_EXIT` controller_c2 pid=39078 exit=-15

## Messages

- messages received: 1067
- messages forwarded: 1070
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=39072 running=False restarts=0
- gateway_a1: pid=39073 running=False restarts=0
- gateway_a2: pid=39074 running=False restarts=0
- sensor_b1: pid=39075 running=False restarts=0
- controller_c1: pid=39076 running=False restarts=0
- sensor_b2: pid=39077 running=False restarts=0
- controller_c2: pid=39078 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS commands still run at all - observed 19 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
