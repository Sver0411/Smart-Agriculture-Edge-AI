#include "b1_store_backend.h"
bool b1_backend_save(void *ctx, unsigned slot, const b1_record_t *r) {
  b1_store_backend_t *b = ctx;
  if (!b || slot >= B1_OUTBOX_CAPACITY)
    return false;
  unsigned char *blob = b->scratch;
  b1_store_result_t status;
  if (r) {
    size_t n = b1_checkpoint_encode(r, blob, B1_CHECKPOINT_MAX);
    if (!n)
      return false;
    status = b->write(b->ctx, slot, blob, n);
  } else
    status = b->remove(b->ctx, slot);
  if (status != B1_STORE_OK && !(status == B1_STORE_MISSING && !r))
    return false;
  /* Missing after a failed erase commit still requires a successful commit. */
  return b->commit(b->ctx) == B1_STORE_OK;
}
bool b1_backend_load(b1_store_backend_t *b, b1_outbox_t *q) {
  unsigned char *blob = b->scratch;
  b1_record_t *r = &b->recovering;
  b1_outbox_init(q, b1_backend_save, b);
  for (unsigned slot = 0; slot < B1_OUTBOX_CAPACITY; slot++) {
    size_t n = B1_CHECKPOINT_MAX;
    b1_store_result_t result = b->read(b->ctx, slot, blob, &n);
    if (result == B1_STORE_MISSING)
      continue;
    if (result != B1_STORE_OK || n > B1_CHECKPOINT_MAX ||
        !b1_checkpoint_decode(blob, n, r) || !b1_outbox_restore(q, slot, r))
      return false;
  }
  return true; /* On failure caller must not start delivery; preserve storage.
                */
}
