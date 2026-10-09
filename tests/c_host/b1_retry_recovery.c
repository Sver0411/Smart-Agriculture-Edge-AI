#include "b1_outbox.h"
#include "b1_retry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static b1_outbox_t q;
static unsigned writes;
static bool store(void *ctx, unsigned slot, const b1_record_t *r) {
  (void)ctx;
  (void)slot;
  (void)r;
  writes++;
  return true;
}
static b1_record_t sample(unsigned seq) {
  b1_record_t r = {.high = 1, .sequence = seq};
  strcpy(r.boot_id, "retry-boot");
  snprintf(r.sample_id, sizeof(r.sample_id), "B1-retry-boot-%08x", seq);
  strcpy(r.wire, "{}\n");
  return r;
}
int main(void) {
  b1_outbox_init(&q, store, NULL);
  b1_record_t r = sample(1);
  assert(b1_outbox_admit(&q, &r));
  for (unsigned i = 0; i < 5; i++) {
    uint64_t now = i * 100000;
    assert(b1_outbox_next(&q, now) >= 0);
    b1_outbox_tick(&q, now + 3000);
  }
  assert(q.entries[0].state == B1_FAILED && b1_outbox_count(&q) == 1);
  /* Gateway returns without a B reboot. Keep logical identity and retry. */
  int slot = b1_outbox_next(&q, 10000000);
  assert(slot >= 0);
  assert(strcmp(q.entries[slot].record.sample_id, r.sample_id) == 0);
  assert(writes == 1);
  assert(b1_outbox_ack(&q, "B1-retry-boot-00000001-S"));
  assert(!b1_outbox_count(&q));
  assert(writes == 2);
  /* One hour offline with virtual seconds: rate is bounded, HIGH retained. */
  b1_outbox_init(&q, store, NULL);
  r = sample(2);
  assert(b1_outbox_admit(&q, &r));
  unsigned before = writes;
  for (uint64_t now = 0; now < 3600000; now += 1000) {
    int ready = b1_outbox_next(&q, now);
    if (ready >= 0)
      assert(strcmp(q.entries[ready].record.sample_id, r.sample_id) == 0);
    assert(b1_outbox_count(&q) == 1 && writes == before);
  }
  assert(q.boot_attempts >= 6 && q.boot_attempts <= 12);
  printf("one-hour attempts=%llu probes=%lu retained=%u\n",
         (unsigned long long)q.boot_attempts, (unsigned long)q.probes,
         b1_outbox_count(&q));
  assert(b1_outbox_next(&q, q.now_ms - 1) == -1);
  assert(b1_outbox_next(&q, UINT64_MAX) == -1);
  assert(b1_outbox_ack(&q, "B1-retry-boot-00000002-S"));
  /* Registration/contact cannot reset a failed message's cooldown. */
  b1_link_retry_t link = {0};
  uint64_t now = 0;
  for (unsigned i = 0; i < 20; i++) {
    assert(b1_link_ready(&link, now));
    b1_link_failed(&link, now);
    assert(!b1_link_ready(&link, now));
    assert(link.due_ms - now <= B1_PROBE_MAX_MS);
    if (i >= 5)
      assert(link.due_ms - now >= B1_PROBE_MIN_MS);
    now = link.due_ms;
  }
  b1_link_confirmed(&link);
  assert(b1_link_ready(&link, now));
  /* Failed entries preserve FIFO order at a shared recovery opportunity. */
  b1_outbox_init(&q, store, NULL);
  for (unsigned seq = 10; seq < 13; seq++) {
    r = sample(seq);
    assert(b1_outbox_admit(&q, &r));
    q.entries[seq - 10].state = B1_FAILED;
    q.entries[seq - 10].attempts = 5;
    q.entries[seq - 10].total_attempts = 5;
    q.entries[seq - 10].probe_delay_ms = B1_PROBE_MIN_MS;
  }
  for (unsigned seq = 10; seq < 13; seq++) {
    int ready = b1_outbox_next(&q, 10000000);
    assert(ready >= 0 && q.entries[ready].record.sequence == seq);
    char id[120];
    snprintf(id, sizeof(id), "B1-retry-boot-%08x-S", seq);
    assert(b1_outbox_ack(&q, id));
  }
  assert(!b1_outbox_count(&q));
  /* Seeded event interleavings: retries never mutate identity or evict HIGH. */
  b1_outbox_init(&q, store, NULL);
  uint32_t seed = 42, seq = 100;
  uint64_t clock = 0;
  for (unsigned step = 0; step < 20000; step++) {
    seed = seed * 1664525u + 1013904223u;
    clock += 137;
    unsigned before_count = b1_outbox_count(&q);
    if (seed % 3 == 0) {
      r = sample(seq++);
      r.high = (seed >> 8) & 1;
      r.has_alert = (seed >> 9) & 1;
      bool admitted = b1_outbox_admit(&q, &r);
      assert(b1_outbox_count(&q) == before_count + (admitted ? 1 : 0));
    } else if (seed % 3 == 1) {
      int ready = b1_outbox_next(&q, clock);
      assert(b1_outbox_count(&q) == before_count);
      if (ready >= 0)
        assert(b1_record_valid(&q.entries[ready].record));
    } else {
      unsigned index = (seed >> 16) % B1_OUTBOX_CAPACITY;
      b1_entry_t *e = &q.entries[index];
      char id[120];
      snprintf(id, sizeof(id), "%s-%c", e->record.sample_id,
               (seed & 1) ? 'S' : 'A');
      bool accepted = b1_outbox_ack(&q, id);
      if (before_count != b1_outbox_count(&q))
        assert(accepted && !e->active &&
               e->ack_mask == (e->record.has_alert ? 3 : 1));
    }
    assert(b1_outbox_count(&q) <= B1_OUTBOX_CAPACITY);
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++)
      if (q.entries[i].active) {
        assert(b1_record_valid(&q.entries[i].record));
        for (unsigned j = i + 1; j < B1_OUTBOX_CAPACITY; j++)
          if (q.entries[j].active)
            assert(strcmp(q.entries[i].record.sample_id,
                          q.entries[j].record.sample_id));
      }
  }
  puts("20000 seeded state transitions: PASS");
  puts("automatic recovery / low-frequency / FIFO / reconnect budgets: PASS");
}
