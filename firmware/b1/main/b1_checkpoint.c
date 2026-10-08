#include "b1_checkpoint.h"
#include <string.h>
static void put(unsigned char *p, uint64_t v, unsigned n) {
  for (unsigned i = 0; i < n; i++)
    p[i] = (unsigned char)(v >> (8 * i));
}
static uint64_t get(const unsigned char *p, unsigned n) {
  uint64_t v = 0;
  for (unsigned i = 0; i < n; i++)
    v |= (uint64_t)p[i] << (8 * i);
  return v;
}
static uint32_t crc(const unsigned char *p, size_t n) {
  uint32_t c = 0xffffffff;
  for (size_t i = 0; i < n; i++) {
    c ^= (i >= 12 && i < 16) ? 0 : p[i];
    for (unsigned b = 0; b < 8; b++)
      c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
  }
  return ~c;
}
size_t b1_checkpoint_encode(const b1_record_t *r, unsigned char *p,
                            size_t cap) {
  if (!b1_record_valid(r) || !r->high)
    return 0;
  size_t b = strlen(r->boot_id), s = strlen(r->sample_id), w = strlen(r->wire),
         n = 44 + b + s + w;
  if (cap < n)
    return 0;
  memset(p, 0, 44);
  memcpy(p, "B1Q2", 4);
  put(p + 4, 2, 2);
  put(p + 6, 44, 2);
  put(p + 8, n, 4);
  put(p + 16, r->order, 8);
  put(p + 24, r->acquired_ms, 8);
  put(p + 32, r->sequence, 4);
  p[36] = (unsigned char)(r->high | (r->has_alert << 1));
  p[37] = (unsigned char)b;
  p[38] = (unsigned char)s;
  put(p + 40, w, 2);
  memcpy(p + 44, r->boot_id, b);
  memcpy(p + 44 + b, r->sample_id, s);
  memcpy(p + 44 + b + s, r->wire, w);
  put(p + 12, crc(p, n), 4);
  return n;
}
bool b1_checkpoint_decode(const unsigned char *p, size_t n, b1_record_t *r) {
  if (!p || !r || n > B1_CHECKPOINT_MAX)
    return false;
  memset(r, 0, sizeof(*r));
  if (n >= 44 && memcmp(p, "B1Q2", 4) == 0) {
    size_t b = p[37], s = p[38], w = (size_t)get(p + 40, 2);
    if (get(p + 4, 2) != 2 || get(p + 6, 2) != 44 || get(p + 8, 4) != n ||
        get(p + 12, 4) != crc(p, n) || p[36] > 3 || !(p[36] & 1) || p[39] ||
        get(p + 42, 2) || !b || b >= B1_BOOT_ID_SIZE || !s ||
        s >= B1_SAMPLE_ID_SIZE || !w || w >= B1_WIRE_SIZE ||
        n != 44 + b + s + w)
      return false;
    /* Embedded NULs must not disguise trailing payload bytes. */
    if (memchr(p + 44, 0, b + s + w))
      return false;
    r->order = get(p + 16, 8);
    r->acquired_ms = get(p + 24, 8);
    r->sequence = (uint32_t)get(p + 32, 4);
    r->high = p[36] & 1;
    r->has_alert = (p[36] >> 1) & 1;
    memcpy(r->boot_id, p + 44, b);
    memcpy(r->sample_id, p + 44 + b, s);
    memcpy(r->wire, p + 44 + b + s, w);
    b1_record_seal(r);
  } else {
    /* Legacy native format cannot be migrated across a different ABI safely. */
    if (n <= offsetof(b1_record_t, wire) || n > sizeof(*r))
      return false;
    memcpy(r, p, n);
    if (!b1_record_valid(r) ||
        n != offsetof(b1_record_t, wire) + strlen(r->wire) + 1)
      return false;
  }
  return b1_record_valid(r) && r->high;
}
