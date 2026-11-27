/*
 * TAIS Phase 5 - Pure C11 zero-allocation implementation of TAIS-JALC.
 */
#include "tais_jalc.h"

#include <math.h>
#include <string.h>

/* Frozen structural constants matching controller.py */
#define MIN_INTERVAL_S     5.0
#define MAX_INTERVAL_S     60.0
#define QUIET_INTERVAL_S   30.0
#define MAD_MULTIPLIER     1.4826
#define ENTER_Z            3.0
#define RISK_ENTER         1.0
#define RISK_EXIT          0.5
#define HORIZON_S          30.0
#define TREND_CONSISTENCY  0.75
#define CONFIRM_SAMPLES    2
#define FAST_WINDOW_S      120.0
#define FAST_LIMIT         6
#define MAX_BURST_S        30.0
#define FALLBACK_HOLD_S    30.0
#define DEADBAND_MULT      2.0
#define LEGACY_HEARTBEAT_S 120.0
#define EPS_TIME           1e-9

static double clamp_d(double x, double lo, double hi)
{
    if (x < lo) {
        return lo;
    }
    if (x > hi) {
        return hi;
    }
    return x;
}

static double min_d(double a, double b)
{
    return (a < b) ? a : b;
}

static double max_d(double a, double b)
{
    return (a > b) ? a : b;
}

static double median_inplace(double *arr, int n)
{
    int i, j;
    for (i = 1; i < n; i++) {
        double key = arr[i];
        j = i - 1;
        while (j >= 0 && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
    if ((n & 1) != 0) {
        return arr[n / 2];
    }
    return 0.5 * (arr[n / 2 - 1] + arr[n / 2]);
}

static int count_fast_at_due(const tais_jalc_t *ctx, double due_t)
{
    int i;
    int used = 0;
    double cutoff = due_t - FAST_WINDOW_S;
    for (i = 0; i < ctx->fast_len; i++) {
        if (ctx->fast_times[i] > cutoff) {
            used++;
        }
    }
    return used;
}

static double enter_fallback(tais_jalc_t *ctx, double t)
{
    ctx->obs_mode = TAIS_JALC_MODE_SAFE_FALLBACK;
    ctx->fallback_until = t + FALLBACK_HOLD_S;
    ctx->has_burst = false;
    ctx->burst_start = 0.0;
    ctx->confirmed = 0;
    ctx->lead_ch = -1;
    ctx->lead_sign = 0;
    return ctx->params.fallback_interval_s;
}

void tais_jalc_default_params(tais_jalc_params_t *params)
{
    if (params == NULL) {
        return;
    }
    params->fallback_interval_s = 20.0;
    params->diag_interval_s = 15.0;
    params->aoi_cap_quiet_s = 45.0;
    params->aoi_cap_active_s = 20.0;
    params->loss_redundancy_threshold = 0.10;
}

static bool params_valid(const tais_jalc_params_t *p)
{
    if (p == NULL) {
        return false;
    }
    if (!isfinite(p->fallback_interval_s) || !isfinite(p->diag_interval_s) ||
        !isfinite(p->aoi_cap_quiet_s) || !isfinite(p->aoi_cap_active_s) ||
        !isfinite(p->loss_redundancy_threshold)) {
        return false;
    }
    if (p->diag_interval_s < 5.0 || p->diag_interval_s > 60.0) {
        return false;
    }
    if (p->fallback_interval_s < 5.0 || p->fallback_interval_s > 60.0) {
        return false;
    }
    if (p->aoi_cap_active_s < 5.0 || p->aoi_cap_active_s > p->aoi_cap_quiet_s) {
        return false;
    }
    if (p->loss_redundancy_threshold <= 0.0 || p->loss_redundancy_threshold > 1.0) {
        return false;
    }
    return true;
}

bool tais_jalc_init(
    tais_jalc_t *ctx,
    int n_channels,
    const double *noise_floors,
    const tais_jalc_params_t *params,
    tais_jalc_variant_t variant
)
{
    int c;
    tais_jalc_params_t p;

    if (ctx == NULL || noise_floors == NULL) {
        return false;
    }
    if (n_channels < 1 || n_channels > TAIS_JALC_MAX_CHANNELS) {
        return false;
    }
    if (variant != TAIS_JALC_VARIANT_OBS_ONLY &&
        variant != TAIS_JALC_VARIANT_AOI &&
        variant != TAIS_JALC_VARIANT_FULL) {
        return false;
    }
    if (params != NULL) {
        p = *params;
    } else {
        tais_jalc_default_params(&p);
    }
    if (!params_valid(&p)) {
        return false;
    }
    for (c = 0; c < n_channels; c++) {
        if (!isfinite(noise_floors[c]) || noise_floors[c] <= 0.0) {
            return false;
        }
    }

    memset(ctx, 0, sizeof(*ctx));
    ctx->initialized = true;
    ctx->n_channels = n_channels;
    ctx->variant = variant;
    ctx->params = p;
    for (c = 0; c < n_channels; c++) {
        ctx->noise_floor[c] = noise_floors[c];
    }
    ctx->obs_mode = TAIS_JALC_MODE_QUIET_ECO;
    ctx->fallback_until = -1.0;
    ctx->lead_ch = -1;
    ctx->last_obs_interval = QUIET_INTERVAL_S;
    ctx->last_aoi_cap = p.aoi_cap_quiet_s;
    return true;
}

bool tais_jalc_update(
    tais_jalc_t *ctx,
    double t,
    const double *values,
    const bool *valid_mask,
    const bool *active_mask,
    const int *health_states,
    const uint32_t *health_flags,
    const tais_jalc_telemetry_t *telemetry,
    tais_jalc_decision_t *out
)
{
    int c, i, j, k;
    bool diagnostic = false;
    bool any_eligible = false;
    int best_ch = -1;
    int best_sign = 0;
    double best_risk = 0.0;

    if (ctx == NULL || !ctx->initialized || values == NULL || valid_mask == NULL ||
        active_mask == NULL || health_states == NULL || health_flags == NULL || out == NULL) {
        return false;
    }
    if (!isfinite(t) || t < 0.0) {
        return false;
    }
    if (ctx->has_last_t && t < ctx->last_t + ctx->last_interval - EPS_TIME) {
        return false;
    }

    /* Update rolling fast window using actual past acquisitions */
    if (ctx->has_last_t && (t - ctx->last_t) <= MIN_INTERVAL_S + EPS_TIME) {
        if (ctx->fast_len < TAIS_JALC_FAST_CAP) {
            ctx->fast_times[ctx->fast_len++] = t;
        }
    }
    {
        int write_idx = 0;
        double cutoff = t - FAST_WINDOW_S;
        for (i = 0; i < ctx->fast_len; i++) {
            if (ctx->fast_times[i] > cutoff) {
                ctx->fast_times[write_idx++] = ctx->fast_times[i];
            }
        }
        ctx->fast_len = write_idx;
    }
    if (ctx->fast_len > FAST_LIMIT) {
        return false;
    }

    /* Extract past-only robust median/MAD + Theil-Sen slope/residual features */
    for (c = 0; c < ctx->n_channels; c++) {
        bool finite_v = valid_mask[c] && isfinite(values[c]);
        bool eligible = finite_v && (health_states[c] == TAIS_HEALTH_HEALTHY);
        if (!eligible) {
            ctx->hist_len[c] = 0;
            diagnostic = true;
            continue;
        }

        double v = values[c];
        double nf = ctx->noise_floor[c];
        int hlen = ctx->hist_len[c];
        double center = v;
        double scale = nf;
        double slope = 0.0;
        bool has_pred = false;
        double prediction = 0.0;
        double consistency = 0.0;

        if (hlen > 0) {
            double tmp[TAIS_JALC_WINDOW];
            for (i = 0; i < hlen; i++) {
                tmp[i] = ctx->hist_v[c][i];
            }
            center = median_inplace(tmp, hlen);
            for (i = 0; i < hlen; i++) {
                tmp[i] = fabs(ctx->hist_v[c][i] - center);
            }
            scale = max_d(nf, MAD_MULTIPLIER * median_inplace(tmp, hlen));
        }

        if (hlen >= 3) {
            double slopes[36];
            int n_slopes = 0;
            for (i = 0; i < hlen; i++) {
                for (j = i + 1; j < hlen; j++) {
                    double dt = ctx->hist_t[c][j] - ctx->hist_t[c][i];
                    if (dt > 0.0) {
                        slopes[n_slopes++] = (ctx->hist_v[c][j] - ctx->hist_v[c][i]) / dt;
                    }
                }
            }
            if (n_slopes > 0) {
                double intercepts[TAIS_JALC_WINDOW];
                int nonzero = 0;
                int aligned = 0;
                slope = median_inplace(slopes, n_slopes);
                for (i = 0; i < hlen; i++) {
                    intercepts[i] = ctx->hist_v[c][i] - slope * ctx->hist_t[c][i];
                }
                prediction = median_inplace(intercepts, hlen) + slope * t;
                has_pred = true;
                for (i = 0; i + 1 < hlen; i++) {
                    double diff_adj = ctx->hist_v[c][i + 1] - ctx->hist_v[c][i];
                    if (diff_adj != 0.0) {
                        nonzero++;
                        if (diff_adj * slope > 0.0) {
                            aligned++;
                        }
                    }
                }
                consistency = (nonzero > 0) ? ((double)aligned / (double)nonzero) : 0.0;
            }
        }

        double delta = v - center;
        double z = fabs(delta) / scale;
        double trend = (consistency >= TREND_CONSISTENCY)
                           ? (fabs(slope) * HORIZON_S / (ENTER_Z * scale))
                           : 0.0;
        double residual = has_pred ? (fabs(v - prediction) / (ENTER_Z * scale)) : 0.0;
        double z_norm = z / ENTER_Z;
        double risk = max_d(z_norm, max_d(trend, residual));
        int sign = (delta > 0.0) ? 1 : ((delta < 0.0) ? -1 : 0);
        int risk_sign = (trend >= max_d(residual, z_norm) && trend > 0.0)
                            ? ((slope > 0.0) ? 1 : -1)
                            : sign;

        if (!any_eligible || risk > best_risk) {
            any_eligible = true;
            best_ch = c;
            best_risk = risk;
            best_sign = risk_sign;
        }

        /* Append current sample to bounded channel history */
        if (hlen < TAIS_JALC_WINDOW) {
            ctx->hist_t[c][hlen] = t;
            ctx->hist_v[c][hlen] = v;
            ctx->hist_len[c] = hlen + 1;
        } else {
            for (k = 0; k + 1 < TAIS_JALC_WINDOW; k++) {
                ctx->hist_t[c][k] = ctx->hist_t[c][k + 1];
                ctx->hist_v[c][k] = ctx->hist_v[c][k + 1];
            }
            ctx->hist_t[c][TAIS_JALC_WINDOW - 1] = t;
            ctx->hist_v[c][TAIS_JALC_WINDOW - 1] = v;
        }
    }

    /* Step 4+1 observation FSM */
    double obs_interval = QUIET_INTERVAL_S;
    bool fast_blocked = false;
    bool handled = false;

    if (ctx->obs_mode == TAIS_JALC_MODE_SAFE_FALLBACK) {
        if (t < ctx->fallback_until) {
            obs_interval = diagnostic
                               ? min_d(ctx->params.fallback_interval_s, ctx->params.diag_interval_s)
                               : ctx->params.fallback_interval_s;
            handled = true;
        } else {
            ctx->obs_mode = TAIS_JALC_MODE_QUIET_ECO;
        }
    }

    if (!handled) {
        if (ctx->has_burst) {
            bool lead_same = any_eligible && (best_ch == ctx->lead_ch) && (best_sign == ctx->lead_sign);
            if ((t - ctx->burst_start) >= MAX_BURST_S || best_risk < RISK_EXIT || !lead_same) {
                obs_interval = enter_fallback(ctx, t);
            } else if (count_fast_at_due(ctx, t + MIN_INTERVAL_S) >= FAST_LIMIT) {
                obs_interval = enter_fallback(ctx, t);
                fast_blocked = true;
            } else {
                ctx->confirmed++;
                ctx->obs_mode = (ctx->confirmed >= CONFIRM_SAMPLES)
                                    ? TAIS_JALC_MODE_TRACK
                                    : TAIS_JALC_MODE_PROBE;
                obs_interval = MIN_INTERVAL_S;
            }
        } else if (best_risk >= RISK_ENTER) {
            if (count_fast_at_due(ctx, t + MIN_INTERVAL_S) >= FAST_LIMIT) {
                obs_interval = enter_fallback(ctx, t);
                fast_blocked = true;
            } else {
                ctx->has_burst = true;
                ctx->burst_start = t;
                ctx->confirmed = 1;
                ctx->lead_ch = best_ch;
                ctx->lead_sign = best_sign;
                ctx->obs_mode = TAIS_JALC_MODE_PROBE;
                obs_interval = MIN_INTERVAL_S;
            }
        } else if (best_risk >= RISK_EXIT) {
            ctx->obs_mode = TAIS_JALC_MODE_PROBE;
            obs_interval = min_d(ctx->params.diag_interval_s, ctx->params.fallback_interval_s);
        } else if (diagnostic) {
            ctx->obs_mode = TAIS_JALC_MODE_DIAG_VERIFY;
            obs_interval = ctx->params.diag_interval_s;
        } else {
            ctx->obs_mode = TAIS_JALC_MODE_QUIET_ECO;
            obs_interval = QUIET_INTERVAL_S;
        }
    }

    if (diagnostic) {
        obs_interval = min_d(obs_interval, ctx->params.diag_interval_s);
    }
    obs_interval = clamp_d(obs_interval, MIN_INTERVAL_S, MAX_INTERVAL_S);

    /* Dynamic AoI cap and weak-link safety margin */
    bool any_active = false;
    for (c = 0; c < ctx->n_channels; c++) {
        if (active_mask[c]) {
            any_active = true;
        }
    }
    bool is_active = (ctx->obs_mode == TAIS_JALC_MODE_PROBE ||
                      ctx->obs_mode == TAIS_JALC_MODE_TRACK ||
                      any_active);
    double aoi_cap_s = is_active ? ctx->params.aoi_cap_active_s : ctx->params.aoi_cap_quiet_s;

    bool has_telem = (telemetry != NULL && telemetry->present);
    bool is_lossy = (ctx->variant == TAIS_JALC_VARIANT_FULL &&
                     has_telem &&
                     telemetry->loss_ema >= ctx->params.loss_redundancy_threshold);
    double delta_margin_s = is_lossy ? MIN_INTERVAL_S : 0.0;

    bool can_fast_now = count_fast_at_due(ctx, t + MIN_INTERVAL_S) < FAST_LIMIT;
    double min_next_gap_s = can_fast_now ? MIN_INTERVAL_S : (MIN_INTERVAL_S + 1.0);

    /* Effective receiver finite timestamps */
    bool rx_has_finite[TAIS_JALC_MAX_CHANNELS];
    double rx_finite_t[TAIS_JALC_MAX_CHANNELS];
    for (c = 0; c < ctx->n_channels; c++) {
        if (ctx->variant == TAIS_JALC_VARIANT_FULL && has_telem) {
            rx_has_finite[c] = telemetry->has_confirmed_finite[c];
            rx_finite_t[c] = telemetry->last_confirmed_finite_t[c];
        } else {
            rx_has_finite[c] = ctx->has_last_sent_finite[c];
            rx_finite_t[c] = ctx->last_sent_finite_t[c];
        }
    }

    /* Build current snapshot */
    tais_jalc_snapshot_t now_snap;
    memset(&now_snap, 0, sizeof(now_snap));
    now_snap.has_snapshot = true;
    for (c = 0; c < ctx->n_channels; c++) {
        bool fin = valid_mask[c] && isfinite(values[c]);
        now_snap.valid[c] = fin;
        now_snap.value[c] = fin ? values[c] : 0.0;
        now_snap.active[c] = active_mask[c];
        now_snap.health_state[c] = health_states[c];
        now_snap.health_flags[c] = health_flags[c];
    }

    /* Upload decision */
    uint32_t crit_mask = 0u;
    uint32_t routine_mask = 0u;
    uint32_t reason_mask = 0u;
    int redundancy_k = 1;

    if (ctx->variant == TAIS_JALC_VARIANT_OBS_ONLY) {
        if (!ctx->last_sent.has_snapshot) {
            reason_mask |= TAIS_REASON_FIRST;
        } else {
            for (c = 0; c < ctx->n_channels; c++) {
                if (now_snap.valid[c] != ctx->last_sent.valid[c]) {
                    reason_mask |= TAIS_REASON_VALIDITY;
                } else if (now_snap.valid[c] &&
                           fabs(now_snap.value[c] - ctx->last_sent.value[c]) >=
                               DEADBAND_MULT * ctx->noise_floor[c]) {
                    reason_mask |= TAIS_REASON_DEADBAND;
                }
                if (now_snap.active[c] != ctx->last_sent.active[c]) {
                    reason_mask |= TAIS_REASON_EVENT_EDGE;
                }
                if (now_snap.health_state[c] != ctx->last_sent.health_state[c] ||
                    now_snap.health_flags[c] != ctx->last_sent.health_flags[c]) {
                    reason_mask |= TAIS_REASON_HEALTH_EDGE;
                }
            }
            if (ctx->has_last_upload_t && (t - ctx->last_upload_t) >= LEGACY_HEARTBEAT_S) {
                reason_mask |= TAIS_REASON_HEARTBEAT;
            }
        }
        if (reason_mask != 0u) {
            ctx->last_sent = now_snap;
            ctx->has_last_upload_t = true;
            ctx->last_upload_t = t;
            for (c = 0; c < ctx->n_channels; c++) {
                if (now_snap.valid[c]) {
                    ctx->has_last_sent_finite[c] = true;
                    ctx->last_sent_finite_t[c] = t;
                }
            }
        }
    } else {
        if (!ctx->last_sent.has_snapshot) {
            crit_mask |= TAIS_REASON_FIRST;
        } else {
            for (c = 0; c < ctx->n_channels; c++) {
                if (now_snap.valid[c] != ctx->last_sent.valid[c]) {
                    crit_mask |= TAIS_REASON_VALIDITY;
                } else if (now_snap.valid[c] &&
                           fabs(now_snap.value[c] - ctx->last_sent.value[c]) >=
                               DEADBAND_MULT * ctx->noise_floor[c]) {
                    routine_mask |= TAIS_REASON_DEADBAND;
                }
                if (now_snap.active[c] != ctx->last_sent.active[c]) {
                    crit_mask |= TAIS_REASON_EVENT_EDGE;
                }
                if (now_snap.health_state[c] != ctx->last_sent.health_state[c] ||
                    now_snap.health_flags[c] != ctx->last_sent.health_flags[c]) {
                    crit_mask |= TAIS_REASON_HEALTH_EDGE;
                }
                if (now_snap.valid[c]) {
                    if (!rx_has_finite[c]) {
                        crit_mask |= TAIS_REASON_AOI_CAP;
                    } else {
                        double eff_cap = max_d(MIN_INTERVAL_S, aoi_cap_s - delta_margin_s);
                        double age_now = t - rx_finite_t[c];
                        if (age_now >= eff_cap - EPS_TIME ||
                            (age_now + min_next_gap_s) > eff_cap + EPS_TIME) {
                            crit_mask |= TAIS_REASON_AOI_CAP;
                        }
                    }
                }
            }
        }

        if (ctx->variant == TAIS_JALC_VARIANT_FULL && has_telem && telemetry->bw_congested) {
            reason_mask = crit_mask;
        } else {
            reason_mask = crit_mask | routine_mask;
        }

        if (ctx->variant == TAIS_JALC_VARIANT_FULL &&
            has_telem &&
            telemetry->loss_ema >= ctx->params.loss_redundancy_threshold &&
            (reason_mask & (TAIS_REASON_EVENT_EDGE | TAIS_REASON_HEALTH_EDGE)) != 0u) {
            if (telemetry->bw_tokens_bytes >= 2.0 * TAIS_JALC_MAX_FRAME_BYTES) {
                redundancy_k = 2;
            }
        }

        if (reason_mask != 0u) {
            if (ctx->variant == TAIS_JALC_VARIANT_FULL && has_telem) {
                ctx->pending = now_snap;
            } else {
                ctx->last_sent = now_snap;
                ctx->has_last_upload_t = true;
                ctx->last_upload_t = t;
                for (c = 0; c < ctx->n_channels; c++) {
                    if (now_snap.valid[c]) {
                        ctx->has_last_sent_finite[c] = true;
                        ctx->last_sent_finite_t[c] = t;
                    }
                }
            }
        }
    }

    bool upload = (reason_mask != 0u);

    /* AoI-Sampling hard reservation */
    double t_next = t + obs_interval;
    if (ctx->variant == TAIS_JALC_VARIANT_AOI || ctx->variant == TAIS_JALC_VARIANT_FULL) {
        bool has_oldest = false;
        double oldest_t = 0.0;
        for (c = 0; c < ctx->n_channels; c++) {
            if (!now_snap.valid[c]) {
                continue;
            }
            bool ref_ok = false;
            double ref_t = 0.0;
            if (upload) {
                ref_ok = true;
                ref_t = t;
            } else if (rx_has_finite[c]) {
                ref_ok = true;
                ref_t = rx_finite_t[c];
            }
            if (ref_ok && (!has_oldest || ref_t < oldest_t)) {
                has_oldest = true;
                oldest_t = ref_t;
            }
        }
        if (has_oldest) {
            double t_aoi_due = oldest_t + aoi_cap_s - delta_margin_s;
            t_next = min_d(t + obs_interval, max_d(t + min_next_gap_s, t_aoi_due));
        }
    }

    double min_bound = can_fast_now ? MIN_INTERVAL_S : min_next_gap_s;
    double interval = clamp_d(t_next - t, min_bound, MAX_INTERVAL_S);
    t_next = t + interval;

    ctx->has_last_t = true;
    ctx->last_t = t;
    ctx->last_interval = interval;
    ctx->last_obs_interval = obs_interval;
    ctx->last_aoi_cap = aoi_cap_s;
    ctx->last_delta_margin = delta_margin_s;
    for (c = 0; c < ctx->n_channels; c++) {
        ctx->last_valid[c] = now_snap.valid[c];
    }

    out->t = t;
    out->obs_mode = ctx->obs_mode;
    out->obs_interval_s = obs_interval;
    out->next_sample_s = t_next;
    out->interval_s = interval;
    out->aoi_cap_s = aoi_cap_s;
    out->delta_margin_s = delta_margin_s;
    out->upload = upload;
    out->reason_mask = reason_mask;
    out->redundancy_k = redundancy_k;
    out->score = best_risk;
    out->fast_used = ctx->fast_len;
    out->fast_blocked = fast_blocked;
    out->diagnostic = diagnostic;
    return true;
}

double tais_jalc_on_tx_result(
    tais_jalc_t *ctx,
    double t,
    bool delivered,
    const tais_jalc_telemetry_t *telemetry
)
{
    int c;
    if (ctx == NULL || !ctx->initialized) {
        return t + QUIET_INTERVAL_S;
    }
    if (ctx->variant != TAIS_JALC_VARIANT_FULL) {
        return t + (ctx->has_last_t ? ctx->last_interval : QUIET_INTERVAL_S);
    }
    if (delivered && ctx->pending.has_snapshot) {
        ctx->last_sent = ctx->pending;
        ctx->has_last_upload_t = true;
        ctx->last_upload_t = t;
        for (c = 0; c < ctx->n_channels; c++) {
            if (ctx->pending.valid[c]) {
                ctx->has_last_sent_finite[c] = true;
                ctx->last_sent_finite_t[c] = t;
            }
        }
        ctx->pending.has_snapshot = false;
        return t + ctx->last_interval;
    }

    ctx->pending.has_snapshot = false;
    if (delivered || telemetry == NULL || !telemetry->present) {
        return t + ctx->last_interval;
    }

    double margin = (telemetry->loss_ema >= ctx->params.loss_redundancy_threshold)
                        ? MIN_INTERVAL_S
                        : ctx->last_delta_margin;
    bool any_missing_ref = false;
    bool any_ref = false;
    double oldest_ref = 0.0;
    for (c = 0; c < ctx->n_channels; c++) {
        if (!ctx->last_valid[c]) {
            continue;
        }
        if (!telemetry->has_confirmed_finite[c]) {
            any_missing_ref = true;
        } else {
            double rt = telemetry->last_confirmed_finite_t[c];
            if (!any_ref || rt < oldest_ref) {
                any_ref = true;
                oldest_ref = rt;
            }
        }
    }

    double desired;
    if (any_missing_ref) {
        desired = t + MIN_INTERVAL_S;
    } else if (any_ref) {
        desired = oldest_ref + ctx->last_aoi_cap - margin;
    } else {
        desired = t + ctx->last_obs_interval;
    }

    double t_next = min_d(t + ctx->last_obs_interval, max_d(t + MIN_INTERVAL_S, desired));
    double interval = clamp_d(t_next - t, MIN_INTERVAL_S, MAX_INTERVAL_S);
    if (interval <= MIN_INTERVAL_S + EPS_TIME) {
        int used = count_fast_at_due(ctx, t + MIN_INTERVAL_S);
        if (used >= FAST_LIMIT || telemetry->bw_congested) {
            interval = min_d(ctx->last_obs_interval, ctx->params.fallback_interval_s);
            interval = max_d(MIN_INTERVAL_S, interval);
        }
    }
    ctx->last_interval = interval;
    return t + interval;
}

size_t tais_jalc_sizeof_ctx(void)
{
    return sizeof(tais_jalc_t);
}

size_t tais_jalc_sizeof_params(void)
{
    return sizeof(tais_jalc_params_t);
}

size_t tais_jalc_sizeof_decision(void)
{
    return sizeof(tais_jalc_decision_t);
}
