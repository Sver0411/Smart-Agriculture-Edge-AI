#pragma once
#include "b1_checkpoint.h"
typedef enum {
  B1_STORE_OK,
  B1_STORE_MISSING,
  B1_STORE_ERROR
} b1_store_result_t;
typedef struct {
  /* Scratch avoids large task/boot stack allocations. Serialize all calls. */
  unsigned char scratch[B1_CHECKPOINT_MAX];
  b1_record_t recovering;
  void *ctx;
  b1_store_result_t (*read)(void *, unsigned, unsigned char *, size_t *);
  b1_store_result_t (*write)(void *, unsigned, const unsigned char *, size_t);
  b1_store_result_t (*remove)(void *, unsigned);
  b1_store_result_t (*commit)(void *);
} b1_store_backend_t;
bool b1_backend_save(void *, unsigned, const b1_record_t *);
bool b1_backend_load(b1_store_backend_t *, b1_outbox_t *);
