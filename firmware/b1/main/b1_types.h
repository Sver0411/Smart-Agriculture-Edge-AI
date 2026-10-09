#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "b1_outbox.h"
#include "sensor_trust.h"
#include "adaptive_scheduler.h"

typedef struct {
    uint32_t seq;
    uint64_t monotonic_ms;
    float temperature;
    float humidity;
    bool valid;
    bool injected;
    sensor_health_result_t temp_health;
    sensor_health_result_t hum_health;
    bool usable;
    bool upload_requested;
    bool control_relevant_change;
    uint32_t upload_reasons;
    bool detected_event;
    bool alert_requested;
    bool recovered;
    sensor_health_state_t health_state;
    float score;
    const char *mode;
    const char *reason;
    uint32_t next_interval_ms;
} b1_sample_t;


typedef struct {
    uint32_t wifi_connects, gateway_connects, registration_attempts;
    uint32_t registration_success, sensor_samples, sensor_messages, alerts;
    uint32_t local_queue_drops, gateway_failovers;
} b1_stats_t;

extern b1_stats_t b1_stats;
extern char b1_boot_id[B1_BOOT_ID_SIZE];
