#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define AL_HEADER 70u
#define AL_MAX_FRAME 256u
#define AL_MAX_MESSAGE 4096u
#define AL_MAX_FRAGMENTS 64u
#define AL_RX_SLOTS 4u
#define AL_TIMEOUT_MS 3000u
#define AL_FLAG_AUTH 1u
#define AL_MAX_KEY 64u
typedef struct {
  uint8_t type, source, destination, zone, flags, session[16], logical[16];
  uint32_t sequence, generation, message_crc;
  uint16_t index, count, total, chunk, payload_length;
  const uint8_t *payload;
} al_frame_t;
typedef struct {
  bool active, quarantined;
  al_frame_t meta;
  uint64_t deadline, seen;
  uint8_t data[AL_MAX_MESSAGE];
} al_slot_t;
typedef struct {
  al_slot_t slots[AL_RX_SLOTS];
  uint64_t now;
  uint32_t expired, rejected, duplicates;
  uint8_t key[AL_MAX_KEY];
  size_t key_len;
  uint32_t last_gen[7], last_seq[7];
  uint8_t last_session[7][16];
  bool seq_seen[7];
} al_receiver_t;
typedef struct {
  uint8_t data[AL_MAX_FRAME];
  size_t used;
  uint32_t rejected;
} al_stream_t;
uint32_t al_crc32(const uint8_t *, size_t);
uint32_t al_mac32(const uint8_t *key, size_t key_len, const uint8_t *data, size_t n);
/* IDs: SERVER=0,A1=1,A2=2,B1=3,B2=4,C1=5,C2=6. Types follow MESSAGE_TYPES. */
int al_zone(uint8_t, uint8_t, uint8_t);
bool al_decode(const uint8_t *, size_t, al_frame_t *);
bool al_decode_auth(const uint8_t *, size_t, const uint8_t *key, size_t key_len, al_frame_t *);
bool al_encode(const al_frame_t *, uint8_t *, size_t, size_t *);
bool al_encode_auth(const al_frame_t *, const uint8_t *key, size_t key_len, uint8_t *, size_t, size_t *);
bool al_fragment(const uint8_t *, size_t, const al_frame_t *, size_t, unsigned,
                 uint8_t *, size_t, size_t *);
bool al_fragment_auth(const uint8_t *, size_t, const al_frame_t *, size_t, unsigned,
                      const uint8_t *key, size_t key_len, uint8_t *, size_t, size_t *);
void al_receiver_init(al_receiver_t *);
bool al_receiver_set_key(al_receiver_t *, const uint8_t *key, size_t key_len);
int al_receive(al_receiver_t *, const uint8_t *, size_t, uint64_t, uint8_t *,
               size_t, size_t *, al_frame_t *);
int al_stream_byte(al_stream_t *, uint8_t, uint8_t *, size_t, size_t *);
bool al_stream_expire(al_stream_t *, uint64_t last_byte_ms, uint64_t now_ms, uint32_t idle_ms);
