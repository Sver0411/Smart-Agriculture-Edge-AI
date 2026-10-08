#include "b1.h"

bool b1_queue_sample(const b1_sample_t *sample)
{
    if (!sample->upload_requested) return false;
    if (xQueueSend(b1_queue, sample, 0) == pdTRUE) return true;
    b1_sample_t discarded;
    if (xQueueReceive(b1_queue, &discarded, 0) == pdTRUE) b1_stats.local_queue_drops++;
    if (xQueueSend(b1_queue, sample, 0) == pdTRUE) return true;
    b1_stats.local_queue_drops++;
    return false;
}
