#include "b1_radio_schedule.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    b1_radio_schedule_t s;b1_radio_schedule_init(&s);
    assert(!b1_radio_schedule_due(&s,0,false));
    assert(b1_radio_schedule_wait(&s,0,false)==UINT32_MAX);
    assert(b1_radio_schedule_due(&s,100,true)); /* empty->HIGH wakes now */
    b1_radio_schedule_finish(&s,101,true,false);
    assert(s.due_ms==60101);
    for(uint64_t i=102;i<60101;i++)assert(!b1_radio_schedule_due(&s,i,true));
    assert(b1_radio_schedule_due(&s,60101,true));
    b1_radio_schedule_finish(&s,60102,true,false);
    assert(s.due_ms==180102);
    for(unsigned i=0;i<20;i++) {
        assert(b1_radio_schedule_due(&s,s.due_ms,true));
        b1_radio_schedule_finish(&s,s.due_ms,true,false);
        assert(s.backoff_ms<=300000);
    }
    uint64_t t=s.due_ms;
    assert(b1_radio_schedule_due(&s,t,true));
    b1_radio_schedule_finish(&s,t,true,true); /* ACK progress, backlog remains */
    assert(s.backoff_ms==60000 && s.due_ms==t+3000);
    b1_radio_schedule_finish(&s,t+3000,false,true);
    assert(!b1_radio_schedule_due(&s,t+3001,true)); /* coalesced wake storms */
    assert(b1_radio_schedule_due(&s,t+5000,true));
    assert(!b1_radio_schedule_due(&s,t,true)); /* clock rollback */
    assert(!b1_radio_schedule_due(&s,UINT64_MAX,true));
    assert(b1_radio_schedule_wait(&s,UINT64_MAX,true)==300000);
    puts("notification deadlines / unavailable backoff / coalescing / rollback: PASS");
    return 0;
}
