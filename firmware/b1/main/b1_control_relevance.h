#pragma once
#include <math.h>
#include "adaptive_scheduler.h"

// Communication sensitivity, never an actuator decision. B1 has temperature only.
static inline uint32_t b1_temperature_relevance(float previous, float current,
                                                float threshold, float margin)
{
    uint32_t reasons = 0;
    if ((previous > threshold) != (current > threshold)) reasons |= UP_CONTROL_THRESHOLD_CROSSING;
    if (margin > 0 && fabsf(previous-threshold) > margin && fabsf(current-threshold) <= margin)
        reasons |= UP_CONTROL_MARGIN_ENTRY;
    return reasons;
}
