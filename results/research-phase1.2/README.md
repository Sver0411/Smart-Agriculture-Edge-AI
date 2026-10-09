# Phase 1.2 evidence

This directory is new; earlier research evidence is preserved. See [development report](../../docs/research/PHASE1_2_DEVELOPMENT_REPORT.md).

- validation/: original failures, targeted C/Python assertions, full regressions, source hashes and public ESP-IDF build logs.
- scenarios/: all 20 internal seven-role TCP scenarios, seed 42, configuration, raw events, assertions and summaries.
- edgefaultlab/: five independent fault scenarios at the reviewed external revision.

Source manifests record the actual base HEAD and dirty state plus functional file hashes. A base SHA is not falsely presented as the hash of uncommitted changes. Test counts are per Python environment and are not summed. Host faults/builds do not establish physical RF, NVS power-loss safety or energy savings.
