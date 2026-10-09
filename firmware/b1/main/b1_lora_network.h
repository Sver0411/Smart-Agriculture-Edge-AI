#pragma once
#include <stdbool.h>
#include <stdint.h>
void b1_lora_network_task(void *);
bool b1_lora_run_window(uint32_t);
uint32_t b1_lora_generation(void);
const char *b1_lora_owner(void);
void b1_lora_restore_owner(uint32_t, const char *);

void b1_lora_notify_pending(void);
