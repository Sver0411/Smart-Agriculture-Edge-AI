#include "b1_outbox.h"
#include "b1_retry.h"
#include <string.h>
#include <stdio.h>
#include <limits.h>

static uint32_t record_crc(const b1_record_t *record)
{
    const unsigned char *p = (const unsigned char *)record;
    uint32_t crc = 0xffffffff;
    for (size_t i = offsetof(b1_record_t, order); i < sizeof(*record); i++) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static bool bounded_text(const char *s, size_t n)
{
    return s[0] && memchr(s, 0, n) != NULL;
}

void b1_record_seal(b1_record_t *r) { r->version=1; r->crc=record_crc(r); }

bool b1_record_valid(const b1_record_t *r)
{
    if (!r || r->version != 1 || r->crc != record_crc(r) || !r->order ||
        r->order == UINT64_MAX || !r->sequence || r->high > 1 || r->has_alert > 1 ||
        !bounded_text(r->boot_id, sizeof(r->boot_id)) ||
        !bounded_text(r->sample_id, sizeof(r->sample_id)) ||
        !bounded_text(r->wire, sizeof(r->wire))) return false;
    for (const char *p=r->boot_id; *p; p++)
        if (!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-')) return false;
    char id[B1_SAMPLE_ID_SIZE];
    int n = snprintf(id, sizeof(id), "B1-%s-%08lx", r->boot_id, (unsigned long)r->sequence);
    return n > 0 && (size_t)n < sizeof(id) && strcmp(id, r->sample_id) == 0 &&
        r->wire[strlen(r->wire) - 1] == '\n';
}

void b1_outbox_init(b1_outbox_t *q, b1_store_fn store, void *ctx)
{
    memset(q, 0, sizeof(*q));
    q->store = store; q->store_context = ctx; q->next_order = 1;
}

unsigned b1_outbox_count(const b1_outbox_t *q)
{
    unsigned n = 0;
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++) n += q->entries[i].active;
    return n;
}

bool b1_outbox_restore(b1_outbox_t *q, unsigned slot, const b1_record_t *r)
{
    if (!r || slot >= B1_OUTBOX_CAPACITY || q->entries[slot].active || !r->high ||
        !b1_record_valid(r) || r->order == UINT64_MAX) return false;
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++)
        if (q->entries[i].active && (q->entries[i].record.order == r->order ||
            strcmp(q->entries[i].record.sample_id, r->sample_id) == 0)) return false;
    q->entries[slot] = (b1_entry_t){.record=*r, .active=true, .state=B1_PENDING};
    if (q->next_order <= r->order) q->next_order = r->order + 1;
    return true;
}

bool b1_outbox_admit(b1_outbox_t *q, const b1_record_t *r)
{
    if (!r) { q->rejected++; return false; }
    b1_record_t copy = *r;
    copy.order=q->next_order; b1_record_seal(&copy);
    if (!b1_record_valid(&copy)) { q->rejected++; return false; }
    unsigned normal = 0;
    int free_slot = -1;
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++) {
        if (!q->entries[i].active && !q->entries[i].quarantined) { if (free_slot < 0) free_slot = (int)i; }
        else if (q->entries[i].active || q->entries[i].quarantined) {
            normal += !q->entries[i].record.high;
            if (strcmp(q->entries[i].record.sample_id, r->sample_id) == 0) {
                q->rejected++; return false;
            }
        }
    }
    if (free_slot < 0 || (!r->high && normal >= B1_OUTBOX_NORMAL_LIMIT) ||
        q->next_order == UINT64_MAX) { q->rejected++; return false; }
    if (copy.high && (!q->store || !q->store(q->store_context, (unsigned)free_slot, &copy))) {
        /* An error may mean committed-but-unacknowledged storage. Reserve
         * slot and order until a fresh reload resolves it; never send it now. */
        q->entries[free_slot]=(b1_entry_t){.record=copy,.quarantined=true};
        q->next_order++;
        q->storage_failures++; q->rejected++; return false;
    }
    q->entries[free_slot] = (b1_entry_t){.record=copy, .active=true, .state=B1_PENDING};
    q->next_order++;
    return true;
}

void b1_outbox_tick(b1_outbox_t *q, uint64_t now)
{
    if (now < q->now_ms || now == UINT64_MAX) return;
    q->now_ms=now;
    if (q->window_open && now >= q->window_end_ms) {
        q->window_open=false;
        q->pause_until_ms=b1_deadline(q->window_end_ms,B1_PROBE_MIN_MS);
    }
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++) {
        b1_entry_t *e = &q->entries[i];
        if (!e->active || e->state != B1_IN_FLIGHT || now < e->due_ms) continue;
        uint64_t timed_out=e->due_ms;
        if (e->probing || e->attempts >= B1_MAX_ATTEMPTS) {
            if (e->probing) e->probe_delay_ms=b1_probe_delay(e->probe_delay_ms);
            else { e->probe_delay_ms=B1_PROBE_MIN_MS; q->exhausted++; }
            e->state=B1_FAILED; e->due_ms=b1_deadline(timed_out,e->probe_delay_ms);
        } else {
            e->state=B1_RETRY_PENDING;
            e->due_ms=b1_deadline(timed_out,1000u << (e->attempts-1));
        }
    }
}

int b1_outbox_next(b1_outbox_t *q, uint64_t now)
{
    if (now < q->now_ms || now == UINT64_MAX) return -1;
    b1_outbox_tick(q, now);
    int best = -1;
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++) {
        b1_entry_t *e = &q->entries[i];
        if (!e->active) continue;
        if (e->state == B1_IN_FLIGHT) return -1;
        if (now < e->due_ms) continue;
        if (best < 0 || e->record.order < q->entries[best].record.order) best = (int)i;
    }
    if (best < 0 || now < q->pause_until_ms) return -1;
    if (!q->window_open) {
        q->window_open=true; q->window_attempts=0;
        q->window_end_ms=b1_deadline(now,B1_COMM_WINDOW_MS);
    }
    if (q->window_attempts >= B1_COMM_MAX_ATTEMPTS) {
        q->window_open=false; q->pause_until_ms=b1_deadline(now,B1_PROBE_MIN_MS); return -1;
    }
    b1_entry_t *e = &q->entries[best];
    if (e->total_attempts) q->retries++;
    e->probing=e->state==B1_FAILED;
    if (e->probing) q->probes++; else e->attempts++;
    if (e->total_attempts < UINT64_MAX) e->total_attempts++;
    if (q->boot_attempts < UINT64_MAX) q->boot_attempts++;
    q->window_attempts++;
    e->state=B1_IN_FLIGHT;
    e->due_ms=b1_deadline(now,B1_ACK_TIMEOUT_MS);
    if (e->due_ms > q->window_end_ms) e->due_ms=q->window_end_ms;
    return best;
}

bool b1_outbox_ack(b1_outbox_t *q, const char *id)
{
    for (unsigned i = 0; i < B1_OUTBOX_CAPACITY; i++) {
        b1_entry_t *e = &q->entries[i];
        if (!e->active || !e->total_attempts) continue;
        char expected[B1_SAMPLE_ID_SIZE+3];
        snprintf(expected, sizeof(expected), "%s-S", e->record.sample_id);
        if (strcmp(id, expected) == 0) e->ack_mask |= 1;
        else {
            snprintf(expected, sizeof(expected), "%s-A", e->record.sample_id);
            if (!e->record.has_alert || strcmp(id, expected) != 0) continue;
            e->ack_mask |= 2;
        }
        if (e->ack_mask != (e->record.has_alert ? 3 : 1)) return true;
        if (e->record.high && (!q->store || !q->store(q->store_context, i, NULL))) {
            q->storage_failures++; return false; /* deletion uncertain: retain and resend */
        }
        e->active=false; q->acknowledged++;
        if (!b1_outbox_count(q)) q->window_open=false;
        return true;
    }
    return false;
}
