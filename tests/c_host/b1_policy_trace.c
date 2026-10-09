#include "b1.h"
#include "b1_policy.h"
#include "b1_transport.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>

#include "b1_storage.h"
b1_stats_t b1_stats;
char b1_boot_id[B1_BOOT_ID_SIZE] = "host-test";
static unsigned queue_sends, network_sends;
static bool expect_missing_fields;
static bool reject_second;
bool b1_storage_save(void *ctx, unsigned slot, const b1_record_t *r) {
    (void)ctx; (void)slot; (void)r; return true;
}
bool b1_storage_init(b1_outbox_t *q) { b1_outbox_init(q,b1_storage_save,NULL); return true; }
void b1_storage_lock(void) {}
void b1_storage_unlock(void) {}

static bool sink(void *ctx, const char *type, cJSON *payload) {
    (void)ctx;
    if (strcmp(type,"SENSOR_DATA")==0) {
        cJSON *data=cJSON_GetObjectItemCaseSensitive(payload,"data");
        bool missing=cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(data,"temperature")) &&
            cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(data,"humidity"));
        assert(expect_missing_fields == missing);
        network_sends++;
    }
    cJSON_Delete(payload);
    return true;
}
int main(int argc, char **argv) {
    reject_second = argc > 1 && strcmp(argv[1], "--reject-second") == 0;
    static b1_policy_t p;
    if (!b1_policy_init(&p)) return 1;
    assert(b1_queue_init());
    unsigned long long ms; float temp, hum; int valid;
    unsigned seq=0;
    const b1_transport_t transport = {.send=sink};
    while (scanf("%llu %f %f %d", &ms, &temp, &hum, &valid)==4) {
        b1_sample_t s = {.seq=++seq,.monotonic_ms=ms,.temperature=temp,.humidity=hum,.valid=valid!=0};
        b1_policy_update(&p,&s);
        expect_missing_fields = !s.valid;
        b1_stats.sensor_samples++;
        bool admitted = !(reject_second && s.seq==2) && b1_queue_sample(&s);
        if (admitted) b1_policy_mark_reported(&p, &s);
        if (admitted) {
            queue_sends++;
            b1_record_t record;
            assert(b1_queue_next(&record,ms));
            const char *line=record.wire;
            while (*line) {
                const char *end=strchr(line,'\n'); assert(end);
                cJSON *root=cJSON_ParseWithLength(line,(size_t)(end-line)); assert(root);
                cJSON *type=cJSON_GetObjectItemCaseSensitive(root,"type");
                cJSON *payload=cJSON_DetachItemFromObjectCaseSensitive(root,"payload");
                sink(NULL,type->valuestring,payload);
                cJSON *id=cJSON_GetObjectItemCaseSensitive(root,"message_id");
                assert(b1_queue_ack(id->valuestring));
                cJSON_Delete(root); line=end+1;
            }
        }
        // An accidental caller bypassing the queue must still send nothing.
        if (!s.upload_requested) b1_transmit_sample(&transport,&s);
        printf("%s %u %d %d %d %u %u %d %.7g %u\n", s.mode,s.next_interval_ms,
            s.detected_event,s.upload_requested,admitted,queue_sends,network_sends,
            s.health_state,s.score,s.upload_reasons);
    }
    return 0;
}
