#pragma once
#include "b1_snapshot.h"
void b1_deep_sleep_task(void *);
/* Optional calibrated board source. Default returns false, never uses plan as
 * measured elapsed. */
bool b1_deep_elapsed(const b1_sleep_identity_t *, uint64_t *elapsed_ms,
                     uint64_t *error_ms);
bool b1_sleep_epoch_load(uint32_t *, char[3]);
bool b1_sleep_epoch_commit(uint32_t, const char *);
