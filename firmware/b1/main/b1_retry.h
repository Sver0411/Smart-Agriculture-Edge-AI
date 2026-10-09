#pragma once
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>

#define B1_PROBE_MIN_MS 60000u
#define B1_PROBE_MAX_MS 900000u
#define B1_COMM_WINDOW_MS 30000u
#define B1_COMM_MAX_ATTEMPTS (B1_OUTBOX_CAPACITY * B1_MAX_ATTEMPTS)

static inline uint64_t b1_deadline(uint64_t now, uint64_t delay) {
  return now > UINT64_MAX - delay ? UINT64_MAX : now + delay;
}
static inline uint32_t b1_probe_delay(uint32_t previous) {
  return previous >= B1_PROBE_MAX_MS / 2 ? B1_PROBE_MAX_MS : previous * 2;
}
/* Shared by real network adapter and host tests. Only confirmed durable ACK
 * resets link failure history; registration alone cannot bypass the budget. */
typedef struct {
  uint32_t failures;
  uint64_t due_ms;
} b1_link_retry_t;
static inline bool b1_link_ready(const b1_link_retry_t *r, uint64_t now) {
  return now != UINT64_MAX && now >= r->due_ms;
}
static inline void b1_link_failed(b1_link_retry_t *r, uint64_t now) {
  if (r->failures < UINT32_MAX)
    r->failures++;
  uint32_t delay;
  if (r->failures <= 5)
    delay = 1000u << (r->failures - 1);
  else {
    delay = B1_PROBE_MIN_MS;
    for (uint32_t n = 6; n < r->failures && delay < B1_PROBE_MAX_MS; n++)
      delay = b1_probe_delay(delay);
  }
  r->due_ms = b1_deadline(now, delay);
}
static inline void b1_link_confirmed(b1_link_retry_t *r) {
  r->failures = 0;
  r->due_ms = 0;
}
