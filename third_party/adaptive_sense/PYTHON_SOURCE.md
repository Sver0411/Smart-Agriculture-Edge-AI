# Python reuse

Source: https://github.com/Sver0411/AdaptiveSense/tree/6e0d086
Pinned full revision: docs/integration_sources.json. MIT licence: PYTHON_LICENSE.

`simulator/scoring.py` → `sensor_node/change_detector.py` (direct reuse).
`simulator/adaptive.py` → `sensor_node/adaptive_scheduler.py` (imports adapted).
`AdaptiveSense` trust gate and configuration translator are agriculture-specific.
No claim of C parity for the new agriculture adapter; upstream core parity is separate.
