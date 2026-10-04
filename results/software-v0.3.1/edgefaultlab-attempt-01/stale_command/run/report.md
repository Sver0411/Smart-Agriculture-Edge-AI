# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.162s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.372s `MESSAGE_MUTATED` nodes_to_gateway_a1 df9d37f7e455 fault=age-commands timestamp 1791087135.595683 -> 1791087105.595683
- 0.775s `MESSAGE_MUTATED` nodes_to_gateway_a1 e95062340c97 fault=age-commands timestamp 1791087135.999477 -> 1791087105.999477
- 1.177s `MESSAGE_MUTATED` nodes_to_gateway_a1 83b8d9a0ad5f fault=age-commands timestamp 1791087136.4031239 -> 1791087106.4031239
- 1.588s `MESSAGE_MUTATED` nodes_to_gateway_a1 a619b65a056c fault=age-commands timestamp 1791087136.811062 -> 1791087106.811062
- 1.989s `MESSAGE_MUTATED` nodes_to_gateway_a1 a910c1770a09 fault=age-commands timestamp 1791087137.2144032 -> 1791087107.2144032
- 2.394s `MESSAGE_MUTATED` nodes_to_gateway_a1 d0727ce1ae73 fault=age-commands timestamp 1791087137.6194031 -> 1791087107.6194031
- 2.998s `MESSAGE_MUTATED` nodes_to_gateway_a1 d9e80c2eb363 fault=age-commands timestamp 1791087138.224153 -> 1791087108.224153
- 3.402s `MESSAGE_MUTATED` nodes_to_gateway_a1 fe29d877dcb0 fault=age-commands timestamp 1791087138.627111 -> 1791087108.627111
- 4.212s `MESSAGE_MUTATED` nodes_to_gateway_a1 db8feca89e75 fault=age-commands timestamp 1791087139.437391 -> 1791087109.437391
- 4.619s `MESSAGE_MUTATED` nodes_to_gateway_a1 735c795f458a fault=age-commands timestamp 1791087139.84355 -> 1791087109.84355
- 5.025s `MESSAGE_MUTATED` nodes_to_gateway_a1 9b0f369a3913 fault=age-commands timestamp 1791087140.249436 -> 1791087110.249436
- 5.629s `MESSAGE_MUTATED` nodes_to_gateway_a1 da1a07a747bc fault=age-commands timestamp 1791087140.855356 -> 1791087110.855356
- 7.048s `MESSAGE_MUTATED` nodes_to_gateway_a1 a9efd0cdcb68 fault=age-commands timestamp 1791087142.274126 -> 1791087112.274126
- 8.267s `MESSAGE_MUTATED` nodes_to_gateway_a1 088b47ac89f1 fault=age-commands timestamp 1791087143.491254 -> 1791087113.491254
- 8.672s `MESSAGE_MUTATED` nodes_to_gateway_a1 5c1930b5807e fault=age-commands timestamp 1791087143.896624 -> 1791087113.896624
- 9.483s `MESSAGE_MUTATED` nodes_to_gateway_a1 36f92ab42e32 fault=age-commands timestamp 1791087144.708101 -> 1791087114.708101
- 10.704s `MESSAGE_MUTATED` nodes_to_gateway_a1 4f044cd32f2f fault=age-commands timestamp 1791087145.928279 -> 1791087115.928279
- 11.513s `MESSAGE_MUTATED` nodes_to_gateway_a1 7771130c16e6 fault=age-commands timestamp 1791087146.738251 -> 1791087116.738251
- 11.919s `MESSAGE_MUTATED` nodes_to_gateway_a1 8d65fd3b2470 fault=age-commands timestamp 1791087147.1445289 -> 1791087117.1445289
- 12.007s `PROCESS_EXIT` server pid=32766 exit=-15
- 12.009s `PROCESS_EXIT` gateway_a1 pid=32767 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a2 pid=32768 exit=-15
- 12.013s `PROCESS_EXIT` sensor_b1 pid=32769 exit=-15
- 12.015s `PROCESS_EXIT` controller_c1 pid=32770 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b2 pid=32771 exit=-15
- 12.018s `PROCESS_EXIT` controller_c2 pid=32772 exit=-15

## Messages

- messages received: 1064
- messages forwarded: 1064
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=32766 running=False restarts=0
- gateway_a1: pid=32767 running=False restarts=0
- gateway_a2: pid=32768 running=False restarts=0
- sensor_b1: pid=32769 running=False restarts=0
- controller_c1: pid=32770 running=False restarts=0
- sensor_b2: pid=32771 running=False restarts=0
- controller_c2: pid=32772 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
