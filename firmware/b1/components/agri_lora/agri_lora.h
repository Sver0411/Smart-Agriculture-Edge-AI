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
typedef struct {
  uint8_t type, source, destination, zone, session[16], logical[16];
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
} al_receiver_t;
typedef struct {
  uint8_t data[AL_MAX_FRAME];
  size_t used;
  uint32_t rejected;
} al_stream_t;
uint32_t al_crc32(const uint8_t *, size_t);
/* IDs: SERVER=0,A1=1,A2=2,B1=3,B2=4,C1=5,C2=6. Types follow MESSAGE_TYPES. */
int al_zone(uint8_t, uint8_t, uint8_t);
bool al_decode(const uint8_t *, size_t, al_frame_t *);
bool al_encode(const al_frame_t *, uint8_t *, size_t, size_t *);
bool al_fragment(const uint8_t *, size_t, const al_frame_t *, size_t, unsigned,
                 uint8_t *, size_t, size_t *);
void al_receiver_init(al_receiver_t *);
/* -1 rejected; 0 accepted incomplete/duplicate; 1 complete CRC-valid bytes.
 * Application must still validate full identity, session, source/epoch and ACK
 * scope. */
int al_receive(al_receiver_t *, const uint8_t *, size_t, uint64_t, uint8_t *,
               size_t, size_t *, al_frame_t *);
/* Bounded UART stream parser, one byte per call. Caller resets on partial
 * timeout. */
int al_stream_byte(al_stream_t *, uint8_t, uint8_t *, size_t, size_t *);
/* Poll timeout is not a frame timeout. Keep partial bytes until idle expiry. */
bool al_stream_expire(al_stream_t *, uint64_t last_byte_ms, uint64_t now_ms, uint32_t idle_ms);
