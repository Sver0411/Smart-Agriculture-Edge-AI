# Phase 2 — Bounded LoRa protocol and E220 firmware adapter

Checkpoint B follows Phase 1.2 commit `30ddbd0`. Evidence is in `results/research-phase2/`; manifests identify the base commit plus exact dirty-source SHA256 hashes. This stage implements a software protocol and a real ESP-IDF B1 UART path. No physical RF experiment was performed.

## Implemented scope

`common/lora` separates canonical JSON, logical delivery contracts, frame codec, bounded reassembly and seeded transport faults. The existing application handlers remain authoritative: sensor receipts and gateway outbox are committed before `PERSISTED_ACK`; server acknowledgement has its own durable boundary. A local UART submission or complete reassembly cannot release HIGH evidence. Commands still pass the existing controller SafetyGuard; reception ACK does not imply execution.

Field links B↔A, A↔C and A1↔A2 have role/type/zone validation. The host adapter uses fragmented frames and a TCP carrier for reassembled messages, while the server uplink continues over TCP. `experiments.runner --transport simulated-lora` exercises all seven original roles. Real hardware implementation is B1's UART E220 endpoint only; physical gateway/controller radio endpoints remain pending. Lab radio CRCs do not authenticate a sender. Gateway peer HMAC from Phase 1.2 remains an application contract.

## Wire format

All multibyte integers are little endian. Header size is 70 bytes; default frame MTU is 160, leaving 90 bytes per fragment. The abstract codec permits frames up to 256; the commissioned B1 adapter caps submitted frames at 200. Messages are limited to 4096 bytes, 64 fragments and four C reassembly slots. Oversize data is rejected, never truncated.

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 2 | Magic `AL` |
| 2 | 1 | Protocol version 1 |
| 3–7 | 5 | Type, source, destination, zone, reserved flags |
| 8 | 16 | Boot/session nonce |
| 24 | 16 | SHA256 prefix of full logical message ID |
| 40 | 4 | Sequence |
| 44 | 4 | Generation |
| 48–57 | 10 | Fragment index/count, total bytes, fragment bytes, chunk bytes (u16 each) |
| 58 | 4 | Full message CRC32 |
| 62 | 4 | Fragment payload CRC32 |
| 66 | 4 | Frame CRC32, including header |
| 70 | variable | Fragment payload |

Full original IDs remain in JSON and are checked against the compact header after reassembly. A 128-bit hash has a birthday collision scale of about 2^64 identities; it is a lookup key, not cryptographic sender authentication. Metadata disagreements and conflicting duplicates quarantine a slot. Fixed deadlines are not extended by duplicate fragments. Unknown version, source/zone, arithmetic/length inconsistencies and CRC failures are rejected before application admission. Clock rollback clears receiver state. Completed logical retries still reach application deduplication so a lost durable ACK can be recovered.

Canonical JSON sorts keys; C uses cJSON's numeric rendering. This is deterministic within each serializer, not a claim of RFC8785 signing interoperability. Fragment keys include the full-message CRC, so a new wire attempt's delivery-age metadata cannot mix with an old attempt.

## E220 constraints and driver

The reference is the [Ebyte E220-900T22D manual](https://www.ebyte.com/Uploadfiles/Files/2021-7-6/202176188184448.pdf). That model documents UART, M0/M1 modes, AUX state, selectable packet lengths and its own buffering. The actual user's module model/configuration has not been supplied; air rate, physical packet timing, channel, power, RF losses and energy remain unmeasured.

`b1_e220.c` implements ESP-IDF UART initialization, GPIO validation, mode changes, bounded AUX waits, exact register readback, byte stream reception, explicit errors and shutdown. Commissioned 8-byte register expectations are mandatory. The public CI string is an illustrative test configuration, not a factory setting or verified device. The driver reads and verifies settings; it does not guess RF frequency/power or overwrite module configuration. Pins/baud/MTU/timeouts are configurable. RSSI trailers/fixed-address mode are not supported by this transparent framing profile.

Audit found that clearing partial data after each 200 ms receive poll could truncate normal 9600-baud frames. The final driver retains data across polls and clears it only after bounded inter-byte idle or clock rollback. The real C stream tests cover preservation across poll boundaries and expiry. AUX/UART success still means local submission; only gateway durable ACK retires B1 evidence. Hardware AUX timing, mode transition and shutdown/current must be measured.

## Tests and experiments

Initial results: 98 radio tests passed, Python 3.10/3.12 full suites each passed 491 tests. A final full regression includes additional retry-clock rejection tests and the UART fix; its exact totals are in the final validation logs. The C codec/parser/reassembler is compiled with ASan/UBSan, compared byte-for-byte with Python, and fed 1000 seed-42 malformed frames.

All 20 existing scenarios passed in host simulated LoRa mode; all 20 passed again in original TCP mode. All five independent EdgeFaultLab scenarios passed. The comparison harness ran 14 cases × four policies = 56 runs: all 56 safety assertion sets passed, while 13 delivery windows were INCOMPLETE. Reliable/event-priority each completed 12/14 cases, fixed retry 11/14, no retry 8/14. Partial-fragment and ACK-loss failures are retained. Safety PASS is not delivery success.

The four policies compare five bounded reliable attempts, one no-retry attempt, three fixed attempts, and HIGH-first admission with five attempts. Metrics include logical count, frame count, simulated bytes, duplicates, admitted/confirmed ratio, host latency and failures. Seed 42 and accelerated 50 ms ACK waits describe a host experiment, not physical RF timing or energy. Session mismatch and old-generation checks are explicit production-code subcases; gateway failover and queue congestion use actual Gateway/SQLite endpoints. Real C firmware serialization produces the business identities. Receiver restart clears simulated reassembly memory; it is not a physical module power-cycle.

First comparison failure (tuple receipt rows misread as mappings), first firmware compiler failure, and all incomplete deliveries remain in the evidence tree. Final IDF v5.4.4 lora-prototype builds execute the nonempty radio path; binary hashes and size evidence are recorded separately. No original results were removed.

## Remaining boundaries

P1 deployment gates: commission/measure real E220 endpoints, provision authenticated radio identity for hostile environments, and validate hardware timing before deployment. P2: measure airtime/latency across MTU/rate/retry policies; add physical A/C endpoints; quantify receipt/outbox capacity operationally. General asymmetric partitions still need an external lease/quorum authority for arbitrary-network consistency; this protocol does not supply one. No exactly-once physical actuation, battery-life gain or agricultural field deployment is claimed.

Final checkpoint validation after the UART fix: Python 3.10 **496 passed / 125.92 s**; Python 3.12 **496 passed / 89.42 s**. IDF v5.4.4 lora-prototype **PASS**, binary 328656 bytes, SHA256 `8f977aa6b892e818aaefbfc0e7ee4feb727664d0dfb331f7f2542681a166363e`. All final logs and exact source hashes are retained. The first build's larger Wi-Fi image differs because the final radio profile links the enabled radio path and omits unused Wi-Fi task code.
