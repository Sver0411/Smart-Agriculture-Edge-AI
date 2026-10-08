#pragma once
#include "b1_outbox.h"
/* Firmware NVS+mutex backend; host harness supplies fault-injectable callbacks. */
bool b1_storage_init(b1_outbox_t *q);
bool b1_storage_save(void *context, unsigned slot, const b1_record_t *record);
void b1_storage_lock(void);
void b1_storage_unlock(void);
void b1_new_boot_identity(void);
