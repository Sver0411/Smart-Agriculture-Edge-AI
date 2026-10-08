#include "b1_radio_schedule.h"
#include <limits.h>
static uint64_t deadline(uint64_t now, uint32_t delay) {
    return now > UINT64_MAX-delay ? UINT64_MAX : now+delay;
}
void b1_radio_schedule_init(b1_radio_schedule_t *s) {
    *s=(b1_radio_schedule_t){.backoff_ms=60000};
}
bool b1_radio_schedule_due(b1_radio_schedule_t *s, uint64_t now, bool pending) {
    if(now<s->now_ms || now==UINT64_MAX)return false;
    s->now_ms=now;
    return pending && now>=s->due_ms;
}
void b1_radio_schedule_finish(b1_radio_schedule_t *s, uint64_t now, bool pending, bool progress) {
    if(now<s->now_ms || now==UINT64_MAX)return;
    s->now_ms=now;
    uint32_t delay=2000; /* Coalesce successful frequent sample arrivals. */
    if(pending && !progress) {
        delay=s->backoff_ms;
        s->backoff_ms=s->backoff_ms>=150000 ? 300000 : s->backoff_ms*2;
    } else {
        s->backoff_ms=60000;
        if(pending)delay=3000;
    }
    s->due_ms=deadline(now,delay);
}
uint32_t b1_radio_schedule_wait(b1_radio_schedule_t *s, uint64_t now, bool pending) {
    if(!pending)return UINT32_MAX;
    if(now<s->now_ms || now==UINT64_MAX)return 300000;
    if(now>=s->due_ms)return 0;
    uint64_t delta=s->due_ms-now;
    return delta>300000 ? 300000 : (uint32_t)delta;
}
