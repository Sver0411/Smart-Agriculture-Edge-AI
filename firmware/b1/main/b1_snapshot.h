#pragma once
#include "b1_policy.h"
#include <stddef.h>
#define B1_SNAPSHOT_MAX 6000u
#define B1_SNAPSHOT_VERSION 1u
typedef struct {
  uint32_t sequence, generation;
  char owner[3], previous_boot[B1_BOOT_ID_SIZE];
  uint64_t saved_ms, planned_sleep_ms;
  uint64_t next_boot_counter, boot_counter_limit;
} b1_sleep_identity_t;
typedef enum {
  B1_RESTORE_REJECTED = 0,
  B1_RESTORE_CONTINUOUS = 1,
  B1_RESTORE_TIME_UNKNOWN = 2
} b1_restore_result_t;
/* IEEE754 binary32/64, LE integer widths, explicit fields; no pointers/padding.
 * Decode is transactional. Unknown schema/profile/CRC reject without mutation.
 * current_ms is a logical algorithm time, never a reset esp_timer timestamp. */
bool b1_snapshot_encode(const b1_policy_t *, const b1_sleep_identity_t *,
                        uint8_t *, size_t, size_t *);
b1_restore_result_t
b1_snapshot_restore(b1_policy_t *, b1_sleep_identity_t *, const uint8_t *,
                    size_t, uint32_t minimum_generation, bool elapsed_trusted,
                    uint64_t elapsed_ms, uint64_t *current_ms);
bool b1_sleep_next_sequence(b1_sleep_identity_t *, uint32_t *);
bool b1_boot_lease_take(b1_sleep_identity_t *, uint64_t persisted_limit,
                        bool rtc_valid, bool *reserve, uint64_t *counter);
/* Persist only on ownership changes; CRC protects corruption, not
 * authentication. */
bool b1_epoch_encode(uint32_t, const char *, uint8_t[16]);
bool b1_epoch_decode(const uint8_t[16], uint32_t *, char[3]);
