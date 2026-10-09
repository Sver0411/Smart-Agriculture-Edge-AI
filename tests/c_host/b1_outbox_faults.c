#include "b1_outbox.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static b1_record_t disk[B1_OUTBOX_CAPACITY];
static bool present[B1_OUTBOX_CAPACITY], fail_write;
static unsigned writes;
static bool save(void *ctx, unsigned slot, const b1_record_t *record) {
    (void)ctx;
    if (fail_write) return false;
    writes++;
    present[slot]=record!=NULL;
    if (record) disk[slot]=*record;
    return true;
}
static b1_outbox_t q;
static void reboot(void) {
    b1_outbox_init(&q,save,NULL);
    for (unsigned i=0;i<B1_OUTBOX_CAPACITY;i++)
        if (present[i]) assert(b1_outbox_restore(&q,i,&disk[i]));
}
static b1_record_t sample(unsigned seq, bool high, bool alert) {
    b1_record_t r={0};r.high=high;r.has_alert=alert;r.sequence=seq;r.acquired_ms=100;
    strcpy(r.boot_id,"device-boot");
    snprintf(r.sample_id,sizeof(r.sample_id),"B1-device-boot-%08x",seq);
    strcpy(r.wire,"{\"sample\":1}\n"); return r;
}
static void ack(unsigned seq, char suffix) {
    char id[120];snprintf(id,sizeof(id),"B1-device-boot-%08x-%c",seq,suffix);
    assert(b1_outbox_ack(&q,id));
}
int main(void) {
    reboot();
    /* Normal admission costs zero flash writes and is honestly volatile. */
    b1_record_t r=sample(1,false,false);
    assert(b1_outbox_admit(&q,&r));assert(writes==0);reboot();assert(!b1_outbox_count(&q));
    /* Power off before sending: committed critical identity/content recover. */
    r=sample(2,true,true);assert(b1_outbox_admit(&q,&r));assert(writes==1);
    reboot();assert(b1_outbox_count(&q)==1);int slot=b1_outbox_next(&q,0);assert(slot>=0);
    char original[4096];strcpy(original,q.entries[slot].record.wire);
    /* TCP success does not delete; power off after send / before ACK. */
    assert(b1_outbox_count(&q)==1);reboot();slot=b1_outbox_next(&q,0);assert(slot>=0);
    assert(strcmp(original,q.entries[slot].record.wire)==0);
    assert(!b1_outbox_ack(&q,"unrelated-S"));
    ack(2,'S');assert(b1_outbox_count(&q)==1);
    /* Lost companion ACK and reboot safely resend both messages. */
    reboot();assert(b1_outbox_next(&q,0)>=0);ack(2,'A');assert(b1_outbox_count(&q)==1);
    fail_write=true;assert(!b1_outbox_ack(&q,"B1-device-boot-00000002-S"));
    assert(b1_outbox_count(&q)==1);fail_write=false;ack(2,'S');assert(!b1_outbox_count(&q));
    reboot();assert(!b1_outbox_count(&q));assert(writes==2);
    /* Disconnection exhausts a finite per-boot retry window without dropping. */
    r=sample(3,true,false);assert(b1_outbox_admit(&q,&r));unsigned before=writes;
    for (unsigned n=0;n<B1_MAX_ATTEMPTS;n++) {
        uint64_t now=n*100000;
        assert(b1_outbox_next(&q,now)>=0);
        assert(b1_outbox_next(&q,now+1)==-1);
        b1_outbox_tick(&q,now+B1_ACK_TIMEOUT_MS);
    }
    assert(q.retries==4 && writes==before);
    assert(b1_outbox_next(&q,10000000)>=0);assert(q.exhausted==1);
    assert(q.retries==5 && writes==before && b1_outbox_count(&q)==1);
    ack(3,'S'); /* late valid receipt can still release the parked record */
    /* Overflow never evicts already admitted critical data; reserve four. */
    for (unsigned n=10;n<22;n++) {r=sample(n,false,false);assert(b1_outbox_admit(&q,&r));}
    r=sample(22,false,false);assert(!b1_outbox_admit(&q,&r));
    for (unsigned n=30;n<34;n++) {r=sample(n,true,false);assert(b1_outbox_admit(&q,&r));}
    r=sample(34,true,false);assert(!b1_outbox_admit(&q,&r));assert(b1_outbox_count(&q)==16);
    reboot();assert(b1_outbox_count(&q)==4);
    /* Corrupt/version-incompatible snapshots are rejected without overwrite. */
    b1_outbox_t recovered; b1_outbox_init(&recovered,save,NULL);
    unsigned used=0;while(!present[used])used++;
    b1_record_t corrupt=disk[used];corrupt.wire[5]^=1;
    assert(!b1_outbox_restore(&recovered,used,&corrupt));
    corrupt=disk[used];corrupt.version=99;assert(!b1_outbox_restore(&recovered,used,&corrupt));
    assert(!b1_outbox_restore(&recovered,B1_OUTBOX_CAPACITY,&disk[used]));
    r=sample(50,true,false);fail_write=true;assert(!b1_outbox_admit(&q,&r));
    assert(q.storage_failures==1 && b1_outbox_count(&q)==4);
    fail_write=false;
    r=sample(0,false,false);assert(!b1_outbox_admit(&q,&r));
    r=sample(0xffffffffu,false,false);assert(b1_outbox_admit(&q,&r));
    /* ACK spoofing cannot remove an entry never submitted to transport. */
    assert(!b1_outbox_ack(&q,"B1-device-boot-ffffffff-S"));
    puts("power-before-send power-before-ack lost-ack duplicate overflow outage storage-failure corruption: PASS");
}
