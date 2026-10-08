#include "agri_lora.h"
bool al_stream_expire(al_stream_t *s, uint64_t last, uint64_t now, uint32_t idle) {
  if (!s || !s->used || (now >= last && now - last < idle)) return false;
  s->used = 0; s->rejected++; return true;
}
#include <string.h>
static uint16_t u16(const uint8_t *p) {
  return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}
static uint32_t u32(const uint8_t *p) {
  return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 |
         (uint32_t)p[3] << 24;
}
static void w16(uint8_t *p, uint16_t x) {
  p[0] = (uint8_t)x;
  p[1] = (uint8_t)(x >> 8);
}
static void w32(uint8_t *p, uint32_t x) {
  for (unsigned i = 0; i < 4; ++i)
    p[i] = (uint8_t)(x >> (8 * i));
}
uint32_t al_crc32(const uint8_t *p, size_t n) {
  uint32_t c = ~0u;
  for (size_t i = 0; i < n; ++i) {
    c ^= p[i];
    for (unsigned b = 0; b < 8; ++b)
      c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
  }
  return ~c;
}
int al_zone(uint8_t s, uint8_t d, uint8_t t) {
  bool a = s == 1 || s == 2, b = s == 3 || s == 4, c = s == 5 || s == 6;
  bool da = d == 1 || d == 2, db = d == 3 || d == 4, dc = d == 5 || d == 6;
  /* SENSOR_DATA=0,CONTROL_COMMAND=1,CONTROL_RESULT=2,HEARTBEAT=3,ALERT=4,
     SERVER_POLICY=5,NODE_REGISTER=6,NODE_REGISTER_ACK=7,NODE_STATUS=8,ACK=9,PERSISTED_ACK=10.
   */
  bool ok = (b && da && (t == 0 || t == 4 || t == 6 || t == 8)) ||
            (a && db && (t == 10 || t == 9 || t == 7 || t == 8 || t == 5)) ||
            (c && da && (t == 2 || t == 9 || t == 6 || t == 8)) ||
            (a && dc && (t == 1 || t == 7 || t == 8)) ||
            (a && da && s != d && (t == 3 || t == 8));
  if (!ok)
    return -1;
  uint8_t node = (b || c) ? s : (db || dc) ? d : 0;
  return node ? (node == 3 || node == 5 ? 1 : 2) : 0;
}
static bool valid(const al_frame_t *f) {
  if (!f || f->type > 10 || f->source > 6 || f->destination > 6 ||
      al_zone(f->source, f->destination, f->type) != f->zone)
    return false;
  if (!f->total || f->total > AL_MAX_MESSAGE || !f->chunk ||
      f->chunk > AL_MAX_FRAME - AL_HEADER || !f->count ||
      f->count > AL_MAX_FRAGMENTS || f->index >= f->count ||
      f->count != (f->total + f->chunk - 1u) / f->chunk)
    return false;
  size_t remain = f->total - (size_t)f->index * f->chunk;
  return f->payload_length == (remain < f->chunk ? remain : f->chunk) &&
         f->payload;
}
bool al_decode(const uint8_t *p, size_t n, al_frame_t *f) {
  if (!p || !f || n <= AL_HEADER || n > AL_MAX_FRAME || p[0] != 'A' ||
      p[1] != 'L' || p[2] != 1 || p[7])
    return false;
  memset(f, 0, sizeof(*f));
  f->type = p[3];
  f->source = p[4];
  f->destination = p[5];
  f->zone = p[6];
  memcpy(f->session, p + 8, 16);
  memcpy(f->logical, p + 24, 16);
  f->sequence = u32(p + 40);
  f->generation = u32(p + 44);
  f->index = u16(p + 48);
  f->count = u16(p + 50);
  f->total = u16(p + 52);
  f->payload_length = u16(p + 54);
  f->chunk = u16(p + 56);
  f->message_crc = u32(p + 58);
  f->payload = p + AL_HEADER;
  if (!valid(f) || n != AL_HEADER + f->payload_length ||
      al_crc32(f->payload, f->payload_length) != u32(p + 62))
    return false;
  uint8_t copy[AL_MAX_FRAME];
  memcpy(copy, p, n);
  memset(copy + 66, 0, 4);
  return al_crc32(copy, n) == u32(p + 66);
}
bool al_encode(const al_frame_t *f, uint8_t *p, size_t cap, size_t *length) {
  if (!valid(f) || !p || !length || cap < AL_HEADER + f->payload_length)
    return false;
  size_t n = AL_HEADER + f->payload_length;
  memset(p, 0, AL_HEADER);
  p[0] = 'A';
  p[1] = 'L';
  p[2] = 1;
  p[3] = f->type;
  p[4] = f->source;
  p[5] = f->destination;
  p[6] = f->zone;
  memcpy(p + 8, f->session, 16);
  memcpy(p + 24, f->logical, 16);
  w32(p + 40, f->sequence);
  w32(p + 44, f->generation);
  w16(p + 48, f->index);
  w16(p + 50, f->count);
  w16(p + 52, f->total);
  w16(p + 54, f->payload_length);
  w16(p + 56, f->chunk);
  w32(p + 58, f->message_crc);
  memcpy(p + AL_HEADER, f->payload, f->payload_length);
  w32(p + 62, al_crc32(f->payload, f->payload_length));
  w32(p + 66, al_crc32(p, n));
  *length = n;
  return true;
}
bool al_fragment(const uint8_t *raw, size_t n, const al_frame_t *meta,
                 size_t mtu, unsigned idx, uint8_t *out, size_t cap,
                 size_t *len) {
  if (!raw || !meta || !n || n > AL_MAX_MESSAGE || mtu <= AL_HEADER ||
      mtu > AL_MAX_FRAME)
    return false;
  size_t chunk = mtu - AL_HEADER, count = (n + chunk - 1) / chunk;
  if (count > AL_MAX_FRAGMENTS || idx >= count)
    return false;
  al_frame_t f = *meta;
  f.total = (uint16_t)n;
  f.chunk = (uint16_t)chunk;
  f.count = (uint16_t)count;
  f.index = (uint16_t)idx;
  f.message_crc = al_crc32(raw, n);
  f.payload = raw + idx * chunk;
  size_t remain = n - idx * chunk;
  f.payload_length = (uint16_t)(remain < chunk ? remain : chunk);
  return al_encode(&f, out, cap, len);
}
void al_receiver_init(al_receiver_t *r) { memset(r, 0, sizeof(*r)); }
static bool same_key(const al_frame_t *a, const al_frame_t *b) {
  return a->source == b->source && a->destination == b->destination &&
         a->message_crc == b->message_crc &&
         !memcmp(a->session, b->session, 16) &&
         !memcmp(a->logical, b->logical, 16);
}
static bool same_meta(const al_frame_t *a, const al_frame_t *b) {
  return same_key(a, b) && a->type == b->type && a->zone == b->zone &&
         a->sequence == b->sequence && a->generation == b->generation &&
         a->count == b->count && a->total == b->total && a->chunk == b->chunk;
}
int al_receive(al_receiver_t *r, const uint8_t *wire, size_t n, uint64_t now,
               uint8_t *out, size_t cap, size_t *length, al_frame_t *meta) {
  if (!r || !out || !length || !meta)
    return -1;
  if (now < r->now) {
    al_receiver_init(r);
    r->now = now;
    return -1;
  }
  r->now = now;
  for (unsigned i = 0; i < AL_RX_SLOTS; ++i)
    if (r->slots[i].active && now >= r->slots[i].deadline) {
      r->slots[i].active = false;
      r->expired++;
    }
  al_frame_t f;
  if (!al_decode(wire, n, &f)) {
    r->rejected++;
    return -1;
  }
  al_slot_t *slot = NULL, *free_slot = NULL;
  for (unsigned i = 0; i < AL_RX_SLOTS; ++i) {
    al_slot_t *s = &r->slots[i];
    if (s->active && same_key(&s->meta, &f))
      slot = s;
    else if (!s->active && !free_slot)
      free_slot = s;
  }
  if (!slot) {
    if (!free_slot || UINT64_MAX - now < AL_TIMEOUT_MS) {
      r->rejected++;
      return -1;
    }
    slot = free_slot;
    memset(slot, 0, sizeof(*slot));
    slot->active = true;
    slot->meta = f;
    slot->meta.payload = NULL;
    slot->deadline = now + AL_TIMEOUT_MS;
  }
  if (slot->quarantined || !same_meta(&slot->meta, &f)) {
    slot->quarantined = true;
    r->rejected++;
    return -1;
  }
  size_t offset = (size_t)f.index * f.chunk;
  uint64_t bit = UINT64_C(1) << f.index;
  if (slot->seen & bit) {
    if (memcmp(slot->data + offset, f.payload, f.payload_length)) {
      slot->quarantined = true;
      r->rejected++;
      return -1;
    }
    r->duplicates++;
  } else {
    memcpy(slot->data + offset, f.payload, f.payload_length);
    slot->seen |= bit;
  }
  uint64_t all = f.count == 64 ? UINT64_MAX : (UINT64_C(1) << f.count) - 1;
  if (slot->seen != all)
    return 0;
  if (cap < f.total || al_crc32(slot->data, f.total) != f.message_crc) {
    slot->active = false;
    r->rejected++;
    return -1;
  }
  memcpy(out, slot->data, f.total);
  *length = f.total;
  *meta = f;
  meta->payload = NULL;
  slot->active = false;
  return 1;
}
int al_stream_byte(al_stream_t *s, uint8_t byte, uint8_t *out, size_t cap,
                   size_t *length) {
  if (!s || !out || !length)
    return -1;
  if (s->used == AL_MAX_FRAME) {
    memmove(s->data, s->data + 1, --s->used);
    s->rejected++;
  }
  s->data[s->used++] = byte;
  while (s->used >= 2) {
    if (s->data[0] != 'A' || s->data[1] != 'L') {
      memmove(s->data, s->data + 1, --s->used);
      continue;
    }
    if (s->used < AL_HEADER)
      return 0;
    size_t n = AL_HEADER + u16(s->data + 54);
    if (n <= AL_HEADER || n > AL_MAX_FRAME) {
      memmove(s->data, s->data + 1, --s->used);
      s->rejected++;
      continue;
    }
    if (s->used < n)
      return 0;
    al_frame_t f;
    if (!al_decode(s->data, n, &f)) {
      memmove(s->data, s->data + 1, --s->used);
      s->rejected++;
      continue;
    }
    if (cap < n)
      return -1;
    memcpy(out, s->data, n);
    memmove(s->data, s->data + n, s->used - n);
    s->used -= n;
    *length = n;
    return 1;
  }
  return 0;
}
