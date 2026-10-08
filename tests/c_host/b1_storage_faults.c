#include "b1_store_backend.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char disk[16][B1_CHECKPOINT_MAX], staged[16][B1_CHECKPOINT_MAX];
static size_t sizes[16], pending[16];
static bool dirty[16];
static int mode, writes, commits; /* 1 set,2 commit before,3 commit after,4
                                     partial,5 erase,6 full,7 read */
static b1_store_result_t read_(void *c, unsigned s, unsigned char *p,
                               size_t *n) {
  (void)c;
  if (mode == 7)
    return B1_STORE_ERROR;
  if (!sizes[s])
    return B1_STORE_MISSING;
  if (*n < sizes[s])
    return B1_STORE_ERROR;
  memcpy(p, disk[s], sizes[s]);
  *n = sizes[s];
  return B1_STORE_OK;
}
static b1_store_result_t write_(void *c, unsigned s, const unsigned char *p,
                                size_t n) {
  (void)c;
  writes++;
  if (mode == 1 || mode == 6)
    return B1_STORE_ERROR;
  pending[s] = mode == 4 ? n / 2 : n;
  memcpy(staged[s], p, pending[s]);
  dirty[s] = true;
  return B1_STORE_OK;
}
static b1_store_result_t erase_(void *c, unsigned s) {
  (void)c;
  if (mode == 5)
    return B1_STORE_ERROR;
  if (dirty[s] && !pending[s])
    return B1_STORE_MISSING;
  pending[s] = 0;
  dirty[s] = true;
  return B1_STORE_OK;
}
static b1_store_result_t commit_(void *c) {
  (void)c;
  commits++;
  if (mode == 2)
    return B1_STORE_ERROR;
  for (unsigned s = 0; s < 16; s++)
    if (dirty[s]) {
      sizes[s] = pending[s];
      memcpy(disk[s], staged[s], sizes[s]);
      dirty[s] = false;
    }
  return mode == 3 ? B1_STORE_ERROR : B1_STORE_OK;
}
static b1_store_backend_t b = {
    .read = read_, .write = write_, .remove = erase_, .commit = commit_};
static b1_outbox_t q;
static void reset(void) {
  memset(sizes, 0, sizeof(sizes));
  memset(dirty, 0, sizeof(dirty));
  mode = 0;
  assert(b1_backend_load(&b, &q));
}
static bool reboot(void) {
  memset(dirty, 0, sizeof(dirty));
  return b1_backend_load(&b, &q);
}
static b1_record_t sample(unsigned seq) {
  b1_record_t r = {.sequence = seq, .high = 1};
  strcpy(r.boot_id, "boot");
  snprintf(r.sample_id, sizeof(r.sample_id), "B1-boot-%08x", seq);
  strcpy(r.wire, "{}\n");
  return r;
}
int main(void) {
  for (int m = 1; m <= 3; m++) {
    reset();
    b1_record_t r = sample(1);
    mode = m;
    assert(!b1_outbox_admit(&q, &r));
    assert(!b1_outbox_count(&q) && q.entries[0].quarantined);
    mode = 0;
    r = sample(2);
    assert(b1_outbox_admit(&q, &r));
    assert(q.entries[1].active && q.entries[1].record.order == 2);
    assert(reboot());
    assert(b1_outbox_count(&q) ==
           (m == 1 ? 1 : 2)); /* later commit may publish earlier staged data */
  }
  reset();
  b1_record_t r = sample(1);
  assert(b1_outbox_admit(&q, &r));
  assert(b1_outbox_next(&q, 0) == 0);
  mode = 5;
  assert(!b1_outbox_ack(&q, "B1-boot-00000001-S"));
  assert(q.entries[0].active);
  mode = 2;
  assert(!b1_outbox_ack(&q, "B1-boot-00000001-S"));
  assert(q.entries[0].active);
  /* Pending erase says MISSING on retry. It still MUST commit. */
  int before = commits;
  mode = 0;
  assert(b1_outbox_ack(&q, "B1-boot-00000001-S"));
  assert(commits == before + 1);
  assert(reboot() && !b1_outbox_count(&q));
  reset();
  mode = 4;
  r = sample(1);
  assert(b1_outbox_admit(&q, &r));
  mode = 0;
  assert(!reboot());
  assert(
      sizes[0] >
      0); /* partial backend violates successful-write contract; boot refuses */
  reset();
  r = sample(1);
  assert(b1_outbox_admit(&q, &r));
  size_t n = sizes[0];
  unsigned char original[B1_CHECKPOINT_MAX];
  memcpy(original, disk[0], n);
  for (size_t i = 0; i < n; i++) {
    disk[0][i] ^= 1;
    assert(!reboot());
    disk[0][i] ^= 1;
  } /* CRC covers metadata and payload */
  mode = 7;
  assert(!reboot());
  assert(!memcmp(original, disk[0], n));
  mode = 0;
  assert(reboot());
  assert(!b1_outbox_restore(
      &q, 1, &q.entries[0].record)); /* duplicate identity/order */
  /* v2 independent from padding, exact length and version; old native v1
   * read-only. */
  b1_record_t decoded;
  assert(b1_checkpoint_decode(original, n, &decoded));
  assert(decoded.sequence == 1);
  assert(!b1_checkpoint_decode(original, n - 1, &decoded));
  assert(!b1_checkpoint_decode(original, n + 1, &decoded));
  b1_record_t legacy = q.entries[0].record;
  size_t oldn = offsetof(b1_record_t, wire) + strlen(legacy.wire) + 1;
  assert(b1_checkpoint_decode((const unsigned char *)&legacy, oldn, &decoded));
  legacy.version = 9;
  assert(!b1_checkpoint_decode((const unsigned char *)&legacy, oldn, &decoded));
  reset();
  mode = 6;
  r = sample(1);
  assert(!b1_outbox_admit(&q, &r));
  assert(!b1_outbox_count(&q));
  mode = 0;
  for (unsigned i = 2; i <= 16; i++) {
    r = sample(i);
    assert(b1_outbox_admit(&q, &r));
  }
  r = sample(17);
  assert(!b1_outbox_admit(&q, &r));
  assert(reboot() && b1_outbox_count(&q) == 15);
  r = sample(0);
  assert(!b1_outbox_admit(&q, &r));
  r = sample(18);
  memset(r.sample_id, 'x', sizeof(r.sample_id));
  assert(!b1_outbox_admit(&q, &r));
  reset();
  r = sample(0xffffffff);
  memset(r.wire, 'x', sizeof(r.wire) - 1);
  r.wire[sizeof(r.wire) - 2] = '\n';
  r.wire[sizeof(r.wire) - 1] = 0;
  assert(b1_outbox_admit(&q, &r));
  assert(reboot());
  q.next_order = UINT64_MAX;
  r = sample(2);
  assert(!b1_outbox_admit(&q, &r));
  printf("set/commit/erase/partial/corruption/capacity/restart/version/"
         "identity/boundary PASS; writes=%d commits=%d\n",
         writes, commits);
}
