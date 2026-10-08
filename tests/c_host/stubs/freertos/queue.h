#pragma once
#include <stddef.h>
typedef void *QueueHandle_t;
int xQueueSend(QueueHandle_t queue, const void *item, unsigned ticks);
int xQueueReceive(QueueHandle_t queue, void *item, unsigned ticks);
