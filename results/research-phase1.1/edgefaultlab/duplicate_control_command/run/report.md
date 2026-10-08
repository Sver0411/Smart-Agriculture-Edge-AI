# EdgeFaultLab Run

Scenario: smart agriculture - duplicate control command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 2.082s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=duplicate-command
- 2.181s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 41ba6120daa0 fault=duplicate-command copies=1
- 2.581s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 0298b2ace2fc fault=duplicate-command copies=1
- 3.187s `MESSAGE_DUPLICATED` nodes_to_gateway_a1 bbd40488dd5c fault=duplicate-command copies=1
- 12.004s `PROCESS_EXIT` server pid=92670 exit=-15
- 12.006s `PROCESS_EXIT` gateway_a1 pid=92671 exit=-15
- 12.007s `PROCESS_EXIT` gateway_a2 pid=92672 exit=-15
- 12.008s `PROCESS_EXIT` sensor_b1 pid=92673 exit=-15
- 12.009s `PROCESS_EXIT` controller_c1 pid=92674 exit=-15
- 12.009s `PROCESS_EXIT` sensor_b2 pid=92675 exit=-15
- 12.010s `PROCESS_EXIT` controller_c2 pid=92677 exit=-15

## Messages

- messages received: 1075
- messages forwarded: 1078
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 3
- messages reordered: 0
- messages mutated: 0
- malformed messages: 0
- messages too large: 0
- messages matched: 3

## Processes

- server: pid=92670 running=False restarts=0
- gateway_a1: pid=92671 running=False restarts=0
- gateway_a2: pid=92672 running=False restarts=0
- sensor_b1: pid=92673 running=False restarts=0
- controller_c1: pid=92674 running=False restarts=0
- sensor_b2: pid=92675 running=False restarts=0
- controller_c2: pid=92677 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS a command_id is executed at most once - 19 distinct payload.command_id value(s) in 19 matching message(s)
PASS commands still run at all - observed 19 message(s) matching [payload.status='EXECUTED', type='CONTROL_RESULT']
PASS no unsafe execution was reported - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
