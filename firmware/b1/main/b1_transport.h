#pragma once
#include "b1_types.h"
#include "cJSON.h"

// Development Wi-Fi/TCP sink today; E220 sink is planned, not hardware validated.
// send consumes payload on both success and failure. Business policy knows no socket.
typedef struct {
    void *context;
    bool (*send)(void *context, const char *type, cJSON *payload);
} b1_transport_t;
bool b1_transmit_sample(const b1_transport_t *transport, const b1_sample_t *sample);

cJSON *b1_envelope(const char *type, const char *target, cJSON *payload, double uptime_s);
