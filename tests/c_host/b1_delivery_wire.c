/* Real JSON serialization and admission; no FreeRTOS or RF claims. */
#include "b1.h"
#include "b1_policy.h"
#include "b1_storage.h"
#include <stdio.h>
#include <assert.h>
b1_stats_t b1_stats;
char b1_boot_id[B1_BOOT_ID_SIZE]="host-test";
static unsigned writes;
bool b1_storage_save(void *ctx, unsigned slot, const b1_record_t *r) {
    (void)ctx;(void)slot;(void)r;writes++;return true;
}
bool b1_storage_init(b1_outbox_t *q) { b1_outbox_init(q,b1_storage_save,NULL);return true; }
void b1_storage_lock(void) {}
void b1_storage_unlock(void) {}
int main(void) {
    assert(b1_queue_init());b1_policy_t p;assert(b1_policy_init(&p));
    for (unsigned seq=1;seq<=2;seq++) {
        b1_sample_t s={.seq=seq,.monotonic_ms=seq*1000,.temperature=seq==1?25:150,.humidity=60,.valid=true};
        b1_policy_update(&p,&s);
        if (seq==1) assert(!p.scheduler.has_uploaded); /* evaluation is not delivery */
        assert(b1_queue_sample(&s));
        assert(writes==(seq==1?0:1));
        b1_sample_t confirmed;assert(!b1_queue_take_confirmed(&confirmed));
        b1_record_t r;assert(b1_queue_next(&r,seq*1000));
        fputs(r.wire,stdout);
        char id[120];snprintf(id,sizeof(id),"%s-S",r.sample_id);assert(b1_queue_ack(id));
        if (r.has_alert) { assert(!b1_queue_take_confirmed(&confirmed));snprintf(id,sizeof(id),"%s-A",r.sample_id);assert(b1_queue_ack(id)); }
        assert(b1_queue_take_confirmed(&confirmed));
        assert(confirmed.seq==seq && confirmed.monotonic_ms==seq*1000);
        assert(confirmed.valid && confirmed.temperature==s.temperature && confirmed.usable==s.usable);
        b1_policy_mark_reported(&p,&confirmed);
    }
    assert(writes==2); /* fault admission + ACK cleanup; no retry writes */
}
