# Phase 1.2: registration, freshness, bounded queues and peer trust

Base: `d909aa4a39e8374d4f356aca2db62473889236b1`, fetched 2026-10-08. Worktree was clean. Development branch: `feature/phase1-2-to-phase3`; main and research refs are not modified. This is software/compile evidence, not a field test.

## Implemented

- B1 portable registration validator returns ACCEPTED, NOT_OWNER, STALE_GENERATION or INVALID_REPLY; TCP adapter additionally reports TIMEOUT and TRANSPORT_FAILURE. A connection round tries at most two candidates, including after an explicit registration rejection. Owner/epoch observations never regress. Current owner stays preferred; no automatic failback. Outbox identities and HIGH storage are untouched.
- Gateway stamps ingress with its own process identity and monotonic/wall receive times. Device send-age plus local queue time gates reliable control, and freshness is rechecked after durable ACK transmission at the decision boundary. Unknown ages, other device boots, other gateway process clocks and >5-second samples remain history. Legacy physical health encoding stays supported when explicit fresh boot/age evidence is present.
- Four queues default to 128 entries (configurable 1–1024), report depth/high-water/max wait, and use explicit ingress rejection. No durable ACK is generated for rejected admission. Saturated cloud queues stage critical uploads in the existing durable outbox instead of waiting on the cloud. Failed persistence is counted and exposed in outbox_alert_state. Commands rejected before dispatch become NOT_DISPATCHED; retries remain UNKNOWN. Result consumption now balances task_done on every path. Inbound sockets are capped at 128.
- Peer sockets establish nonce-bound sessions before heartbeat authority. Lab mode is enrollment on a trusted host network, **not authentication**. `--peer-security-mode hmac --peer-key-file /private/path` uses an out-of-band >=32-byte key, mutual challenge proof and per-message HMAC-SHA256. Session/sequence, source/target, generation and complete paired ownership snapshots are checked before mutation. No private key is committed; public test keys are fixtures only.

## Reproduction and evidence

[Evidence](../../results/research-phase1.2/) preserves before/after tests, all raw internal/external scenarios, compile attempts and source hashes. Python baseline rerun: **378 passed**, 95.05 s. New targeted suite: **15 passed**, including real C/cJSON registration under ASan/UBSan. Full Python 3.12 regression: **393 passed**, 90.90 s. Python 3.10 final regression: **393 passed**, 88.03 s (`validation/py310-verified.log`). Internal fault scenarios: **20/20 PASS**. Independent EdgeFaultLab: **5/5 PASS**, reviewed revision `c7248239f456cc877114ca1e67c5949fb4a7b958`.

Commands: `python -m pytest -q`; `python -m experiments.runner --all --output <fresh-dir>`; `python -m experiments.edgefaultlab --edgefaultlab-root <pinned-checkout> --output <fresh-dir>`; `bash scripts/ci_build_b1.sh lab <fresh-absolute-dir>` with ESP-IDF v5.4.4 exported. ESP32-S3 public lab build passed; binary 831264 bytes, hash in `firmware-lab-manifest.json`.

Three original Python reproductions fail before fixes: unrestricted heartbeat, delayed sample action, unbounded queues. The C routing fixture extracts the actual candidate-selection block from original/current b1_network.c, stubs only socket registration outcomes, and asserts A1 TCP-success/registration-rejection reaches A2. Original block aborts the assertion; fixed block passes. This is control-flow host evidence, not a radio or board run. Initial fixture compilation failures are separately preserved and are not counted as functional reproductions.

One legacy channel-health fixture was supplied with explicit registered boot/send-age evidence without changing its ventilation assertion. Old physical messages with unknown age now intentionally lack control authority. An initial full run stalled on the old fixture and was interrupted; both logs are retained. An overlapping multi-version run hit the legacy fixed TCP test ports; the final 3.10 run is sequential. Initial IDF export scoping failure and successful retry are both retained.

## Limits

Authentication does not solve asymmetric partitions or provide consensus. A controller fences a lower epoch only after it observes a higher one; independent gateways/ledgers are not a quorum. Ordinary B/C TCP registration remains a laboratory identity boundary. SQLite synchronous staging uses the existing bounded storage operations; slow/damaged local storage remains a deployment risk and is not disguised as RF behavior. Queue rejection is observable and recoverable only when the sender has a retry contract. No board, actuator, power-cut, RF or energy test was performed.
