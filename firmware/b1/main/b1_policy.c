#include "b1_policy.h"
#ifndef B1_HOST_TEST
#include "sdkconfig.h"
#endif
#include <math.h>
#include <string.h>
#include "b1_profiles.h"
#include "b1_control_relevance.h"

const char *b1_policy_version(void) { return B1_POLICY_VERSION; }

bool b1_policy_set_temperature_threshold(b1_policy_t *p, float threshold)
{
    if (!isfinite(threshold)) return false;
    p->temperature_threshold = threshold;
    return true;
}

void b1_policy_mark_reported(b1_policy_t *p, const b1_sample_t *s)
{
    p->has_reported_temperature = s->valid && isfinite(s->temperature) && s->temp_health.state == SENSOR_STATE_HEALTHY;
    if (p->has_reported_temperature) p->reported_temperature = s->temperature;
    if (s->usable) {
        p->scheduler.last_upload_values[0] = s->temperature;
        p->scheduler.last_upload_values[1] = s->humidity;
        p->scheduler.last_upload_valid[0] = p->scheduler.last_upload_valid[1] = true;
        p->scheduler.last_upload_t = s->monotonic_ms / 1000.0;
        p->scheduler.has_uploaded = true;
    }
}

bool b1_policy_init(b1_policy_t *p)
{
    memset(p, 0, sizeof(*p));
    configure_profile(p);
    if (!p->temperature.initialised || !p->humidity.initialised) return false;
    cd_init(&p->detector, &p->cd_config);
    as_init(&p->scheduler, &p->as_config);
    return true;
}

void b1_policy_update(b1_policy_t *p, b1_sample_t *s)
{
    s->upload_reasons = 0;
    s->control_relevant_change = false;
    sensor_sample_t temp = {s->temperature, s->valid, s->monotonic_ms};
    sensor_sample_t hum = {s->humidity, s->valid, s->monotonic_ms};
    s->temp_health = sensor_trust_update(&p->temperature, &temp);
    s->hum_health = sensor_trust_update(&p->humidity, &hum);
    s->health_state = s->temp_health.state > s->hum_health.state ? s->temp_health.state : s->hum_health.state;
    bool valid_read = s->valid && isfinite(s->temperature) && isfinite(s->humidity);
    s->usable = valid_read && s->health_state == SENSOR_STATE_HEALTHY;
    bool changed = !p->has_health || valid_read != p->last_valid ||
        s->health_state != p->last_health || s->temp_health.fault_flags != p->last_temp_flags ||
        s->hum_health.fault_flags != p->last_hum_flags;
    s->recovered = p->has_health && (!p->last_valid || p->last_health != SENSOR_STATE_HEALTHY) && s->usable;
    double t = s->monotonic_ms / 1000.0;
    s->alert_requested = (!s->usable && (changed || t - p->last_notification_t >= p->fault_reminder_s)) || s->recovered;
    if (s->alert_requested) p->last_notification_t = t;
    bool health_changed = !p->has_health || s->health_state != p->last_health;
    p->has_health = true;
    p->last_valid = valid_read;
    p->last_health = s->health_state;
    p->last_temp_flags = s->temp_health.fault_flags;
    p->last_hum_flags = s->hum_health.fault_flags;

    // An unrelated humidity fault must not hide a trusted temperature crossing.
    uint32_t relevant = 0;
    if (p->has_reported_temperature && s->valid && isfinite(s->temperature) && s->temp_health.state == SENSOR_STATE_HEALTHY)
        relevant = b1_temperature_relevance(p->reported_temperature, s->temperature,
            p->temperature_threshold, p->temperature_margin);
    s->control_relevant_change = relevant != 0;

    if (!s->usable) {
        // Suspect values never alter environmental EMA/history/event debounce.
        p->untrusted = true;
        s->mode = s->health_state == SENSOR_STATE_DEGRADED ? "ACTIVE" : "STABLE";
        s->next_interval_ms = (uint32_t)((s->health_state == SENSOR_STATE_DEGRADED ?
            p->degraded_interval_s : p->fault_interval_s) * 1000);
        s->score = NAN;
        s->detected_event = false;
        s->upload_reasons = relevant | (s->alert_requested ? UP_SENSOR_FAULT : 0);
        s->upload_requested = s->upload_reasons != 0;
        s->reason = "untrusted_measurement";
        return;
    }
    if (p->untrusted) {
        cd_init(&p->detector, &p->cd_config);
        as_init(&p->scheduler, &p->as_config);
        p->untrusted = false;
    }
    const float values[CD_NUM_CHANNELS] = {s->temperature, s->humidity, 0, 0};
    const bool valid[CD_NUM_CHANNELS] = {true, true, false, false};
    bool event = false;
    s->score = cd_update(&p->detector, t, values, valid, &event);
    as_decision_t decision;
    const as_t report_baseline = p->scheduler;
    as_update(&p->scheduler, t, values, valid, s->score, event, &decision);
    // The upstream core treats upload intent as reported. At the B1 boundary
    // only durable gateway confirmation advances heartbeat/delta baselines.
    p->scheduler.last_upload_t = report_baseline.last_upload_t;
    p->scheduler.has_uploaded = report_baseline.has_uploaded;
    memcpy(p->scheduler.last_upload_values, report_baseline.last_upload_values, sizeof(p->scheduler.last_upload_values));
    memcpy(p->scheduler.last_upload_valid, report_baseline.last_upload_valid, sizeof(p->scheduler.last_upload_valid));
    if (!p->scheduler.has_uploaded && p->as_config.up_first_sample) {
        decision.upload_requested = true;
        decision.upload_reasons |= UP_FIRST_SAMPLE;
    }
    s->mode = decision.state == AS_ALERT ? "ALERT" : decision.state == AS_ACTIVE ? "ACTIVE" : "STABLE";
    s->reason = s->mode;
    s->next_interval_ms = (uint32_t)(decision.interval_s * 1000);
    s->detected_event = decision.detected_event;
    s->upload_reasons = decision.upload_reasons;
    if (health_changed) s->upload_reasons |= UP_HEALTH_CHANGE;
    if (s->recovered) s->upload_reasons |= UP_SENSOR_RECOVERY;
    s->upload_reasons |= relevant;
    s->upload_requested = s->upload_reasons != 0;
}
