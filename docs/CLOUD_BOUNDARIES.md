# Cloud enhancement / learning interfaces — designed, pending

Cloud never commands C directly and never joins the real-time decision path. Existing capabilities: TCP ingestion, semantic validation, SQLite history, atomic dedup/commit receipt and versioned policy push. Gateway heartbeat now also preserves ownership/connectivity/outbox metadata in SQLite for future views.

## HTTP / Dashboard boundary

No HTTP listener or frontend is implemented in this round. A minimal read-only application can share the existing DB, without a broker, cluster or microservices:

| Proposed endpoint | View |
|---|---|
| GET /api/zones | fixed B1/C1, B2/C2 mapping; newest owner/epoch; data age |
| GET /api/sensors/:id/latest | newest sample, units, health, sample time and receipt time |
| GET /api/sensors/:id/history?from=&to=&limit= | bounded history / curves |
| GET /api/gateways | latest reported role, ownership, connectivity, queue depth/bytes/age/replay metrics |
| GET /api/alerts | bounded alert history and fault recovery |
| GET /api/controls | command, receipt/result distinction, UNKNOWN / NOT_DISPATCHED history |

Responses must carry observed_at/received_at and stale status. Cloud disconnect does not prove farm offline; a quiet battery B may be sleeping. Reports are snapshots, not live control authority. There is no proposed actuator POST API. Pagination/time-range bounds, authentication and a concrete dashboard are later work.

## Field dataset / offline learning boundary

Input contract for a future Dataset Builder: a consistent read-only Cloud DB snapshot, field campaign/crop/sensor calibration identifiers, physical message IDs/boot/sequence, timestamps/units, channel trust evidence, actuator history and independently defined labels/outcome windows. Retain rejected/suspect readings for audit; do not silently train on them or treat policy-imitation labels as agricultural ground truth.

Output: immutable versioned dataset plus manifest containing dataset_version, source campaign/snapshot hash, content SHA-256, feature schema/version, filtering/label protocol, units, train/validation/test grouping, and source_kind=`field-measured`. Split by time/zone/campaign to avoid leakage; record missing channels. Current physical B1 has only temperature/humidity and cannot supply all four learned-engine inputs. A new compatible feature contract would require evaluation before deployment.

The existing `ai.train.train(rows=...)` accepts feature/label rows and explicitly records `user-provided-unvalidated`; it is a software hook, not a field Dataset Builder. Do not relabel synthetic artifacts as field validated.

Future batch/scheduled job: Field Data → Cloud DB → Dataset Builder → Versioned Dataset → RTX GPU Offline Training → Candidate Model → Evaluation → Model Registry → Approved Deployment. Registry records dataset/model hashes, feature version, evaluation evidence and approval state. Approved model/policy rollout must validate compatibility and persist last-known-good at A before activation. Never retrain from each incoming sample. Dataset construction, labeled campaigns, GPU execution, registry and approval/rollout automation are pending; this document specifies their boundary rather than pretending they exist.
