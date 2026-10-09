# PR #7 recovery and sampling initialization fix

## Original evidence and root causes

The original blocking failure is [run 37893918383, attempt 1](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37893918383/attempts/1), source `021585e28b468a9db7f09aed2e5e4c6996d09586`, Python 3.12.15, job `113700798696`: 629 passed, 2 failed. Later green documentation runs do not replace this observation. The original complete artifact is `software-evidence-python-3.12`. Selected sent peer events, the original event-file hash, failed summary and deterministic pre-fix regression logs are retained in `results/pr7-recovery-fix/`.

Recovery starts with persisted A1 generation 1 in STANDBY. A2 has already taken over generation 2. `task_heartbeat()` awaits `_connect_peer()` before `evaluate_peer_status()`. The successful handshake formerly carried only authentication/session information. If connection/handshake scheduling exceeds the 0.6-second failure window, A1 still has `peer_last_seen=None` when it evaluates the timeout, despite having just spoken to the live A2. A1 takes over at generation 2 and clears `_recovery_pending`. Both peers then ignore equal-generation ownership transfers; `observe_peer()` only demotes for a strictly higher generation. The failure artifact shows both persisted ACTIVE/generation 2 checkpoints and overlapping ownership. This is a state-machine initialization defect, not an acceptable timeout result.

The separate keepalive log ends after gateway registration and before the sensor records an accepted registration or first sample. The test started its 0.8-second clock when it scheduled `sensor.run()`, before registration, and conflated connection/registration startup with the subsequent silent sampling period. Sampling is correctly gated on accepted registration. Delaying registration by 0.9 seconds deterministically reproduces zero samples at the old observation point; the same sensor then produces its first telemetry and remains ONLINE throughout the unchanged 0.8-second silent period. The original logs do not identify the host scheduling cause of the delay, and this fix does not claim to make arbitrary startup latency fit a fixed deadline.

## Changes and safety boundaries

- Peer AUTH_ACK includes current generation, role and owned node pairs. HMAC mode authenticates this response together with its session nonce. The connecting gateway validates and applies it through the existing heartbeat validator before timeout evaluation or publishing its own ownership. Missing, malformed, stale or unauthenticated state cannot establish liveness/authority. A checkpoint fault rejects enrollment; it cannot advertise authority through this new path.
- An equal-epoch overlapping ACTIVE peer claim fails closed to STANDBY, including persisted recovery. Ownership is never transferred using arrival order or gateway ID. STANDBY claims do not demote the incumbent. Existing disjoint initial ACTIVE ownership and formal unreachable-peer takeover remain supported.
- The keepalive test observes first delivered B1 telemetry before starting its silent-period clock. Original 0.8-second duration, single-sample assertion, 0.3-second expiry threshold and ONLINE assertions are retained. A delayed-registration variant verifies zero pre-registration samples and the identical post-initialization contract.
- The existing seven gateway tasks, architecture, field protocol, firmware, golden references and all historical research evidence are preserved. The peer handshake is additive but upgraded host peers now require ownership evidence; mixed old/new host gateway versions fail enrollment and must be upgraded together. This does not establish consensus under arbitrary partitions or prove physical actuation safety.

## Regression evidence

On the unchanged research executable baseline, two delayed-handshake cases (lab/HMAC) and the equal-epoch persisted recovery case fail deterministically. The recorded logs show A1 promoting 1 → 2 after the successful delayed handshake. With the fix, A1 stays generation 1/STANDBY, sends no local ownership claims, and recognizes all four nodes as A2/generation 2. Tests also cover equal ACTIVE conflict, a recovering STANDBY peer not demoting the incumbent, tampered HMAC evidence, invalid/missing state, and real timeout recovery without a reachable peer.

Focused validation: 58 tests passed on Python 3.12.14. Fresh complete validation ran on clean commit `69facd0a4510934be6b3c86322a29c6f7368032e`, with `dirty=false` and source hashes retained in `results/pr7-recovery-fix/validation-summary.json`.

| Verification | Result |
| --- | --- |
| Full Python 3.10.21 / 3.12.14 pytest | 641/641 each; 97.63 s / 89.88 s |
| TCP / host simulated-LoRa topology | 20/20 each |
| Repeated ownership and reliability | 20/20 |
| Seeded radio safety comparison | 56/56; 43 COMPLETE and 13 INCOMPLETE deliveries retained |
| Actual C sleep/restore oracle | 19/19 |
| Cross-phase integration | 10/10 |
| External EdgeFaultLab | 5/5 at `c7248239f456cc877114ca1e67c5949fb4a7b958` |
| Historical evidence inventory | PASS |
| Fix-branch full CI | [37899830922](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37899830922): 6/6 |
| ESP32-S3, ESP-IDF v5.4.4 | lab, light-sleep, lora-prototype, deep-sleep-experimental actual builds all successful |

Both CI Python jobs ran the complete tests; every Python 3.12 experiment step executed successfully. Firmware compile/size evidence is retained by Actions. Local command argv, exit codes, durations and experiment hashes are retained with the validation summary; complete bulk output remains under `.research-runs/pr7-recovery-fix/full-69facd0/`. Historical failures remain unchanged. The validation-report commit only adds evidence and updates publication status, with no change to tested executable source, tests, firmware or workflow.

## Publication gates

The recovery blocker is resolved by reproduced-before/fixed-after state-machine evidence and the complete validation above. Merge the fix branch into research with an ordinary merge, retaining both histories. PR #7 must remain Draft until the full research push and PR checks pass on its latest head; then use an ordinary merge commit into main and verify full main CI. [PR #7 checks](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/pull/7/checks) and [main Actions](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions?query=branch%3Amain) expose the current publication result. Exact research/PR runs and the final main merge/run are also reported with the completed task, without a recursive post-merge documentation commit.

No timeout increase, weakened assertion, skipped test, force push or historical evidence deletion was used. Remaining limits: host gateway pairs require a coordinated upgrade of the enriched peer handshake; equal-epoch conflict detection favors safety and may sacrifice availability; arbitrary partitions, physical RF/AUX/reset, real actuation, RTC/NVS power cuts and energy/battery behavior remain unverified. The sampling regression removes an invalid initialization assumption, not arbitrary host scheduling delay.
