#include "b1.h"
#include "b1_transport.h"
#include "b1_storage.h"
#if CONFIG_B1_USE_E220 && !CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL
#include "b1_lora_network.h"
#endif
#include <stdio.h>
#include <string.h>

static b1_outbox_t outbox;
static b1_sample_t confirmed;
static bool has_confirmed;
static uint32_t confirmed_seq;
static b1_record_t building; /* protected by backend mutex; never persist pointers */

bool b1_queue_init(void) {
    bool ok=b1_storage_init(&outbox);
    if(ok) { has_confirmed=false; confirmed_seq=0; memset(&confirmed,0,sizeof(confirmed)); }
    return ok; /* boot initialization, before tasks start */
}

static bool capture(void *context, const char *type, cJSON *payload)
{
    b1_record_t *r = context;
    cJSON_AddStringToObject(payload, "sample_id", r->sample_id);
    cJSON_AddStringToObject(payload, "delivery_contract", "gateway-durable-v1");
    cJSON_AddStringToObject(payload, "importance", r->high ? "HIGH" : "NORMAL");
    cJSON_AddStringToObject(payload, "policy_version", b1_policy_version());
    if (strcmp(type, "ALERT") == 0) {
        cJSON_AddStringToObject(payload, "boot_id", r->boot_id);
        cJSON_AddNumberToObject(payload, "device_monotonic_ms", (double)r->acquired_ms);
    }
    cJSON *root = b1_envelope(type, "A1", payload, r->acquired_ms / 1000.0);
    char *raw = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!raw) return false;
    size_t used = strlen(r->wire), n = strlen(raw);
    bool ok = used + n + 2 <= sizeof(r->wire);
    if (ok) { memcpy(r->wire + used, raw, n); r->wire[used+n]='\n'; r->wire[used+n+1]=0; }
    cJSON_free(raw);
    return ok;
}

bool b1_queue_sample(const b1_sample_t *sample)
{
    if (!sample->upload_requested) return false;
    b1_storage_lock();
    bool was_empty=b1_outbox_count(&outbox)==0;
    memset(&building, 0, sizeof(building));
    building.acquired_ms=sample->monotonic_ms;
    building.sequence=sample->seq; building.has_alert=sample->alert_requested;
    building.high=sample->alert_requested || sample->detected_event || sample->control_relevant_change ||
        (sample->upload_reasons & ((1u<<1) | (1u<<2) | (1u<<8) | (1u<<9)));
    snprintf(building.boot_id, sizeof(building.boot_id), "%s", b1_boot_id);
    snprintf(building.sample_id, sizeof(building.sample_id), "B1-%s-%08lx", b1_boot_id, (unsigned long)sample->seq);
    bool ok = b1_transmit_sample(&(b1_transport_t){.context=&building,.send=capture}, sample) &&
        b1_outbox_admit(&outbox, &building);
    if (!ok) {
        b1_stats.local_queue_drops++;
        printf("B1_DELIVERY {\"event\":\"ADMISSION_REJECTED\",\"sample_id\":\"%s\",\"importance\":\"%s\"}\n",
               building.sample_id, building.high ? "HIGH" : "NORMAL");
    }
    bool notify=ok && (was_empty || building.high);
    b1_storage_unlock();
#if CONFIG_B1_USE_E220 && !CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL
    if(notify)b1_lora_notify_pending();
#else
    (void)notify;
#endif
    return ok;
}

bool b1_queue_next(b1_record_t *record, uint64_t now_ms)
{
    b1_storage_lock();
    int slot = b1_outbox_next(&outbox, now_ms);
    if (slot >= 0) *record=outbox.entries[slot].record;
    b1_storage_unlock(); return slot >= 0;
}

static void remember_confirmed(const b1_record_t *r)
{
    if (strcmp(r->boot_id, b1_boot_id) != 0 || r->sequence <= confirmed_seq) return;
    cJSON *root=cJSON_Parse(r->wire);
    if(!cJSON_IsObject(root)) { cJSON_Delete(root); return; }
    cJSON *p=cJSON_GetObjectItemCaseSensitive(root,"payload");
    cJSON *data=cJSON_GetObjectItemCaseSensitive(p,"data");
    cJSON *temp=cJSON_GetObjectItemCaseSensitive(data,"temperature");
    cJSON *hum=cJSON_GetObjectItemCaseSensitive(data,"humidity");
    cJSON *health=cJSON_GetObjectItemCaseSensitive(p,"health");
    cJSON *th=cJSON_GetObjectItemCaseSensitive(health,"temperature");
    cJSON *state=cJSON_GetObjectItemCaseSensitive(th,"state");
    confirmed=(b1_sample_t){.seq=r->sequence,.monotonic_ms=r->acquired_ms,
        .valid=cJSON_IsNumber(temp) && cJSON_IsNumber(hum),
        .temperature=cJSON_IsNumber(temp) ? (float)temp->valuedouble : 0,
        .humidity=cJSON_IsNumber(hum) ? (float)hum->valuedouble : 0,
        .usable=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(p,"usable_for_control"))};
    confirmed.temp_health.state=cJSON_IsString(state) && strcmp(state->valuestring,"HEALTHY")==0
        ? SENSOR_STATE_HEALTHY : SENSOR_STATE_FAULT;
    confirmed_seq=r->sequence; has_confirmed=true;
    cJSON_Delete(root);
}

bool b1_queue_ack(const char *message_id)
{
    b1_storage_lock();
    int slot=-1;
    for (unsigned i=0; i<B1_OUTBOX_CAPACITY; i++) {
        b1_entry_t *e=&outbox.entries[i];
        if (!e->active) continue;
        size_t len=strlen(e->record.sample_id);
        if (strlen(message_id)==len+2 && strncmp(message_id,e->record.sample_id,len)==0) { slot=(int)i; break; }
    }
    bool ok=b1_outbox_ack(&outbox, message_id);
    if (ok && slot>=0 && !outbox.entries[slot].active) remember_confirmed(&outbox.entries[slot].record);
    b1_storage_unlock(); return ok;
}

bool b1_queue_take_confirmed(b1_sample_t *sample)
{
    b1_storage_lock();
    bool ok=has_confirmed;
    if (ok) { *sample=confirmed; has_confirmed=false; }
    b1_storage_unlock(); return ok;
}

void b1_queue_stats(void)
{
    b1_storage_lock();
    unsigned quarantined=0;
    for(unsigned i=0;i<B1_OUTBOX_CAPACITY;i++)quarantined+=outbox.entries[i].quarantined;
    printf("B1_DELIVERY {\"event\":\"STATS\",\"pending\":%u,\"acknowledged\":%lu,\"retries\":%lu,"
           "\"exhausted\":%lu,\"rejected\":%lu,\"storage_failures\":%lu,\"probes\":%lu,\"boot_attempts\":%llu,\"quarantined\":%u}\n",
           b1_outbox_count(&outbox), (unsigned long)outbox.acknowledged,
           (unsigned long)outbox.retries, (unsigned long)outbox.exhausted,
           (unsigned long)outbox.rejected, (unsigned long)outbox.storage_failures,
           (unsigned long)outbox.probes, (unsigned long long)outbox.boot_attempts,quarantined);
    b1_storage_unlock();
}

unsigned b1_queue_pending_count(void){b1_storage_lock();unsigned n=b1_outbox_count(&outbox);b1_storage_unlock();return n;}
