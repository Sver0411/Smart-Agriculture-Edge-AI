# v0.3.1 software evidence

No hardware or RF results. See docs/V0_3_1_RELIABILITY_REPORT.md.

- release: 20/20 internal scenarios at source e9cf7a5; README/report bookkeeping dirty flags preserved.
- edgefaultlab-release: 5/5 independent process/proxy scenarios at pinned c7248239.
- final / final-acceptance and individual attempts: earlier stage evidence, unchanged.
- validation: staged full suites, Python 3.10 diagnostics, passing/cancelled/failed CI logs, host raw console.
- ci-acceptance.log: clean committed e9cf7a5 matrix, 231 tests per Python version plus 20 internal and 5 external scenarios.

Synthetic sensors and simulated actuators run on host TCP. Null is not measured; zero is observed only where instrumented. offline_queued / queue_replayed are compatibility names for all durable outbox staging / confirmed deletion, including online uploads.
