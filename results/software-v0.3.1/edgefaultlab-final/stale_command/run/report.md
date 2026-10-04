# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.142s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.147s `MESSAGE_MUTATED` nodes_to_gateway_a1 7abd2ec7a5df fault=age-commands timestamp 1791087487.1440551 -> 1791087457.1440551
- 0.351s `MESSAGE_MUTATED` nodes_to_gateway_a1 f9342951bb0b fault=age-commands timestamp 1791087487.347102 -> 1791087457.347102
- 0.762s `MESSAGE_MUTATED` nodes_to_gateway_a1 90994e61f6ed fault=age-commands timestamp 1791087487.758616 -> 1791087457.758616
- 1.160s `MESSAGE_MUTATED` nodes_to_gateway_a1 85c636a25ed6 fault=age-commands timestamp 1791087488.156717 -> 1791087458.156717
- 1.566s `MESSAGE_MUTATED` nodes_to_gateway_a1 bd3790235f9c fault=age-commands timestamp 1791087488.562631 -> 1791087458.562631
- 1.969s `MESSAGE_MUTATED` nodes_to_gateway_a1 6a7aaaa8e8ac fault=age-commands timestamp 1791087488.965748 -> 1791087458.965748
- 2.375s `MESSAGE_MUTATED` nodes_to_gateway_a1 94eeb4b66be8 fault=age-commands timestamp 1791087489.370419 -> 1791087459.370419
- 2.982s `MESSAGE_MUTATED` nodes_to_gateway_a1 eb8ae875dd62 fault=age-commands timestamp 1791087489.97766 -> 1791087459.97766
- 3.385s `MESSAGE_MUTATED` nodes_to_gateway_a1 2a3eecd24a52 fault=age-commands timestamp 1791087490.380298 -> 1791087460.380298
- 4.194s `MESSAGE_MUTATED` nodes_to_gateway_a1 391522f0fe20 fault=age-commands timestamp 1791087491.1894689 -> 1791087461.1894689
- 4.597s `MESSAGE_MUTATED` nodes_to_gateway_a1 4a4a3a7c1abe fault=age-commands timestamp 1791087491.592745 -> 1791087461.592745
- 5.002s `MESSAGE_MUTATED` nodes_to_gateway_a1 f10abe084c62 fault=age-commands timestamp 1791087491.997217 -> 1791087461.997217
- 5.609s `MESSAGE_MUTATED` nodes_to_gateway_a1 297b32bd462a fault=age-commands timestamp 1791087492.6029198 -> 1791087462.6029198
- 7.032s `MESSAGE_MUTATED` nodes_to_gateway_a1 b5ad47233d28 fault=age-commands timestamp 1791087494.0175328 -> 1791087464.0175328
- 8.233s `MESSAGE_MUTATED` nodes_to_gateway_a1 160927e2219c fault=age-commands timestamp 1791087495.2292721 -> 1791087465.2292721
- 8.640s `MESSAGE_MUTATED` nodes_to_gateway_a1 d9adca8089f8 fault=age-commands timestamp 1791087495.635442 -> 1791087465.635442
- 9.450s `MESSAGE_MUTATED` nodes_to_gateway_a1 d0fafbb2f7c2 fault=age-commands timestamp 1791087496.445539 -> 1791087466.445539
- 10.665s `MESSAGE_MUTATED` nodes_to_gateway_a1 961f70168581 fault=age-commands timestamp 1791087497.660872 -> 1791087467.660872
- 11.475s `MESSAGE_MUTATED` nodes_to_gateway_a1 a2e2b41b8216 fault=age-commands timestamp 1791087498.4702349 -> 1791087468.4702349
- 11.882s `MESSAGE_MUTATED` nodes_to_gateway_a1 3295bd841ea2 fault=age-commands timestamp 1791087498.877454 -> 1791087468.877454
- 12.008s `PROCESS_EXIT` server pid=34777 exit=-15
- 12.011s `PROCESS_EXIT` gateway_a1 pid=34778 exit=-15
- 12.014s `PROCESS_EXIT` gateway_a2 pid=34779 exit=-15
- 12.016s `PROCESS_EXIT` sensor_b1 pid=34780 exit=-15
- 12.018s `PROCESS_EXIT` controller_c1 pid=34781 exit=-15
- 12.020s `PROCESS_EXIT` sensor_b2 pid=34782 exit=-15
- 12.022s `PROCESS_EXIT` controller_c2 pid=34783 exit=-15

## Messages

- messages received: 1023
- messages forwarded: 1023
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 20
- malformed messages: 0
- messages too large: 0
- messages matched: 20

## Processes

- server: pid=34777 running=False restarts=0
- gateway_a1: pid=34778 running=False restarts=0
- gateway_a2: pid=34779 running=False restarts=0
- sensor_b1: pid=34780 running=False restarts=0
- controller_c1: pid=34781 running=False restarts=0
- sensor_b2: pid=34782 running=False restarts=0
- controller_c2: pid=34783 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 20 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
