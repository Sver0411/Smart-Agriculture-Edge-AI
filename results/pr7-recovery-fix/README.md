# PR #7 recovery evidence

See [root-cause and validation report](../../docs/research/PR7_RECOVERY_FIX.md).

- `failure-provenance.json` identifies the failed CI source/artifact and hashes the original complete event file; it retains the original failed scenario summary.
- `failed-ci-peer-events.jsonl` preserves selected original sent peer heartbeat/AUTH_ACK frames, without rewriting message contents or event timestamps. This is an extraction, not the complete trace.
- `before-regression.log` records deterministic failures on the original research gateway code with the new regression tests.

Fresh bulk experiment output is isolated under ignored `.research-runs/pr7-recovery-fix/` locally and retained in Actions artifacts. Summaries and exact-source CI links are recorded after validation; original failed evidence remains retained.
