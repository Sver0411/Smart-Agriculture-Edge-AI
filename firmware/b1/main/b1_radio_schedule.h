#pragma once
#include <stdbool.h>
#include <stdint.h>
/* Portable deadline gate. Notifications wake the sole UART task; they never
 * bypass its deadline or its unavailable-gateway backoff. */
typedef struct {
    uint64_t now_ms, due_ms;
    uint32_t backoff_ms;
} b1_radio_schedule_t;
void b1_radio_schedule_init(b1_radio_schedule_t *s);
bool b1_radio_schedule_due(b1_radio_schedule_t *s, uint64_t now, bool pending);
void b1_radio_schedule_finish(b1_radio_schedule_t *s, uint64_t now, bool pending, bool progress);
uint32_t b1_radio_schedule_wait(b1_radio_schedule_t *s, uint64_t now, bool pending);
