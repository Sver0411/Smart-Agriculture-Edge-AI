#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "sensor_trust.h"

#include "b1_types.h"

extern QueueHandle_t b1_queue;
extern b1_stats_t b1_stats;
extern char b1_boot_id[16];
void b1_sensor_task(void *arg);
void b1_network_task(void *arg);
bool b1_queue_sample(const b1_sample_t *sample);
void b1_runtime_init(void);
