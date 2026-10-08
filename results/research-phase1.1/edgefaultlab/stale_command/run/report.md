# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.123s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.334s `MESSAGE_MUTATED` nodes_to_gateway_a1 b80d73e26694 fault=age-commands timestamp 1791456655.997786 -> 1791456625.997786
- 0.536s `MESSAGE_MUTATED` nodes_to_gateway_a1 9a99dd112788 fault=age-commands timestamp 1791456656.200377 -> 1791456626.200377
- 0.937s `MESSAGE_MUTATED` nodes_to_gateway_a1 88368ddb492c fault=age-commands timestamp 1791456656.602397 -> 1791456626.602397
- 1.342s `MESSAGE_MUTATED` nodes_to_gateway_a1 09f99e338706 fault=age-commands timestamp 1791456657.006298 -> 1791456627.006298
- 1.744s `MESSAGE_MUTATED` nodes_to_gateway_a1 f08c149486e3 fault=age-commands timestamp 1791456657.408524 -> 1791456627.408524
- 2.145s `MESSAGE_MUTATED` nodes_to_gateway_a1 4580fb8e8adb fault=age-commands timestamp 1791456657.8105311 -> 1791456627.8105311
- 2.552s `MESSAGE_MUTATED` nodes_to_gateway_a1 0b194d8dc3a3 fault=age-commands timestamp 1791456658.2153332 -> 1791456628.2153332
- 3.153s `MESSAGE_MUTATED` nodes_to_gateway_a1 c3b1338f3ab9 fault=age-commands timestamp 1791456658.8180852 -> 1791456628.8180852
- 3.557s `MESSAGE_MUTATED` nodes_to_gateway_a1 d5efffd025b2 fault=age-commands timestamp 1791456659.221497 -> 1791456629.221497
- 4.360s `MESSAGE_MUTATED` nodes_to_gateway_a1 8b25eaf1e62d fault=age-commands timestamp 1791456660.025237 -> 1791456630.025237
- 4.765s `MESSAGE_MUTATED` nodes_to_gateway_a1 0ffc2f30ec1e fault=age-commands timestamp 1791456660.430167 -> 1791456630.430167
- 5.167s `MESSAGE_MUTATED` nodes_to_gateway_a1 be3efbe7ac73 fault=age-commands timestamp 1791456660.832219 -> 1791456630.832219
- 5.772s `MESSAGE_MUTATED` nodes_to_gateway_a1 0a0cfc8909fd fault=age-commands timestamp 1791456661.436883 -> 1791456631.436883
- 7.193s `MESSAGE_MUTATED` nodes_to_gateway_a1 64e4942f842a fault=age-commands timestamp 1791456662.857416 -> 1791456632.857416
- 8.402s `MESSAGE_MUTATED` nodes_to_gateway_a1 6092be064d18 fault=age-commands timestamp 1791456664.066549 -> 1791456634.066549
- 8.805s `MESSAGE_MUTATED` nodes_to_gateway_a1 37f8cdc37a10 fault=age-commands timestamp 1791456664.469741 -> 1791456634.469741
- 9.614s `MESSAGE_MUTATED` nodes_to_gateway_a1 d19e148e804c fault=age-commands timestamp 1791456665.2792718 -> 1791456635.2792718
- 10.826s `MESSAGE_MUTATED` nodes_to_gateway_a1 b61fc17a4250 fault=age-commands timestamp 1791456666.489985 -> 1791456636.489985
- 11.631s `MESSAGE_MUTATED` nodes_to_gateway_a1 19f68531ee6b fault=age-commands timestamp 1791456667.2961202 -> 1791456637.2961202
- 12.007s `PROCESS_EXIT` server pid=92829 exit=-15
- 12.010s `PROCESS_EXIT` gateway_a1 pid=92830 exit=-15
- 12.012s `PROCESS_EXIT` gateway_a2 pid=92831 exit=-15
- 12.014s `PROCESS_EXIT` sensor_b1 pid=92832 exit=-15
- 12.016s `PROCESS_EXIT` controller_c1 pid=92833 exit=-15
- 12.018s `PROCESS_EXIT` sensor_b2 pid=92834 exit=-15
- 12.020s `PROCESS_EXIT` controller_c2 pid=92835 exit=-15

## Messages

- messages received: 1069
- messages forwarded: 1069
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=92829 running=False restarts=0
- gateway_a1: pid=92830 running=False restarts=0
- gateway_a2: pid=92831 running=False restarts=0
- sensor_b1: pid=92832 running=False restarts=0
- controller_c1: pid=92833 running=False restarts=0
- sensor_b2: pid=92834 running=False restarts=0
- controller_c2: pid=92835 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
