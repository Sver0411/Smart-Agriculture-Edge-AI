# Phase 1.2 → Phase 3 integration

This research change starts at `d909aa4a39e8374d4f356aca2db62473889236b1`. Independent checkpoints are A `30ddbd0` (registration/freshness/queues/peer trust), B `37c0cc4` (LoRa protocol/UART), C `1cb84fb` (RTC algorithm restore/Deep Sleep). Main/research histories and the original checkout were left unchanged. This PR targets research, with no automatic merge.

## Ten asserted scenarios

`python -m experiments.phase123_integration --output FRESH_DIRECTORY --seed 42` ran **10/10 PASS** in `results/research-phase123/scenarios-final`.

| # | Scenario | Assertion and actual execution scope |
|---:|---|---|
| 1 | Stable sampling → sleep → restore | Real C B1 policy is warmed to a stable confirmed baseline, serialized, restored with known elapsed time and sampled again; no upload or synthetic onset |
| 2 | Important event + packet loss + durable ACK | Real C threshold crossing produces HIGH; all first-attempt fragments are lost; retry reaches actual Gateway/SQLite/Server, ACK is matched, actual C confirmed sequence becomes 2 |
| 3 | HIGH pending across sleep/restart | Real C v2 checkpoint reload preserves full identity; first gateway ACK is lost; new-boot retry has UNKNOWN age, deduplicates, retires evidence and cannot advance fresh baseline |
| 4 | A1 crash, A2 takeover, history vs fresh | Seven-role LoRa topology proves fixed B1↔C1/B2↔C2 takeover. Additional C-restored historical HIGH is saved without control; a separately identified fresh host sample crosses A2→fragment codec→C1 SafetyGuard and executes |
| 5 | A1 recovery and old epoch | Actual two-gateway recovery enters STANDBY, B1/C1 stay with A2, old A1 generation is refused; no automatic failback |
| 6 | Corrupt fragments | CRC-corrupted first attempt never creates a receipt or decision; clean retry yields one durable logical sample |
| 7 | Gateway queue delay | Production queue ingress timestamp is shifted by an explicit 6-second monotonic delay injection; sample is durably historical with no command |
| 8 | Corrupt RTC snapshot | Production decoder rejects CRC damage; existing HIGH checkpoint remains, old identity is sent with UNKNOWN age, and no control is issued |
| 9 | Server offline and replay | Actual Gateway/Controller continue safe local operation, SQLite queues persist, server restart deduplicates and stores all 250 queued sample identities |
| 10 | One-way peer heartbeat loss | Actual A1→A2 HEARTBEAT drop rule advances A2's epoch; reverse link informs A1 to become STANDBY. Controller epoch fencing is exercised. This is one tested asymmetric schedule, not arbitrary-network consensus |

The bridge uses actual C policy, snapshot, queue, outbox and v2 checkpoint encoding with file callbacks for an NVS commit. It does not emulate ESP32 electrical retention or physical Flash. Fault-free fresh samples in scenario 4 are explicit host inputs, not physical SHT30 readings. Known elapsed time in scenario 1 is an oracle input, while the default board provider remains UNKNOWN. The gateway/server/controller application implementations and SQLite durability run for real; the RF carrier is simulated.

The first bridge run failed because its restored outbox had not been marked attempted before consuming an ACK. The real outbox rejected the premature ACK as designed. The harness was corrected to perform the attempt transition first; failed logs, original fixture source and failure context are retained. No expectation was weakened.

## Reproduction and evidence

```sh
python -m pytest tests/ -vv -o faulthandler_timeout=60
python -m experiments.runner --all --output /tmp/agri-tcp-NEW
python -m experiments.runner --all --transport simulated-lora --output /tmp/agri-lora-NEW
python -m experiments.lora_harness --seed 42 --output /tmp/agri-radio-NEW
python -m experiments.snapshot_harness --output /tmp/agri-snapshot-NEW
python -m experiments.phase123_integration --seed 42 --output /tmp/agri-integration-NEW
python -m experiments.edgefaultlab --edgefaultlab-root .external/edgefaultlab --output /tmp/agri-external-NEW
# ESP-IDF v5.4.4 exported; each output must be fresh:
bash scripts/ci_build_b1.sh deep-sleep-experimental /tmp/agri-deep-NEW
```

Tests require a C11 compiler and pytest; no third-party runtime is introduced into the seven node roles. Full Python versions must run sequentially when sharing a machine: some existing tests deliberately use fixed ports 9201/9202. EdgeFaultLab revision is `c7248239f456cc877114ca1e67c5949fb4a7b958`; EventGuard-LoRa was reviewed read-only at `f7b6e44597abe958d7e9d6d481265d0fae33b749` and no restricted code was copied.

Raw frame events, original firmware wire identities, restored-state events, actual durable receipt assertions, failed attempts, configurations and source hashes accompany the summaries. A dirty-source manifest explicitly names the base HEAD plus file SHA256; it never presents an uncommitted code tree as that commit. Result hashes identify exact evidence. Simulated bytes are not RF energy, and host delay is not physical airtime.

## Validation scope and remaining gates

Phase 1.2 passed 393 tests per Python version, TCP 20/20, external 5/5 and public lab firmware. Phase 2 passed 496 per version, TCP 20/20, simulated LoRa 20/20 and external 5/5. Its 56 comparison runs all passed safety assertions; 13 finite delivery windows remained INCOMPLETE and are retained. Phase 3 passed 513 per version, real C snapshot 17/17 with 2800 oracle observations, TCP 20/20, external 5/5 and four firmware profiles. Final integrated counts and CI status are recorded below when complete.

No known P0 remains in the tested software paths. P1 deployment gates remain: commissioned RF endpoints for A/C, authenticated hostile-environment radio identity, a calibrated elapsed-time source, physical RTC/GPIO/AUX/reset/Flash behavior, and any stronger partition authority required by deployment. These are not masked by software PASS. P2 research work: MTU/rate/retry/priority sweeps, simultaneous gateway power cuts, long-duration receipt-capacity tests, Flash wear measurement and measured wake-window energy. Battery lifetime and agriculture field deployment are not claimed.

The default Deep Sleep provider explicitly rebuilds baseline when elapsed time is unknown, possibly requesting one initial upload per wake. Continuous temporal algorithm behavior is software-validated under trusted elapsed input; board-level continuity is pending. CRC provides integrity, not authentication, and command reception does not promise exactly-once physical execution.

## Final local validation

After the final snapshot counter/configuration and sleep-overflow audit, Python 3.10 passed **523 tests / 106.92 s**, Python 3.12 passed **523 / 100.85 s**; 27 targeted sanitizer/integration tests passed. The final snapshot harness passed **19/19** cases with **2800** oracle observations. The extra cases reject a maximum diagnostic counter and a null ladder configuration. The final simulated LoRa topology passed **20/20**; original TCP **20/20** and EdgeFaultLab **5/5** were rerun at Checkpoint C. Integrated 10/10 assertions were also rerun after audit. There are no unrun software scenarios in the requested matrix; physical RF/Deep Sleep/current experiments were not run because the hardware is unavailable.

All four final-source incremental IDF builds passed using the earlier isolated public SDK configurations; GitHub Actions rebuilds each profile from fresh defaults. Final local binaries: lab 831152 bytes; light-sleep 848736; LoRa 328560; Deep Sleep 350448. Exact binary/configuration/source hashes are in `results/research-phase123/validation/firmware-*-manifest.json` and `source_manifest.json`. The compiler was Xtensa GCC 14.2.0, ESP-IDF v5.4.4; Python was 3.10.21 and 3.12.14; the host compiler/version is recorded with the evidence.

GitHub Actions is configured for two Python versions, all TCP/LoRa/external scenarios, radio comparisons, snapshot/integration harnesses and four IDF profiles. Its actual run status will be recorded separately after the PR is created; local PASS does not imply Actions PASS.
