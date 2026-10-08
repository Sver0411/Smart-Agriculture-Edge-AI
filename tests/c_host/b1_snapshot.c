#include "b1_snapshot.h"
#include "agri_lora.h"
#include <assert.h>
#include <math.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned observations;
static void crc(uint8_t *b, size_t n) {
  memset(b + 12, 0, 4);
  uint32_t x = al_crc32(b, n);
  for (unsigned i = 0; i < 4; i++)
    b[12 + i] = (uint8_t)(x >> (i * 8));
}
static b1_sleep_identity_t identity(void) {
  b1_sleep_identity_t i = {.generation = 3,
                           .planned_sleep_ms = 1000,
                           .owner = "A2",
                           .previous_boot = "host-old"};
  return i;
}
static void same(const b1_sample_t *a, const b1_sample_t *b) {
  assert(a->seq == b->seq && a->temp_health.state == b->temp_health.state &&
         a->temp_health.fault_flags == b->temp_health.fault_flags &&
         a->hum_health.fault_flags == b->hum_health.fault_flags);
  assert(a->usable == b->usable && a->upload_requested == b->upload_requested &&
         a->upload_reasons == b->upload_reasons &&
         a->next_interval_ms == b->next_interval_ms &&
         a->detected_event == b->detected_event &&
         a->recovered == b->recovered);
  assert((isnan(a->score) && isnan(b->score)) ||
         fabsf(a->score - b->score) < 0.00001f);
  observations++;
}
static void continuity(const char *mode) {
  b1_policy_t continuous, restored;
  assert(b1_policy_init(&continuous) && b1_policy_init(&restored));
  b1_sleep_identity_t id = identity();
  uint8_t raw[B1_SNAPSHOT_MAX], other[B1_SNAPSHOT_MAX];
  size_t n, m;
  unsigned events = 0, faults = 0, recoveries = 0;
  for (unsigned step = 1; step <= 400; step++) {
    float temp = 25 + 0.2f * sinf(step * .1f),
          hum = 60 + .3f * cosf(step * .1f);
    bool valid = true;
    if (!strcmp(mode, "event") && step % 80 > 10 && step % 80 < 25)
      temp += (step % 80 - 10) * .6f;
    if (!strcmp(mode, "range") && step % 80 > 20 && step % 80 < 30)
      temp = 150;
    if (!strcmp(mode, "missing") && step % 80 > 20 && step % 80 < 30)
      valid = false;
    if (!strcmp(mode, "stuck")) {
      temp = 25;
      hum = 60;
    }
    if (!strcmp(mode, "drift")) {
      temp = 20 + step * .03f;
      hum = 50 + step * .12f;
    }
    if (!strcmp(mode, "spike") && step % 17 == 0)
      temp += 6;
    b1_sample_t a = {.seq = step,
                     .monotonic_ms = step * 1000,
                     .temperature = temp,
                     .humidity = hum,
                     .valid = valid},
                b = a;
    b1_policy_update(&continuous, &a);
    b1_policy_update(&restored, &b);
    same(&a, &b);
    if(getenv("B1_SNAPSHOT_TRACE"))printf("{\"event\":\"RESTORE_ORACLE_SAMPLE\",\"case\":\"%s\",\"seq\":%u,\"monotonic_ms\":%llu,\"temperature\":%.6f,\"valid\":%s,\"flags\":%u,\"state\":%d,\"upload_reasons\":%u,\"detected_event\":%s,\"oracle_matches\":true}\n",mode,step,(unsigned long long)a.monotonic_ms,(double)temp,valid?"true":"false",a.temp_health.fault_flags,a.temp_health.state,a.upload_reasons,a.detected_event?"true":"false");
    events += a.detected_event;
    faults += a.temp_health.fault_flags != 0;
    recoveries += a.recovered;
    /* Same explicit confirmation boundary in oracle and restored variant. */
    if (a.upload_requested && step % 3 == 0) {
      b1_policy_mark_reported(&continuous, &a);
      b1_policy_mark_reported(&restored, &b);
    }
    id.sequence = step;
    id.saved_ms = step * 1000;
    assert(b1_snapshot_encode(&restored, &id, raw, sizeof(raw), &n));
    assert(b1_snapshot_encode(&continuous, &id, other, sizeof(other), &m));
    assert(n == m && !memcmp(raw, other, n));
    uint64_t now = 0;
    b1_policy_t wake;
    assert(b1_snapshot_restore(&wake, &id, raw, n, 3, true, 1000, &now) ==
               B1_RESTORE_CONTINUOUS &&
           now == (step + 1) * 1000);
    restored = wake;
    restored.detector.cfg = &restored.cd_config;
    restored.scheduler.cfg = &restored.as_config;
  }
  if (!strcmp(mode, "event"))
    assert(events > 0);
  if (strcmp(mode, "healthy"))
    assert(faults > 0 || events > 0);
  if (!strcmp(mode, "range") || !strcmp(mode, "missing") ||
      !strcmp(mode, "spike"))
    assert(recoveries > 0);
  printf("{\"case\":\"%s\",\"observations\":%u,\"events\":%u,\"faults\":%u,"
         "\"recoveries\":%u,\"snapshot_bytes\":%zu}\n",
         mode, observations, events, faults, recoveries, n);
}
static void bounds(const char *mode) {
  b1_policy_t p, q;
  assert(b1_policy_init(&p) && b1_policy_init(&q));
  b1_sleep_identity_t id = identity(), out = identity();
  id.saved_ms = 1000;
  id.sequence = 1;
  b1_sample_t sample = {.seq = 1,
                        .monotonic_ms = 1000,
                        .temperature = 25,
                        .humidity = 60,
                        .valid = true};
  b1_policy_update(&p, &sample);
  b1_policy_mark_reported(&p, &sample);
  uint8_t raw[B1_SNAPSHOT_MAX], copy[B1_SNAPSHOT_MAX];
  size_t n = 0;
  assert(b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
  memcpy(copy, raw, n);
  uint64_t now = 999;
  if (!strcmp(mode, "unknown-time")) {
    assert(b1_snapshot_restore(&q, &out, raw, n, 3, false, 0, &now) ==
           B1_RESTORE_TIME_UNKNOWN);
    assert(now == 0 && out.sequence == 1 && out.generation == 3 &&
           !q.has_confirmed && !q.scheduler.has_uploaded &&
           q.detector.hist_len[0] == 0);
    sample.seq = 2;
    sample.monotonic_ms = 10;
    b1_policy_update(&q, &sample);
    assert(!sample.detected_event && (sample.upload_reasons & UP_FIRST_SAMPLE));
  } else if (!strcmp(mode, "sequence")) {
    id.sequence = UINT32_MAX - 1;
    uint32_t seq;
    assert(b1_sleep_next_sequence(&id, &seq) && seq == UINT32_MAX);
    assert(!b1_sleep_next_sequence(&id, &seq));
  } else if (!strcmp(mode, "epoch")) {
    uint8_t e[16];
    uint32_t gen;
    char owner[3];
    assert(b1_epoch_encode(42, "A2", e));
    assert(b1_epoch_decode(e, &gen, owner) && gen == 42 &&
           !strcmp(owner, "A2"));
    e[8] ^= 1;
    assert(!b1_epoch_decode(e, &gen, owner));
    assert(!b1_epoch_encode(0, "A1", e));
    assert(b1_snapshot_restore(&q, &out, raw, n, 4, true, 1000, &now) ==
           B1_RESTORE_REJECTED);
  } else if (!strcmp(mode, "truncated")) {
    for (size_t i = 0; i < n; i++)
      assert(b1_snapshot_restore(&q, &out, raw, i, 3, true, 0, &now) ==
             B1_RESTORE_REJECTED);
  } else if (!strcmp(mode, "bit-corruption")) {
    for (size_t i = 0; i < n; i++) {
      raw[i] ^= 1;
      assert(b1_snapshot_restore(&q, &out, raw, n, 3, true, 0, &now) ==
             B1_RESTORE_REJECTED);
      raw[i] ^= 1;
    }
  } else if (!strcmp(mode, "version")) {
    raw[4] = 2;
    crc(raw, n);
    assert(b1_snapshot_restore(&q, &out, raw, n, 3, true, 0, &now) ==
           B1_RESTORE_REJECTED);
  } else if (!strcmp(mode, "profile")) {
    raw[8] ^= 1;
    crc(raw, n);
    assert(b1_snapshot_restore(&q, &out, raw, n, 3, true, 0, &now) ==
           B1_RESTORE_REJECTED);
  } else if (!strcmp(mode, "state-capacity")) {
    p.temperature.window_count = 65;
    assert(!b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
  } else if (!strcmp(mode,"counter-max")) {
    p.temperature.spike_confirmed_count=INT_MAX;assert(!b1_snapshot_encode(&p,&id,raw,sizeof(raw),&n));
  } else if (!strcmp(mode,"config-null")) {
    p.as_config.ladders[0]=NULL;assert(!b1_snapshot_encode(&p,&id,raw,sizeof(raw),&n));
  } else if (!strcmp(mode, "clock-overflow")) {
    assert(b1_snapshot_restore(&q, &out, raw, n, 3, true, UINT64_MAX, &now) ==
           B1_RESTORE_REJECTED);
  } else if (!strcmp(mode, "lease")) {
    id.next_boot_counter = 1;
    id.boot_counter_limit = 256;
    assert(b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
    assert(b1_snapshot_restore(&q, &out, raw, n, 3, true, 0, &now) ==
           B1_RESTORE_CONTINUOUS);
    assert(out.next_boot_counter == 1 && out.boot_counter_limit == 256);
    id.next_boot_counter = 258;
    assert(!b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
    id.next_boot_counter = 0;
    id.boot_counter_limit = 0;
    bool reserve;
    uint64_t count;
    assert(b1_boot_lease_take(&id, 0, false, &reserve, &count) && reserve &&
           count == 1 && id.boot_counter_limit == 256);
    for (unsigned i = 2; i <= 256; i++)
      assert(b1_boot_lease_take(&id, 256, true, &reserve, &count) && !reserve &&
             count == i);
    assert(b1_boot_lease_take(&id, 256, true, &reserve, &count) && reserve &&
           count == 257 && id.boot_counter_limit == 512);
    assert(b1_boot_lease_take(&id, 512, false, &reserve, &count) && reserve &&
           count == 513);
    assert(!b1_boot_lease_take(&id, UINT64_MAX, true, &reserve, &count));
  } else
    abort();
  if (strcmp(mode, "unknown-time") && strcmp(mode, "lease"))
    assert(!q.has_confirmed); /* rejecting restores never mutate output */
  printf("{\"case\":\"%s\",\"status\":\"PASS\"}\n", mode);
}
int main(int argc, char **argv) {
  assert(argc == 2);
  if (!strncmp(argv[1], "continuity-", 11))
    continuity(argv[1] + 11);
  else
    bounds(argv[1]);
  return 0;
}
