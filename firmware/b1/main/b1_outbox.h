#pragma once
/* Portable bounded delivery state machine. Persisted records contain no pointers.
 * v1 blobs are same-firmware checkpoints, not a cross-ABI interchange format. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define B1_OUTBOX_CAPACITY 16
#define B1_OUTBOX_NORMAL_LIMIT 12
#define B1_BOOT_ID_SIZE 80
#define B1_SAMPLE_ID_SIZE 100
#define B1_WIRE_SIZE 4096
#define B1_MAX_ATTEMPTS 5
#define B1_ACK_TIMEOUT_MS 3000

typedef struct {
    uint32_t version;
    uint32_t crc;
    uint64_t order;
    uint64_t acquired_ms;
    uint32_t sequence;
    uint8_t high, has_alert;
    char boot_id[B1_BOOT_ID_SIZE];
    char sample_id[B1_SAMPLE_ID_SIZE];
    char wire[B1_WIRE_SIZE]; /* immutable SENSOR_DATA newline + optional ALERT newline */
} b1_record_t;

typedef enum { B1_PENDING, B1_IN_FLIGHT, B1_RETRY_PENDING, B1_FAILED } b1_delivery_state_t;
typedef struct {
    b1_record_t record;
    bool active, quarantined;
    uint8_t attempts, ack_mask;
    bool probing;
    uint32_t probe_delay_ms;
    uint64_t total_attempts;
    b1_delivery_state_t state;
    uint64_t due_ms;
} b1_entry_t;
typedef bool (*b1_store_fn)(void *ctx, unsigned slot, const b1_record_t *record);
typedef struct {
    b1_entry_t entries[B1_OUTBOX_CAPACITY];
    b1_store_fn store;
    void *store_context;
    uint64_t next_order;
    uint64_t now_ms, window_end_ms, pause_until_ms, boot_attempts;
    unsigned window_attempts;
    bool window_open;
    uint32_t rejected, storage_failures, acknowledged, retries, exhausted, probes;
} b1_outbox_t;

void b1_outbox_init(b1_outbox_t *q, b1_store_fn store, void *ctx);
bool b1_outbox_admit(b1_outbox_t *q, const b1_record_t *record);
bool b1_outbox_restore(b1_outbox_t *q, unsigned slot, const b1_record_t *record);
/* Five rapid attempts per record, then one recovery probe per capped backoff.
 * Nonempty communication windows last <=30 s / <=80 issued attempts, separated
 * by >=60 s. Boot/lifetime are not total attempt caps: rate and retention are
 * bounded, eventual delivery under arbitrary outages is not guaranteed. */
void b1_outbox_tick(b1_outbox_t *q, uint64_t now_ms);
int b1_outbox_next(b1_outbox_t *q, uint64_t now_ms);
bool b1_outbox_ack(b1_outbox_t *q, const char *message_id);
void b1_record_seal(b1_record_t *record);
bool b1_record_valid(const b1_record_t *record);
unsigned b1_outbox_count(const b1_outbox_t *q);
