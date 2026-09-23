#pragma once
#include "b1.h"
#include "change_detector.h"
#include "adaptive_scheduler.h"

typedef struct {
    sensor_trust_t temperature, humidity;
    cd_t detector;
    as_t scheduler;
    cd_config_t cd_config;
    as_config_t as_config;
} b1_policy_t;
bool b1_policy_init(b1_policy_t *p);
void b1_policy_update(b1_policy_t *p, b1_sample_t *sample);
