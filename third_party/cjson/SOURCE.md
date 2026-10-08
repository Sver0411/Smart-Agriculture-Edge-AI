# cJSON host serialization reference

- Upstream: https://github.com/DaveGamble/cJSON
- Commit: `c859b25da02955fef659d658b8f324b5cde87be3`
- Obtained from the local ESP-IDF 5.4.4 `components/json/cJSON` submodule.
- Files: unmodified `cJSON.c`, `cJSON.h`, MIT `LICENSE`.
- Used only by host firmware serialization/parity tests. Firmware continues to
  link ESP-IDF's JSON component. No RF delivery is implied by host serialization.
