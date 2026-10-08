/* File callbacks model an NVS commit; actual v2 checkpoint/outbox/policy used.
 */
#include "b1.h"
#include "b1_checkpoint.h"
#include "b1_policy.h"
#include "b1_snapshot.h"
#include "b1_storage.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
b1_stats_t b1_stats;
char b1_boot_id[B1_BOOT_ID_SIZE] = "host-old";
static const char *directory;
static void path(char *out, size_t n, const char *name) {
  int k = snprintf(out, n, "%s/%s", directory, name);
  assert(k > 0 && (size_t)k < n);
}
bool b1_storage_save(void *ctx, unsigned slot, const b1_record_t *r) {
  (void)ctx;
  char name[30], file[1024];
  snprintf(name, sizeof(name), "q%02u.bin", slot);
  path(file, sizeof(file), name);
  if (!r) {
    return unlink(file) == 0;
  }
  unsigned char buf[B1_CHECKPOINT_MAX];
  size_t n = b1_checkpoint_encode(r, buf, sizeof(buf));
  if (!n)
    return false;
  FILE *f = fopen(file, "wb");
  if (!f)
    return false;
  bool ok =
      fwrite(buf, 1, n, f) == n && fflush(f) == 0 && fsync(fileno(f)) == 0;
  return fclose(f) == 0 && ok;
}
bool b1_storage_init(b1_outbox_t *q) {
  b1_outbox_init(q, b1_storage_save, NULL);
  for (unsigned slot = 0; slot < 16; slot++) {
    char name[30], file[1024];
    snprintf(name, sizeof(name), "q%02u.bin", slot);
    path(file, sizeof(file), name);
    FILE *f = fopen(file, "rb");
    if (!f)
      continue;
    unsigned char buf[B1_CHECKPOINT_MAX];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    b1_record_t r;
    if (!b1_checkpoint_decode(buf, n, &r) || !b1_outbox_restore(q, slot, &r))
      return false;
  }
  return true;
}
void b1_storage_lock(void) {}
void b1_storage_unlock(void) {}
int main(int argc, char **argv) {
  assert(argc >= 3);
  directory = argv[2];
  static b1_policy_t p;
  assert(b1_policy_init(&p));
  assert(b1_queue_init());
  b1_sleep_identity_t id = {.generation = 1,
                            .sequence = 2,
                            .saved_ms = 2000,
                            .planned_sleep_ms = 1000,
                            .owner = "A1",
                            .previous_boot = "host-old"};
  uint8_t raw[B1_SNAPSHOT_MAX];
  size_t n;
  char file[1024];
  path(file, sizeof(file), "snapshot.bin");
  if (!strcmp(argv[1], "stable")) {
    for (unsigned seq = 1; seq <= 12; seq++) {
      b1_sample_t s = {.seq = seq,
                       .monotonic_ms = seq * 1000,
                       .temperature = 25,
                       .humidity = 60,
                       .valid = true};
      b1_policy_update(&p, &s);
      if (s.upload_requested)
        b1_policy_mark_reported(&p, &s);
    }
    id.sequence = 12;
    id.saved_ms = 12000;
    assert(b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
    uint64_t now;
    assert(b1_snapshot_restore(&p, &id, raw, n, 1, true, 1000, &now) ==
           B1_RESTORE_CONTINUOUS);
    b1_sample_t s = {.seq = 13,
                     .monotonic_ms = now,
                     .temperature = 25,
                     .humidity = 60,
                     .valid = true};
    b1_policy_update(&p, &s);
    assert(!s.upload_requested && !s.detected_event);
    fprintf(stderr, "{\"event\":\"STABLE_RESTORE\",\"upload_requested\":false,"
                    "\"synthetic_event\":false}\n");
    return 0;
  }
  if (!strcmp(argv[1], "prepare")) {
    b1_sample_t s = {.seq = 1,
                     .monotonic_ms = 1000,
                     .temperature = 31.5,
                     .humidity = 60,
                     .valid = true};
    b1_policy_update(&p, &s);
    assert(b1_queue_sample(&s));
    b1_record_t r;
    assert(b1_queue_next(&r, 1000));
    char ack[110];
    snprintf(ack, sizeof(ack), "%s-S", r.sample_id);
    assert(b1_queue_ack(ack));
    assert(b1_queue_take_confirmed(&s));
    b1_policy_mark_reported(&p, &s);
    s = (b1_sample_t){.seq = 2,
                      .monotonic_ms = 2000,
                      .temperature = 32.5,
                      .humidity = 60,
                      .valid = true};
    b1_policy_update(&p, &s);
    assert(s.control_relevant_change && b1_queue_sample(&s));
    assert(b1_snapshot_encode(&p, &id, raw, sizeof(raw), &n));
    FILE *f = fopen(file, "wb");
    assert(f && fwrite(raw, 1, n, f) == n);
    fclose(f);
  } else {
    FILE *f = fopen(file, "rb");
    assert(f);
    n = fread(raw, 1, sizeof(raw), f);
    fclose(f);
    uint64_t now;
    if (!strcmp(argv[1], "corrupt"))
      raw[12] ^= 1;
    bool trusted = !strcmp(argv[1], "ack") || !strcmp(argv[1], "stable");
    b1_restore_result_t result =
        b1_snapshot_restore(&p, &id, raw, n, 1, trusted, 1000, &now);
    if (!strcmp(argv[1], "corrupt"))
      assert(result == B1_RESTORE_REJECTED);
    else
      assert(result ==
             (trusted ? B1_RESTORE_CONTINUOUS : B1_RESTORE_TIME_UNKNOWN));
    if (!strcmp(argv[1], "restore") || !strcmp(argv[1], "corrupt") ||
        !strcmp(argv[1], "old-ack"))
      strcpy(b1_boot_id, "host-new");
    if (!strcmp(argv[1], "old-ack") || !strcmp(argv[1], "ack")) {
      b1_record_t attempted;assert(b1_queue_next(&attempted,2000));
    }
    if (!strcmp(argv[1], "old-ack")) {
      for (int i = 3; i < argc; i++)
        assert(b1_queue_ack(argv[i]));
      b1_sample_t confirmed;
      assert(!b1_queue_take_confirmed(&confirmed) && !b1_queue_pending_count());
      fprintf(stderr,
              "{\"event\":\"OLD_ACK_RETIRED\",\"baseline_advanced\":false}\n");
      return 0;
    }
    if (!strcmp(argv[1], "ack")) {
      for (int i = 3; i < argc; i++)
        assert(b1_queue_ack(argv[i]));
      b1_sample_t confirmed;
      assert(b1_queue_take_confirmed(&confirmed));
      b1_policy_mark_reported(&p, &confirmed);
      assert(p.confirmed_seq == 2 && !b1_queue_pending_count());
      fprintf(stderr, "{\"event\":\"ACK_CONFIRMED\",\"confirmed_seq\":%u}\n",
              (unsigned)p.confirmed_seq);
      return 0;
    }
    fprintf(stderr,
            "{\"event\":\"RESTORE\",\"result\":%d,\"pending\":%u,"
            "\"generation\":%u}\n",
            result, b1_queue_pending_count(), (unsigned)id.generation);
  }
  b1_record_t r;
  assert(b1_queue_next(&r, 2000));
  assert(r.high);
  fputs(r.wire, stdout);
  return 0;
}
