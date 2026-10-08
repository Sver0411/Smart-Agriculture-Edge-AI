# research Phase 0/1 evidence — 2026-10-08

Read [the Chinese development report](../../docs/research/PHASE1_DEVELOPMENT_REPORT.md) and [delivery limits](../../docs/research/B1_RELIABLE_DELIVERY.md).

- Baseline: `ccff0ae690073c9cc40b184932fe7b98abd70302`.
- Verified functional implementation: `827cc393af34a1921613e9239785a625f191eafb` (includes gateway commit `ffb5615`).
- `manifest.json`: environment, source hashes, firmware hash, seeds, test counts and explicit limitations. Hardware energy and RF rate are null.
- `validation/baseline-pytest.log`: original 350 tests passed.
- `validation/gateway-before.log`, `queue-before.log`, `report-baseline-before.log`: reproduced defects before fixes. The retained historical C source compiles with the baseline headers, not the new outbox API.
- Other intermediate logs retain a fixture assertion mistake, expected failures and the Python 3.14 IDF activation limitation. `idf-build.log` is the failed initial command; `idf-release-build.log` is the successful final build.
- `validation/committed-code-regression.log`: final 363 tests passed, 48.64 s. `targeted-acceptance.log`: 91 targeted tests passed. Sanitized host C execution is part of these tests.
- `raw/firmware-wire.jsonl`: real production C serializer output, deterministic host readings (25 °C, then injected 150 °C fault), not physical sensor measurements.
- `raw/b1-tcp-events.jsonl`: real localhost TCP from the C-wire integration test. First gateway-to-B ACK was deliberately dropped in the test shim; same identity was retried after cloud queue cleanup. The asserted final state is 2 samples and 1 alert; not a measured RF delivery probability.
- `scenarios/`: initial complete 20-scenario execution on a dirty development tree; its manifests report the actual base HEAD and dirty status. Do not relabel as a clean committed run.
- `scenarios-acceptance/`: final functional-code 20/20 PASS, seed 42, revision 827cc393. Documentation/evidence and trace-capture additions leave working_tree_dirty=true in existing runner manifests; functional code matches the recorded commit, separately checked in manifest.json. Existing scenario input_mode remains software-simulation; C actuation remains simulated.
- Scenario raw frames, injection plans, config, summaries and hashes are saved using the existing experiment runner. SQLite runtime files remain locally available and Git-ignored; raw JSONL is the committed replay/audit evidence. No historical results overwritten.
- `hardware_measurement_template.csv` is an empty schema, not a measurement dataset.

No power-cut, radio or physical actuator verification was executed. Five attempts are a per-boot limit; FAILED critical records remain until a valid ACK or later reboot/retry, and normal RAM records can be lost on reset. Capacity failures remain explicit negative outcomes.
