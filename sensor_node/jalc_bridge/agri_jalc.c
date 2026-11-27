#include "agri_jalc.h"
#include <string.h>

bool agri_jalc_init(agri_jalc_t *node, int channels, const double *noise)
{
    memset(node, 0, sizeof(*node));
    node->link.present = true;
    /* The durable outbox owns retries. No second copy is budgeted here. */
    return tais_jalc_init(&node->kernel, channels, noise, NULL, TAIS_JALC_VARIANT_FULL);
}

bool agri_jalc_step(agri_jalc_t *node, double t, const tais_jalc_snapshot_t *s,
                    tais_jalc_decision_t *decision)
{
    return tais_jalc_update(&node->kernel, t, s->value, s->valid, s->active,
                            s->health_state, s->health_flags, &node->link, decision);
}

void agri_jalc_confirm(agri_jalc_t *node, double acquired, const tais_jalc_snapshot_t *reported)
{
    /* The upstream kernel has one pending slot. Restore the snapshot identified
       by the durable receipt, including when newer samples are in flight. */
    node->kernel.pending = *reported;
    node->kernel.pending.has_snapshot = true;
    tais_jalc_on_tx_result(&node->kernel, acquired, true, &node->link);
    for (int i = 0; i < node->kernel.n_channels; ++i) {
        if (reported->valid[i]) {
            node->link.has_confirmed_finite[i] = true;
            node->link.last_confirmed_finite_t[i] = acquired;
        }
    }
}

void agri_jalc_feedback(agri_jalc_t *node, bool missed_ack)
{
    node->link.loss_ema = 0.8 * node->link.loss_ema + 0.2 * (missed_ack ? 1.0 : 0.0);
}

size_t agri_jalc_size(void) { return sizeof(agri_jalc_t); }
