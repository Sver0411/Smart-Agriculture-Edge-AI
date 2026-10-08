#include "b1_types.h"
#include "b1_transport.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint32_t message_counter;

cJSON *b1_envelope(const char *type, const char *target, cJSON *payload, double uptime_s)
{
    cJSON *root = cJSON_CreateObject();
    char id[32];
    snprintf(id, sizeof(id), "B1-%s-%08lx", b1_boot_id, (unsigned long)++message_counter);
    cJSON_AddStringToObject(root, "type", type);
    cJSON_AddStringToObject(root, "source", "B1");
    cJSON_AddStringToObject(root, "target", target);
    // The envelope carries uptime seconds. Gateway uses receipt wall time for physical B1.
    cJSON_AddNumberToObject(root, "timestamp", uptime_s);
    cJSON_AddStringToObject(root, "message_id", id);
    cJSON_AddItemToObject(root, "payload", payload);
    return root;
}

static cJSON *health_json(sensor_health_result_t health)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "score", health.health_score);
    cJSON_AddStringToObject(obj, "state", sensor_trust_state_name(health.state));
    cJSON_AddNumberToObject(obj, "flags", health.fault_flags);
    return obj;
}

bool b1_transmit_sample(const b1_transport_t *transport, const b1_sample_t *s)
{
    if (!s->upload_requested) return true;
    cJSON *payload = cJSON_CreateObject();
    cJSON_AddStringToObject(payload, "node_mode", "physical");
    cJSON_AddStringToObject(payload, "timestamp_source", "device_uptime");
    cJSON_AddStringToObject(payload, "boot_id", b1_boot_id);
    cJSON_AddNumberToObject(payload, "sample_seq", s->seq);
    cJSON_AddNumberToObject(payload, "device_monotonic_ms", (double)s->monotonic_ms);
    cJSON_AddBoolToObject(payload, "usable_for_control", s->usable);
    cJSON_AddBoolToObject(payload, "physical_read_ok", s->valid);
    cJSON_AddBoolToObject(payload, "test_injected", s->injected);
    cJSON_AddStringToObject(payload, "health_state", sensor_trust_state_name(s->health_state));
    cJSON *data = cJSON_AddObjectToObject(payload, "data");
    if (s->valid) {
        cJSON_AddNumberToObject(data, "temperature", s->temperature);
        cJSON_AddNumberToObject(data, "humidity", s->humidity);
    } else {
        // Preserve missing channels as fault evidence; an empty data object
        // would be rejected by Cloud and block persisted-ACK FIFO replay.
        cJSON_AddNullToObject(data, "temperature");
        cJSON_AddNullToObject(data, "humidity");
    }
    cJSON *health = cJSON_AddObjectToObject(payload, "health");
    cJSON_AddItemToObject(health, "temperature", health_json(s->temp_health));
    cJSON_AddItemToObject(health, "humidity", health_json(s->hum_health));
    cJSON *sampling = cJSON_AddObjectToObject(payload, "sampling");
    cJSON_AddNumberToObject(sampling, "next_interval_ms", s->next_interval_ms);
    if (isfinite(s->score)) cJSON_AddNumberToObject(sampling, "score", s->score);
    else cJSON_AddNullToObject(sampling, "score");
    cJSON_AddBoolToObject(sampling, "upload_requested", s->upload_requested);
    cJSON_AddBoolToObject(sampling, "control_relevant_change", s->control_relevant_change);
    static const char *const reason_names[] = {"FIRST_SAMPLE", "EVENT_ONSET", "EVENT_RECOVERY",
        "STATE_CHANGE", "INTERVAL_CHANGE", "PERIODIC_HEARTBEAT", "MEANINGFUL_DELTA",
        "HEALTH_CHANGE", "SENSOR_FAULT", "SENSOR_RECOVERY", "CONTROL_THRESHOLD_CROSSING", "CONTROL_MARGIN_ENTRY"};
    cJSON *reasons = cJSON_CreateArray();
    for (unsigned i = 0; i < sizeof(reason_names)/sizeof(reason_names[0]); i++)
        if (s->upload_reasons & (1u << i)) cJSON_AddItemToArray(reasons, cJSON_CreateString(reason_names[i]));
    cJSON_AddItemToObject(sampling, "upload_reasons", reasons);
    cJSON_AddBoolToObject(sampling, "detected_event", s->detected_event);
    cJSON_AddStringToObject(sampling, "mode", s->mode);
    cJSON_AddStringToObject(sampling, "reason", s->reason);
    if (!transport->send(transport->context, "SENSOR_DATA", payload)) return false;
    b1_stats.sensor_messages++;
    if (s->alert_requested) {
        cJSON *alert = cJSON_CreateObject();
        cJSON_AddStringToObject(alert, "alert_type", s->recovered ? "SENSOR_RECOVERED" :
            s->health_state == SENSOR_STATE_FAULT ? "SENSOR_FAULT" : "SENSOR_DEGRADED");
        cJSON_AddStringToObject(alert, "sensor_node_id", "B1");
        cJSON_AddStringToObject(alert, "health_state", sensor_trust_state_name(s->health_state));
        cJSON_AddStringToObject(alert, "message", s->recovered ? "sensor recovered" : s->injected ? "integration fault injection" : "sensor health anomaly");
        cJSON_AddNumberToObject(alert, "sample_seq", s->seq);
        if (!transport->send(transport->context, "ALERT", alert)) return false;
        b1_stats.alerts++;
    }
    return true;
}
