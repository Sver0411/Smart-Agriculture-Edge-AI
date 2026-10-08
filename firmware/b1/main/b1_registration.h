#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "cJSON.h"
typedef enum { B1_REG_ACCEPTED, B1_REG_NOT_OWNER, B1_REG_STALE_GENERATION,
    B1_REG_INVALID_REPLY, B1_REG_TIMEOUT, B1_REG_TRANSPORT_FAILURE } b1_registration_result_t;
typedef struct { uint32_t generation; char owner[3]; bool confirmed; } b1_registration_t;
/* Socket endpoint association is a LAB trust boundary, not cryptographic authentication. */
b1_registration_result_t b1_registration_reply(b1_registration_t *, const cJSON *, const char *);
