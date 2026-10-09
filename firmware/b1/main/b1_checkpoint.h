#pragma once
#include "b1_outbox.h"
#define B1_CHECKPOINT_MAX                                                      \
  (44 + B1_BOOT_ID_SIZE - 1 + B1_SAMPLE_ID_SIZE - 1 + B1_WIRE_SIZE - 1)
/* v2 explicit little-endian wire format; v1 read only, same ABI only. */
size_t b1_checkpoint_encode(const b1_record_t *, unsigned char *, size_t);
bool b1_checkpoint_decode(const unsigned char *, size_t, b1_record_t *);
