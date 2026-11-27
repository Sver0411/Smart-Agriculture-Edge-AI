#pragma once

#include "tais_jalc.h"

typedef struct {
    tais_jalc_t kernel;
    tais_jalc_telemetry_t link;
} agri_jalc_t;

bool agri_jalc_init(agri_jalc_t *node, int channels, const double *noise);
bool agri_jalc_step(agri_jalc_t *node, double t, const tais_jalc_snapshot_t *sample,
                    tais_jalc_decision_t *decision);
void agri_jalc_confirm(agri_jalc_t *node, double acquired, const tais_jalc_snapshot_t *reported);
void agri_jalc_feedback(agri_jalc_t *node, bool missed_ack);
size_t agri_jalc_size(void);
