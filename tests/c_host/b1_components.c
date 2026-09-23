#include <assert.h>
#include "sensor_trust.h"
#include "change_detector.h"
#include "adaptive_scheduler.h"

int main(void)
{
    sensor_trust_config_t cfg = {-40, 85, 0.01f, 20, 3, 24, 0.01f, 3};
    sensor_trust_t temperature;
    assert(sensor_trust_init(&temperature, &cfg));
    sensor_sample_t normal = {27.0f, true, 1000};
    assert(sensor_trust_update(&temperature, &normal).state == SENSOR_STATE_HEALTHY);
    sensor_sample_t injected = {150.0f, true, 2000};
    sensor_health_result_t fault = sensor_trust_update(&temperature, &injected);
    assert(fault.state == SENSOR_STATE_FAULT && (fault.fault_flags & FAULT_RANGE));

    cd_config_t cd_cfg = {0};
    cd_cfg.channels[CD_CH_TEMPERATURE] = (cd_channel_cfg_t){true, 0.15f};
    cd_cfg.variety_window_s = 15;
    cd_cfg.roc_window_s = 6;
    cd_cfg.baseline_tau_s = 20;
    cd_cfg.min_interval_s = 1;
    cd_cfg.event_threshold = 8;
    cd_cfg.event_min_duration_s = 4;
    cd_t detector;
    cd_init(&detector, &cd_cfg);
    const float values[CD_NUM_CHANNELS] = {27.0f, 0, 0, 0};
    const bool valid[CD_NUM_CHANNELS] = {true, false, false, false};
    bool event;
    assert(cd_update(&detector, 1.0, values, valid, &event) == 0.0f);

    const float stable[] = {2, 4, 5};
    const float active[] = {2, 1};
    const float alert[] = {1};
    as_config_t as_cfg = {0};
    as_cfg.min_interval = 1;
    as_cfg.default_interval = 2;
    as_cfg.max_interval = 5;
    as_cfg.stable_threshold = 3;
    as_cfg.active_threshold = 8;
    as_cfg.hysteresis_fraction = 0.5f;
    as_cfg.ladders[AS_STABLE] = stable;
    as_cfg.ladder_len[AS_STABLE] = 3;
    as_cfg.ladder_confirm[AS_STABLE] = 2;
    as_cfg.ladders[AS_ACTIVE] = active;
    as_cfg.ladder_len[AS_ACTIVE] = 2;
    as_cfg.ladder_confirm[AS_ACTIVE] = 1;
    as_cfg.ladders[AS_ALERT] = alert;
    as_cfg.ladder_len[AS_ALERT] = 1;
    as_cfg.ladder_confirm[AS_ALERT] = 1;
    as_t scheduler;
    as_init(&scheduler, &as_cfg);
    as_decision_t decision;
    as_update(&scheduler, 1, values, valid, 0, false, &decision);
    assert(decision.state == AS_STABLE && decision.interval_s == 2);
    as_update(&scheduler, 3, values, valid, 0, false, &decision);
    as_update(&scheduler, 5, values, valid, 0, false, &decision);
    assert(decision.state == AS_STABLE && decision.interval_s > 2);
    as_update(&scheduler, 9, values, valid, 20, false, &decision);
    assert(decision.state == AS_ALERT && decision.interval_s == 1);
    return 0;
}
