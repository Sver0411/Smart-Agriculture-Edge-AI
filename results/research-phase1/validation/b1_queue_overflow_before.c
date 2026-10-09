/* Baseline regression: a saturated queue must retain its unacknowledged head. */
#include "b1.h"
#include <assert.h>
QueueHandle_t b1_queue;
b1_stats_t b1_stats;
char b1_boot_id[16];
static b1_sample_t head = {.seq=1,.upload_requested=true,.alert_requested=true};
static int full = 1;
int xQueueSend(QueueHandle_t q, const void *item, unsigned ticks) {
    (void)q; (void)ticks;
    if (full) return 0;
    head = *(const b1_sample_t *)item; full=1; return pdTRUE;
}
int xQueueReceive(QueueHandle_t q, void *item, unsigned ticks) {
    (void)q; (void)ticks;
    if (!full) return 0;
    *(b1_sample_t *)item=head;full=0;return pdTRUE;
}
int main(void) {
    b1_sample_t incoming = {.seq=2,.upload_requested=true};
    assert(!b1_queue_sample(&incoming));
    assert(head.seq==1);
}
