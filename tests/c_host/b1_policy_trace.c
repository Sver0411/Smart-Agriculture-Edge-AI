#include "b1.h"
#include "b1_policy.h"
#include "b1_transport.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>

QueueHandle_t b1_queue;
b1_stats_t b1_stats;
char b1_boot_id[16] = "host-test";
static b1_sample_t queued;
static unsigned queue_depth, queue_sends, network_sends;
static unsigned null_fields;
static bool expect_missing_fields;
static bool reject_second;
int xQueueSend(QueueHandle_t q, const void *item, unsigned ticks) {
    (void)q; (void)ticks;
    if (reject_second && ((const b1_sample_t *)item)->seq == 2) return 0;
    queued = *(const b1_sample_t *)item; queue_depth++; queue_sends++; return pdTRUE;
}
int xQueueReceive(QueueHandle_t q, void *item, unsigned ticks) {
    (void)q; (void)ticks;
    if (!queue_depth) return 0;
    *(b1_sample_t *)item = queued; queue_depth--; return pdTRUE;
}
static cJSON dummy;
cJSON *cJSON_CreateObject(void) { return &dummy; }
cJSON *cJSON_CreateArray(void) { return &dummy; }
cJSON *cJSON_CreateString(const char *v) { (void)v; return &dummy; }
void cJSON_AddItemToArray(cJSON *a, cJSON *v) { (void)a; (void)v; }
cJSON *cJSON_AddObjectToObject(cJSON *o, const char *n) { (void)o; (void)n; return &dummy; }
void cJSON_AddNumberToObject(cJSON *o, const char *n, double v) { (void)o; (void)n; (void)v; }
void cJSON_AddStringToObject(cJSON *o, const char *n, const char *v) { (void)o; (void)n; (void)v; }
void cJSON_AddBoolToObject(cJSON *o, const char *n, int v) { (void)o; (void)n; (void)v; }
void cJSON_AddNullToObject(cJSON *o, const char *n) {
    (void)o;
    if (strcmp(n,"temperature")==0) null_fields |= 1;
    if (strcmp(n,"humidity")==0) null_fields |= 2;
}
void cJSON_AddItemToObject(cJSON *o, const char *n, cJSON *v) { (void)o; (void)n; (void)v; }
static bool sink(void *ctx, const char *type, cJSON *payload) {
    (void)ctx; (void)payload;
    if (strcmp(type,"SENSOR_DATA")==0) {
        assert(expect_missing_fields == (null_fields == 3));
        network_sends++;
    }
    return true;
}
int main(int argc, char **argv) {
    reject_second = argc > 1 && strcmp(argv[1], "--reject-second") == 0;
    static b1_policy_t p;
    if (!b1_policy_init(&p)) return 1;
    unsigned long long ms; float temp, hum; int valid;
    unsigned seq=0;
    const b1_transport_t transport = {.send=sink};
    while (scanf("%llu %f %f %d", &ms, &temp, &hum, &valid)==4) {
        b1_sample_t s = {.seq=++seq,.monotonic_ms=ms,.temperature=temp,.humidity=hum,.valid=valid!=0};
        b1_policy_update(&p,&s);
        null_fields = 0;
        expect_missing_fields = !s.valid;
        b1_stats.sensor_samples++;
        bool admitted = b1_queue_sample(&s);
        if (admitted) b1_policy_mark_reported(&p, &s);
        b1_sample_t wire;
        if (xQueueReceive(b1_queue,&wire,0)==pdTRUE) b1_transmit_sample(&transport,&wire);
        // An accidental caller bypassing the queue must still send nothing.
        if (!s.upload_requested) b1_transmit_sample(&transport,&s);
        printf("%s %u %d %d %d %u %u %d %.7g %u\n", s.mode,s.next_interval_ms,
            s.detected_event,s.upload_requested,admitted,queue_sends,network_sends,
            s.health_state,s.score,s.upload_reasons);
    }
    return 0;
}
