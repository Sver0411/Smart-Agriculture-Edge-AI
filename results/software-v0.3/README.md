# v0.3 software evidence

All data here is host software simulation / TCP fault experimentation.

- `final/`: 17 internal complete-topology scenarios, PASS/FAIL assertions and metrics.
- `attempt-01/`: original internal run; metrics implementation recorded in its revision.
- `edgefaultlab-attempt-01/`: independent external runner, 4 PASS + 1 FAIL (preserved).
- `edgefaultlab-attempt-02/`: corrected portable lab configuration, 5 PASS.
- `validation/`: actual test, training, quantization and demo logs, including initial collection failures.
- `model_benchmark.json`: host prediction cost; no MCU flash/energy/latency claim.

Raw events and original manifests are preserved. Do not overwrite run directories. Local SQLite scratch DB files are Git-ignored. Follow docs/V0_3_INTEGRATION_REPORT.md for provenance and limitations.
