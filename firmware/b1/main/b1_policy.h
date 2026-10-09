#pragma once
#include "b1_types.h"
#include "change_detector.h"
#include "adaptive_scheduler.h"

typedef struct {
    sensor_trust_t temperature, humidity;
    cd_t detector;
    as_t scheduler;
    cd_config_t cd_config;
    as_config_t as_config;
    float fault_interval_s, degraded_interval_s, fault_reminder_s;
    bool untrusted, has_health, last_valid;
    sensor_health_state_t last_health;
    uint32_t last_temp_flags, last_hum_flags;
    double last_notification_t;
    float temperature_threshold, temperature_margin, reported_temperature;
    bool has_reported_temperature;
    bool has_confirmed;
    uint32_t confirmed_seq;
    uint64_t confirmed_ms;
} b1_policy_t;
bool b1_policy_init(b1_policy_t *p);
void b1_policy_update(b1_policy_t *p, b1_sample_t *sample);
void b1_policy_mark_reported(b1_policy_t *p, const b1_sample_t *sample);
bool b1_policy_set_temperature_threshold(b1_policy_t *p, float threshold);
