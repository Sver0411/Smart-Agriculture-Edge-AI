#include "b1_outbox.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned first_slot, last_slot;
static uint64_t first_order, last_order;
static int calls;
static bool save(void *ctx, unsigned slot, const b1_record_t *r) {
  (void)ctx;
  assert(r);
  calls++;
  last_slot = slot;
  last_order = r->order;
  if (calls == 1) {
    first_slot = slot;
    first_order = r->order;
    return false;
  }
  return true;
}
int main(void) {
  static b1_outbox_t q;
  b1_outbox_init(&q, save, NULL);
  b1_record_t r = {.high = 1, .sequence = 1};
  strcpy(r.boot_id, "boot");
  strcpy(r.sample_id, "B1-boot-00000001");
  strcpy(r.wire, "{}\n");
  assert(!b1_outbox_admit(&q, &r));
  assert(b1_outbox_count(&q) == 0);
  r.sequence = 2;
  strcpy(r.sample_id, "B1-boot-00000002");
  assert(b1_outbox_admit(&q, &r));
  assert(last_slot != first_slot);
  assert(last_order > first_order);
  puts("uncertain save cannot overwrite slot/order: PASS");
}
