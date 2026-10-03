# EdgeFaultLab Run

Scenario: smart agriculture - stale command
Seed: 42
Duration: 12s
Result: PASS

## Faults

- 0.212s `FAULT_ACTIVATED` nodes_to_gateway_a1 fault=age-commands
- 0.421s `MESSAGE_MUTATED` nodes_to_gateway_a1 2fd2a26317ec fault=age-commands timestamp 1791048608.674099 -> 1791048578.674099
- 0.827s `MESSAGE_MUTATED` nodes_to_gateway_a1 5fcf40042dfc fault=age-commands timestamp 1791048609.079246 -> 1791048579.079246
- 1.231s `MESSAGE_MUTATED` nodes_to_gateway_a1 ff5f5f9cc115 fault=age-commands timestamp 1791048609.483787 -> 1791048579.483787
- 1.637s `MESSAGE_MUTATED` nodes_to_gateway_a1 935e3d880e50 fault=age-commands timestamp 1791048609.88893 -> 1791048579.88893
- 2.044s `MESSAGE_MUTATED` nodes_to_gateway_a1 ed5e681f395b fault=age-commands timestamp 1791048610.295934 -> 1791048580.295934
- 2.446s `MESSAGE_MUTATED` nodes_to_gateway_a1 446e36c3b788 fault=age-commands timestamp 1791048610.699139 -> 1791048580.699139
- 3.067s `MESSAGE_MUTATED` nodes_to_gateway_a1 e8a7912535f1 fault=age-commands timestamp 1791048611.319531 -> 1791048581.319531
- 3.472s `MESSAGE_MUTATED` nodes_to_gateway_a1 bfc6b3ad7aff fault=age-commands timestamp 1791048611.724256 -> 1791048581.724256
- 4.279s `MESSAGE_MUTATED` nodes_to_gateway_a1 f75074c2e395 fault=age-commands timestamp 1791048612.531633 -> 1791048582.531633
- 4.685s `MESSAGE_MUTATED` nodes_to_gateway_a1 45e25e41f89e fault=age-commands timestamp 1791048612.937234 -> 1791048582.937234
- 5.090s `MESSAGE_MUTATED` nodes_to_gateway_a1 0d428d849925 fault=age-commands timestamp 1791048613.342328 -> 1791048583.342328
- 5.696s `MESSAGE_MUTATED` nodes_to_gateway_a1 be209b1e49a3 fault=age-commands timestamp 1791048613.948859 -> 1791048583.948859
- 7.115s `MESSAGE_MUTATED` nodes_to_gateway_a1 756cd40e56d2 fault=age-commands timestamp 1791048615.367367 -> 1791048585.367367
- 8.335s `MESSAGE_MUTATED` nodes_to_gateway_a1 f432fa75d3bb fault=age-commands timestamp 1791048616.5870268 -> 1791048586.5870268
- 8.742s `MESSAGE_MUTATED` nodes_to_gateway_a1 4e3f68b84139 fault=age-commands timestamp 1791048616.9937642 -> 1791048586.9937642
- 9.550s `MESSAGE_MUTATED` nodes_to_gateway_a1 aa32613bf438 fault=age-commands timestamp 1791048617.80266 -> 1791048587.80266
- 10.764s `MESSAGE_MUTATED` nodes_to_gateway_a1 773a08d7ef95 fault=age-commands timestamp 1791048619.015944 -> 1791048589.015944
- 11.574s `MESSAGE_MUTATED` nodes_to_gateway_a1 70c7c44c3e6d fault=age-commands timestamp 1791048619.8256152 -> 1791048589.8256152
- 11.979s `MESSAGE_MUTATED` nodes_to_gateway_a1 06c015acc2d3 fault=age-commands timestamp 1791048620.230905 -> 1791048590.230905
- 12.012s `PROCESS_EXIT` server pid=26653 exit=-15
- 12.015s `PROCESS_EXIT` gateway_a1 pid=26654 exit=-15
- 12.017s `PROCESS_EXIT` gateway_a2 pid=26655 exit=-15
- 12.020s `PROCESS_EXIT` sensor_b1 pid=26656 exit=-15
- 12.022s `PROCESS_EXIT` controller_c1 pid=26657 exit=-15
- 12.024s `PROCESS_EXIT` sensor_b2 pid=26658 exit=-15
- 12.026s `PROCESS_EXIT` controller_c2 pid=26659 exit=-15

## Messages

- messages received: 952
- messages forwarded: 952
- messages dropped: 0
- messages delayed: 0
- messages duplicated: 0
- messages reordered: 0
- messages mutated: 19
- malformed messages: 0
- messages too large: 0
- messages matched: 19

## Processes

- server: pid=26653 running=False restarts=0
- gateway_a1: pid=26654 running=False restarts=0
- gateway_a2: pid=26655 running=False restarts=0
- sensor_b1: pid=26656 running=False restarts=0
- controller_c1: pid=26657 running=False restarts=0
- sensor_b2: pid=26658 running=False restarts=0
- controller_c2: pid=26659 running=False restarts=0

## Recovery

Recovery time: n/a (no disruptive fault took effect, or nothing recovered)

## Assertions

PASS no aged command was executed - no message matching [payload.status='EXECUTED', type='CONTROL_RESULT'] was ever delivered
PASS the controller refused the aged command - observed 19 message(s) matching [payload.status='REJECTED', type='CONTROL_RESULT']
PASS the refusal was clean, not a safety violation - no message matching [payload.reason='UNSAFE_EXECUTION', type='CONTROL_RESULT'] was ever delivered

## Result

PASS
