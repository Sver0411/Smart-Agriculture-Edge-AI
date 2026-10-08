#pragma once
#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>
/* Prototype assumes a commissioned E220-900T22D-compatible transparent UART.
 * Register readback is mandatory. No AUX event is a receiver/durable ACK. */
esp_err_t b1_e220_init(void);
esp_err_t b1_e220_send(const uint8_t *, size_t, uint32_t);
int b1_e220_receive(uint8_t *, size_t, uint32_t);
esp_err_t b1_e220_shutdown(uint32_t);
