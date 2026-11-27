/*
 * TAIS Phase 5 - Lean 3D Joint Adaptive Closed-Loop Controller (TAIS-JALC).
 *
 * Pure C11: zero dynamic allocation, zero RTOS/OS dependencies, fixed O(1)
 * memory footprint, deterministic bit-parity with Python JointAdaptiveController.
 */
#ifndef TAIS_JALC_H
#define TAIS_JALC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TAIS_JALC_MAX_CHANNELS 4
#define TAIS_JALC_WINDOW 9
#define TAIS_JALC_FAST_CAP 8
#define TAIS_JALC_MAX_FRAME_BYTES 56.0

/* Variants matching Python JointAdaptiveController */
typedef enum {
    TAIS_JALC_VARIANT_OBS_ONLY = 0,
    TAIS_JALC_VARIANT_AOI = 1,
    TAIS_JALC_VARIANT_FULL = 2
} tais_jalc_variant_t;

/* 4+1 observation state machine */
typedef enum {
    TAIS_JALC_MODE_QUIET_ECO = 0,
    TAIS_JALC_MODE_PROBE = 1,
    TAIS_JALC_MODE_TRACK = 2,
    TAIS_JALC_MODE_SAFE_FALLBACK = 3,
    TAIS_JALC_MODE_DIAG_VERIFY = 4
} tais_jalc_mode_t;

/* Mirrors sensor_health_state_t in SensorTrust C11 */
typedef enum {
    TAIS_HEALTH_HEALTHY = 0,
    TAIS_HEALTH_DEGRADED = 1,
    TAIS_HEALTH_FAULT = 2
} tais_health_state_t;

/* Upload reason bitmask */
#define TAIS_REASON_FIRST       (1u << 0)
#define TAIS_REASON_VALIDITY    (1u << 1)
#define TAIS_REASON_DEADBAND    (1u << 2)
#define TAIS_REASON_EVENT_EDGE  (1u << 3)
#define TAIS_REASON_HEALTH_EDGE (1u << 4)
#define TAIS_REASON_AOI_CAP     (1u << 5)
#define TAIS_REASON_HEARTBEAT   (1u << 6)

/* Exactly 5 primary control hyperparameters */
typedef struct {
    double fallback_interval_s;
    double diag_interval_s;
    double aoi_cap_quiet_s;
    double aoi_cap_active_s;
    double loss_redundancy_threshold;
} tais_jalc_params_t;

/* Strictly causal link telemetry input */
typedef struct {
    bool present;
    double loss_ema;
    bool bw_congested;
    double bw_tokens_bytes;
    bool has_confirmed_finite[TAIS_JALC_MAX_CHANNELS];
    double last_confirmed_finite_t[TAIS_JALC_MAX_CHANNELS];
} tais_jalc_telemetry_t;

/* Per-channel sample snapshot */
typedef struct {
    bool has_snapshot;
    bool valid[TAIS_JALC_MAX_CHANNELS];
    double value[TAIS_JALC_MAX_CHANNELS];
    bool active[TAIS_JALC_MAX_CHANNELS];
    int health_state[TAIS_JALC_MAX_CHANNELS];
    uint32_t health_flags[TAIS_JALC_MAX_CHANNELS];
} tais_jalc_snapshot_t;

/* Output decision */
typedef struct {
    double t;
    tais_jalc_mode_t obs_mode;
    double obs_interval_s;
    double next_sample_s;
    double interval_s;
    double aoi_cap_s;
    double delta_margin_s;
    bool upload;
    uint32_t reason_mask;
    int redundancy_k;
    double score;
    int fast_used;
    bool fast_blocked;
    bool diagnostic;
} tais_jalc_decision_t;

/* Fixed-size controller context (zero heap allocation) */
typedef struct {
    bool initialized;
    int n_channels;
    tais_jalc_variant_t variant;
    tais_jalc_params_t params;
    double noise_floor[TAIS_JALC_MAX_CHANNELS];

    /* Bounded per-channel past healthy histories */
    int hist_len[TAIS_JALC_MAX_CHANNELS];
    double hist_t[TAIS_JALC_MAX_CHANNELS][TAIS_JALC_WINDOW];
    double hist_v[TAIS_JALC_MAX_CHANNELS][TAIS_JALC_WINDOW];

    /* Rolling fast acquisition timestamps (<= 6 in 120s) */
    int fast_len;
    double fast_times[TAIS_JALC_FAST_CAP];

    bool has_last_t;
    double last_t;
    double last_interval;

    /* 4+1 observation FSM */
    tais_jalc_mode_t obs_mode;
    double fallback_until;
    bool has_burst;
    double burst_start;
    int confirmed;
    int lead_ch;
    int lead_sign;

    /* Upload & per-channel finite AoI state */
    tais_jalc_snapshot_t last_sent;
    tais_jalc_snapshot_t pending;
    bool has_last_upload_t;
    double last_upload_t;
    bool has_last_sent_finite[TAIS_JALC_MAX_CHANNELS];
    double last_sent_finite_t[TAIS_JALC_MAX_CHANNELS];

    /* Saved context for causal post-tx ACK/NACK recovery */
    double last_obs_interval;
    double last_aoi_cap;
    double last_delta_margin;
    bool last_valid[TAIS_JALC_MAX_CHANNELS];
} tais_jalc_t;

void tais_jalc_default_params(tais_jalc_params_t *params);

bool tais_jalc_init(
    tais_jalc_t *ctx,
    int n_channels,
    const double *noise_floors,
    const tais_jalc_params_t *params,
    tais_jalc_variant_t variant
);

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
);

double tais_jalc_on_tx_result(
    tais_jalc_t *ctx,
    double t,
    bool delivered,
    const tais_jalc_telemetry_t *telemetry
);

size_t tais_jalc_sizeof_ctx(void);
size_t tais_jalc_sizeof_params(void);
size_t tais_jalc_sizeof_decision(void);

#ifdef __cplusplus
}
#endif

#endif /* TAIS_JALC_H */
