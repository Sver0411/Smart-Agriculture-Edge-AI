#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "b1_outbox.h"
#include "freertos/FreeRTOS.h"

#include "sensor_trust.h"

#include "b1_types.h"


extern b1_stats_t b1_stats;
extern char b1_boot_id[B1_BOOT_ID_SIZE];
void b1_sensor_task(void *arg);
void b1_network_task(void *arg);
bool b1_queue_sample(const b1_sample_t *sample);
void b1_runtime_init(void);

bool b1_queue_init(void);
bool b1_queue_next(b1_record_t *record, uint64_t now_ms);
bool b1_queue_ack(const char *message_id);
void b1_queue_stats(void);
bool b1_queue_take_confirmed(b1_sample_t *sample);
const char *b1_policy_version(void);
