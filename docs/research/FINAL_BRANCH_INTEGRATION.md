# Final research → main integration

**Status: RECOVERY FIX VALIDATED.** The recorded CI blocker below has been investigated and fixed with deterministic regressions and complete local/CI validation. See [PR #7 recovery fix](PR7_RECOVERY_FIX.md) for root causes, code changes and exact evidence. Publication still requires full checks on the latest research/PR head, an ordinary main merge, and successful main CI; the linked PR/Actions pages show the live publication status. Earlier preparation runs and the original failure are retained below as history.

## Inputs and history audit

Reviewed on 2026-10-09 (Asia/Shanghai), after `git fetch origin --prune`, from a clean worktree.

- Main input: `08f573fbbd53d150a2bf80d577ba4d438e1a90a4`; [baseline CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37890916775) passed its two software jobs.
- Research input: `f5c2710fa4f45318e77314dcc4fb3c8bc25cf70c`; [baseline CI](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37890854347) passed all six software/firmware jobs.
- Every non-primary remote branch has zero commits outside the union of these two histories (`git rev-list <branch> --not origin/main origin/research`). Historical branches are retained and are not merged again. All six previous PRs were already merged.

| Remote branch | Audited tip | Already contained in |
| --- | --- | --- |
| `docs/chinese-readme-sync` | `ea5ab6176888` | main |
| `docs/english-readme` | `45289d9cbfb7` | main |
| `docs/research-readme-polish` | `4f68c7b87e37` | main |
| `feature/deployment-semantics` | `a60c5d14d55d` | both |
| `feature/main-integration-review` | `002e26a86bdb` | both |
| `feature/phase1-2-to-phase3` | `d18aebdeadc8` | research |
| `fix/research-reliability-stabilization` | `993d3827e68e` | research |
| `main` | `08f573fbbd53` | main |
| `refactor/ar1-sensor-pipeline` | `825bb9246728` | research |
| `research` | `f5c2710fa4f4` | research |
| `v0.2.1-protocol-hardening` | `4e320f96511f` | both |
| `v0.3-physical-b1` | `5a01dcdee7bc` | both |
| `v0.3-software-integration` | `79a5c5a5feca` | both |
| `v0.3.1-reliability-hardening` | `e9cf7a5547b3` | both |

## Conflict choices and consistency

Only `README.md` (content) and `README.zh-CN.md` (add/add) conflicted. Resolution uses main's academic header, all 30 existing section headings, both architecture diagrams, fixed two-zone description, six related-project descriptions and research evidence navigation. Updated prose includes the current research implementation and its verified limits. `docs/RESEARCH_EVIDENCE_GUIDE.md` is retained and extended. The dated deployment contract receives a current-source reading note so its earlier best-effort/planned-phase text cannot be mistaken for current behavior. Original reports and measurements are not rewritten.

At the preparation stage, all executable source, tests, configuration, dependency declarations, protocol/schema, golden references, firmware and the complete six-job workflow remained byte-identical to the research input. The later recovery fix changes Gateway peer enrollment and focused tests as documented separately. There is no new runtime abstraction or state. AR-1's pure pipeline depends on messages/protocol/trust_gate, never on Gateway; Gateway retains durable admission, ACKs, live ownership/generation and dispatch. Main's only independent changes were the two READMEs and evidence guide. Existing research results, including failed attempts, are retained.

Preparation merges main history into research with an ordinary two-parent merge; the final PR has `research` as head and `main` as base. Both pushes must be fast-forwards. Final acceptance requires a successful full PR matrix before an ordinary merge commit, followed by successful main CI. No history rewrite or force push is used.

## Validation

Fresh local validation completed on clean preparation commit `fe427f35c7a6f7f67d9562083de9d616d15616f7` (`dirty=false`). The subsequent acceptance-report/deployment-note update changes only documentation: executable source, tests, configuration, dependencies, firmware and CI hashes remain identical to that tested source and the research input.

| Acceptance | Fresh result |
| --- | --- |
| Full pytest, Python 3.10.21 | 631/631; 115.61 s |
| Full pytest, Python 3.12.14 | 631/631; 109.80 s |
| Original TCP topology | 20/20 PASS |
| Repeated ownership/reliability | 20/20 PASS: stale-generation ×10, failover ×3, recovery ×3, four other scenarios |
| Host simulated-LoRa topology | 20/20 PASS |
| Seeded radio comparison | 56/56 safety checks PASS; 43 COMPLETE / 13 INCOMPLETE deliveries retained |
| Actual C sleep/restore oracle | 19/19 PASS; 2800 observations; Apple clang 17.0.0; applicable C sanitizer checks included in pytest |
| Cross-phase integration | 10/10 PASS |
| External EdgeFaultLab | 5/5 PASS at the pinned revision |
| Historical evidence inventory | PASS; every tracked evidence file retained, with original failures and duplicate experiment contexts |
| Preparation push / PR CI | [Push](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37893032395) and [PR](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37893060375): 6/6 jobs each |
| Firmware CI | ESP32-S3 / ESP-IDF v5.4.4: lab, light-sleep, lora-prototype, deep-sleep-experimental all compiled successfully |

All Python 3.12 experiment steps and all four actual firmware build steps executed successfully. No core test was skipped or expected result changed. Local Python runs were sequential because existing socket tests use fixed ports. Exact argv, durations, logs, source/toolchain manifest and fresh summaries are ignored under `.research-runs/final-integration-verified/`; CI preserves full artifacts, including failures.

[PR #7](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/pull/7) is `research` → `main`. Publication additionally requires successful [checks on its latest head](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/pull/7/checks), then successful [main Actions](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions?query=branch%3Amain). These live links distinguish the final publication checks from the fixed preparation runs above. The final merge SHA and main run are reported after those checks, without adding a recursive post-merge report commit.

Reproduction commands (use a fresh output directory each time):

```sh
python -m pytest tests/ -q -o faulthandler_timeout=60
python -m experiments.runner --all --output .research-runs/tcp-NEW
python -m experiments.reliability_stabilization --output .research-runs/repeats-NEW
python -m experiments.runner --all --transport simulated-lora --output .research-runs/lora-NEW
python -m experiments.lora_harness --seed 42 --output .research-runs/comparison-NEW
python -m experiments.snapshot_harness --output .research-runs/snapshot-NEW
python -m experiments.phase123_integration --seed 42 --output .research-runs/integration-NEW
python -m experiments.edgefaultlab --edgefaultlab-root .external/edgefaultlab --output .research-runs/external-NEW
python -m experiments.evidence_inventory --output .research-runs/inventory-NEW.json
```

Actions runs full pytest on Python 3.10/3.12, every experiment above on 3.12, and ESP-IDF v5.4.4 / ESP32-S3 builds for `lab`, `light-sleep`, `lora-prototype` and `deep-sleep-experimental`. EdgeFaultLab is pinned at `c7248239f456cc877114ca1e67c5949fb4a7b958`. All core experiment steps and actual firmware build steps must execute successfully; an unresolved failure blocks merging.

## Publication blocker: final-head CI failure

**Historical blocking observation, now addressed by [the separately validated recovery fix](PR7_RECOVERY_FIX.md).** The following records the original failure and decision to stop publication before investigation; it is not superseded by a rerun.

On documentation head `021585e28b468a9db7f09aed2e5e4c6996d09586`, [research push CI, attempt 1](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37893918383/attempts/1) failed Python 3.12: **629 passed, 2 failed**. Python 3.10 and all four actual firmware builds passed. Later experiment steps in that failed job were skipped because pytest failed; those steps are **not** counted as passing. The independent [PR run](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37893925593) passed all six jobs on the same executable-source hashes, but cannot invalidate the failed observation.

- `test_gateway_recovery_metrics_include_pre_crash_incarnation`: production `run_scenario('gateway-recovery')` returned FAIL with `TimeoutError: recovered peer enrollment`. The recorded takeover, synchronized A2/B1/C1 epoch, fixed ownership and rejection of the deposed command passed. Recovery did not converge to the required STANDBY state. Preserved events show recovered A1 advertising ACTIVE/generation 2 at `time_s=3.568`, and A2 advertising ACTIVE/generation 2 at `3.574`; subsequent peer heartbeats continue to show both ACTIVE with conflicting B1 ownership through the timeout. This is a real recorded software state, not just a missing assertion/log. It does not prove duplicate physical actuation, but blocks the recovery acceptance.
- `test_keepalive_keeps_sensor_online_during_silent_sampling`: the fixed 0.8-second observation found zero samples instead of one, while registration was still completing. Startup/host scheduling sensitivity is a plausible contributor; its cause is not established as infrastructure-only.

Both original tests were repeated **10 times each** locally on Python 3.12, unchanged, and all 20 executions passed. This establishes intermittent reproduction, not a fix. No expected values, golden references, timeouts, product logic or CI gates were changed. No retry was used to replace the failed push result.

Failed job logs, the complete failed software artifact, summary and original raw peer events were retained locally in `/tmp/agri-final-integration/` and remain available in the linked Actions run/artifact. Focused repetition logs are ignored under `.research-runs/final-integration-failure-recheck/`. A separate recovery investigation must establish why a recovering gateway reached the same active epoch as its surviving peer and provide an appropriate fix/regression before publication. Merely increasing deadlines or obtaining a green rerun would not settle that observation.

**Merge stopped.** No main PR merge or main push occurred. Therefore there is no integration merge SHA or post-merge main CI result. Final branch-report commits change documentation only and may trigger additional CI; any later green report-only run does not resolve this explicitly recorded blocker.

## Remaining risks and boundaries

- This integration adds no physical measurements. Only the historical 30 CRC-valid SHT30 reads are hardware evidence. RF links, A/C endpoints, real actuators, RTC calibration, GPIO/AUX/reset behavior, NVS power cuts, energy and battery life remain unverified.
- Heartbeats and generation fencing do not prove consensus across arbitrary partitions. Bounded storage and deduplication windows cannot provide unconditional delivery or exactly-once physical execution.
- The radio comparison deliberately retains incomplete deliveries; safety PASS is not universal delivery success.
- Deployment entry points stay fail-closed until every required link authenticates; optional peer HMAC and CRC do not satisfy that requirement.
- Legacy nonphysical inputs retain their weaker freshness contract, and a committed receipt interrupted by ACK-send failure does not replay an interrupted control decision. These are documented AR-1 compatibility boundaries, not changes made during integration.
- Learned models remain synthetic policy references. Field accuracy, MCU inference and agricultural benefit are not established. AR-2/AR-3/AR-4, dashboard and model registry are not implemented by this integration.
