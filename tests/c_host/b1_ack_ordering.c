#include "b1.h"
#include "b1_policy.h"
#include "b1_storage.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
b1_stats_t b1_stats;
char b1_boot_id[B1_BOOT_ID_SIZE] = "host-test";
static bool restore_old;
static b1_record_t saved;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
bool b1_storage_save(void *c, unsigned slot, const b1_record_t *r) {
  (void)c;
  (void)slot;
  if (r)
    saved = *r;
  return true;
}
bool b1_storage_init(b1_outbox_t *q) {
  b1_outbox_init(q, b1_storage_save, NULL);
  return !restore_old || b1_outbox_restore(q, 0, &saved);
}
void b1_storage_lock(void) { assert(!pthread_mutex_lock(&lock)); }
void b1_storage_unlock(void) { assert(!pthread_mutex_unlock(&lock)); }
static b1_sample_t make(unsigned seq) {
  b1_sample_t s = {.seq = seq,
                   .monotonic_ms = seq * 1000,
                   .temperature = (float)(25 + seq),
                   .humidity = 60,
                   .valid = true,
                   .usable = true,
                   .upload_requested = true};
  s.temp_health.state = s.hum_health.state = SENSOR_STATE_HEALTHY;
  return s;
}
static void ack(unsigned seq, char kind) {
  char id[120];
  snprintf(id, sizeof(id), "B1-host-test-%08x-%c", seq, kind);
  assert(b1_queue_ack(id));
}
static void *duplicates(void *ctx) {
  (void)ctx;
  for (int i = 0; i < 1000; i++)
    assert(!b1_queue_ack("B1-host-test-00000002-S"));
  return NULL;
}
int main(void) {
  b1_policy_t p;
  assert(b1_policy_init(&p));
  b1_sample_t old = make(1), newer = make(2);
  b1_policy_mark_reported(&p, &newer);
  b1_policy_mark_reported(&p, &old);
  assert(p.scheduler.last_upload_t == 2 && p.reported_temperature == 27);
  assert(b1_queue_init());
  assert(b1_queue_sample(&old));
  assert(b1_queue_sample(&newer));
  b1_record_t r;
  assert(b1_queue_next(&r, 1000));
  assert(b1_queue_next(&r, 4000));
  assert(r.sequence == 2);
  ack(2, 'S');
  b1_sample_t confirmed;
  assert(b1_queue_take_confirmed(&confirmed) && confirmed.seq == 2);
  ack(1, 'S');
  assert(!b1_queue_take_confirmed(&confirmed));
  b1_sample_t alert = make(3);
  alert.alert_requested = true;
  assert(b1_queue_sample(&alert));
  assert(b1_queue_next(&r, 5000));
  ack(3, 'A');
  assert(!b1_queue_take_confirmed(&confirmed));
  ack(3, 'A');
  assert(!b1_queue_take_confirmed(&confirmed));
  ack(3, 'S');
  assert(b1_queue_take_confirmed(&confirmed) && confirmed.seq == 3);
  pthread_t a, b;
  assert(!pthread_create(&a, NULL, duplicates, NULL));
  assert(!pthread_create(&b, NULL, duplicates, NULL));
  assert(!pthread_join(a, NULL));
  assert(!pthread_join(b, NULL));
  assert(!b1_queue_take_confirmed(&confirmed));
  assert(b1_queue_init());
  assert(!b1_queue_take_confirmed(&confirmed));
  old = make(1);
  assert(b1_queue_sample(&old));
  assert(b1_queue_next(&r, 1000));
  ack(1, 'S');
  assert(b1_queue_take_confirmed(&confirmed) && confirmed.seq == 1);
  restore_old = true;
  strcpy(b1_boot_id, "new-boot");
  assert(b1_queue_init());
  assert(b1_queue_next(&r, 0));
  ack(3, 'S');
  ack(3, 'A');
  assert(!b1_queue_take_confirmed(
      &confirmed)); /* restored previous-boot evidence */
  puts("late/duplicate/reordered/companion/mailbox/reinitialization PASS");
}
