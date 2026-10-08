Repository: https://github.com/Sver0411/AdaptiveSense

Commit: `6e0d086cf14c81d2fb5dba8305e13a7dff2dae3b`

Imported files: `firmware/main/change_detector.{c,h}` and `firmware/main/adaptive_scheduler.{c,h}` into `firmware/b1/components/adaptive_sense/`.

License: MIT, preserved in this directory.

Local changes in the deployment realignment: upload on confirmed event recovery as well as onset; retain a per-channel last-upload validity mask so newly available channels do not compare against zero. Host parity tests cover these adaptations. B1's `b1_policy.c` supplies integration parameters. Laboratory time constants and interval ladders are accelerated; they are integration settings, not a new algorithm or deployment claim.
