#include "b1_policy.h"
#include "sdkconfig.h"
#include <string.h>

#if CONFIG_B1_LAB_MODE
static const float stable[] = {2, 4, 5};
static const float active[] = {2, 1};
static const float alert[] = {1};
#else
static const float stable[] = {20, 40, 60};
static const float active[] = {15, 10, 5};
static const float alert[] = {5};
#endif

bool b1_policy_init(b1_policy_t *p)
{
    memset(p, 0, sizeof(*p));
    // Temperature is the frozen SensorTrust hardware-study configuration.
    sensor_trust_config_t temp = {-40, 85, 0.01f, 20, 3, 24, 0.01f, 3};
    // Humidity is an integration configuration, not independently validated.
    sensor_trust_config_t hum = {0, 100, 0.1f, 20, 10, 24, 0.1f, 3};
    if (!sensor_trust_init(&p->temperature, &temp) ||
        !sensor_trust_init(&p->humidity, &hum)) return false;
    p->cd_config.channels[CD_CH_TEMPERATURE] = (cd_channel_cfg_t){true, 0.15f};
    p->cd_config.channels[CD_CH_HUMIDITY] = (cd_channel_cfg_t){true, 0.80f};
#if CONFIG_B1_LAB_MODE
    p->cd_config.variety_window_s = 15;
    p->cd_config.roc_window_s = 6;
    p->cd_config.baseline_tau_s = 20;
    p->cd_config.min_interval_s = 1;
    p->cd_config.event_min_duration_s = 4;
#else
    p->cd_config.variety_window_s = 30;
    p->cd_config.roc_window_s = 10;
    p->cd_config.baseline_tau_s = 60;
    p->cd_config.min_interval_s = 5;
    p->cd_config.event_min_duration_s = 10;
#endif
    p->cd_config.event_threshold = 8;
    cd_init(&p->detector, &p->cd_config);
    as_config_t *cfg = &p->as_config;
    cfg->min_interval = p->cd_config.min_interval_s;
    cfg->default_interval = stable[0];
    cfg->max_interval = stable[2];
    cfg->stable_threshold = 3;
    cfg->active_threshold = 8;
    cfg->hysteresis_fraction = 0.5f;
    cfg->ladders[AS_STABLE] = stable;
    cfg->ladder_len[AS_STABLE] = 3;
    cfg->ladder_confirm[AS_STABLE] = 2;
    cfg->ladders[AS_ACTIVE] = active;
    cfg->ladder_len[AS_ACTIVE] = sizeof(active)/sizeof(active[0]);
    cfg->ladder_confirm[AS_ACTIVE] = 1;
    cfg->ladders[AS_ALERT] = alert;
    cfg->ladder_len[AS_ALERT] = 1;
    cfg->ladder_confirm[AS_ALERT] = 1;
    cfg->up_first_sample = true;
    cfg->up_on_event = true;
    cfg->up_on_state_change = true;
    cfg->up_on_interval_change = true;
    cfg->heartbeat_s = stable[2];
    cfg->delta_threshold = 2;
    cfg->delta_channel_use[0] = cfg->delta_channel_use[1] = true;
    cfg->delta_noise_floor[0] = 0.15f;
    cfg->delta_noise_floor[1] = 0.80f;
    as_init(&p->scheduler, cfg);
    return true;
}

void b1_policy_update(b1_policy_t *p, b1_sample_t *s)
{
    sensor_sample_t temp = {s->temperature, s->valid, s->monotonic_ms};
    sensor_sample_t hum = {s->humidity, s->valid, s->monotonic_ms};
    s->temp_health = sensor_trust_update(&p->temperature, &temp);
    s->hum_health = sensor_trust_update(&p->humidity, &hum);
    s->usable = s->valid && s->temp_health.state != SENSOR_STATE_FAULT &&
                s->hum_health.state != SENSOR_STATE_FAULT;
    const float values[CD_NUM_CHANNELS] = {s->temperature, s->humidity, 0, 0};
    const bool valid[CD_NUM_CHANNELS] = {s->valid && s->temp_health.state != SENSOR_STATE_FAULT,
        s->valid && s->hum_health.state != SENSOR_STATE_FAULT, false, false};
    bool event = false;
    double t = s->monotonic_ms / 1000.0;
    s->score = cd_update(&p->detector, t, values, valid, &event);
    as_decision_t decision;
    as_update(&p->scheduler, t, values, valid, s->score, event, &decision);
    s->mode = decision.state == AS_ALERT ? "ALERT" : decision.state == AS_ACTIVE ? "ACTIVE" : "STABLE";
    s->reason = !s->valid ? "read_failure" : !s->usable ? "trust_fault" : s->mode;
    s->next_interval_ms = (uint32_t)(decision.interval_s * 1000);
}
