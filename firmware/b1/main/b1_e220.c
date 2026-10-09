#include "b1_e220.h"
#include "agri_lora.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include <stdio.h>
#include <string.h>
#define PORT UART_NUM_1
static bool installed;
static al_stream_t stream;
static uint64_t last_byte_ms;
static uint64_t clock_ms(void) {
  return (uint64_t)(esp_timer_get_time() / 1000);
}
static TickType_t ticks(uint32_t ms) {
  TickType_t t = pdMS_TO_TICKS(ms);
  return t ? t : 1;
}
static esp_err_t ready(uint64_t deadline) {
  while (!gpio_get_level(CONFIG_B1_E220_AUX_GPIO)) {
    if (clock_ms() >= deadline)
      return ESP_ERR_TIMEOUT;
    vTaskDelay(1);
  }
  /* Mode completion needs settling after AUX high; schedule >=2 ms. */
  vTaskDelay(ticks(2));
  return clock_ms() <= deadline ? ESP_OK : ESP_ERR_TIMEOUT;
}
static esp_err_t mode(unsigned m, uint64_t deadline) {
  esp_err_t e = ready(deadline);
  if (e != ESP_OK)
    return e;
  if ((e = gpio_set_level(CONFIG_B1_E220_M0_GPIO, m & 1u)) != ESP_OK)
    return e;
  if ((e = gpio_set_level(CONFIG_B1_E220_M1_GPIO, (m >> 1) & 1u)) != ESP_OK)
    return e;
  vTaskDelay(ticks(2));
  return ready(deadline);
}
static int hex(char c) {
  return c >= '0' && c <= '9'   ? c - '0'
         : c >= 'a' && c <= 'f' ? c - 'a' + 10
         : c >= 'A' && c <= 'F' ? c - 'A' + 10
                                : -1;
}
esp_err_t b1_e220_init(void) {
  const int pins[] = {CONFIG_B1_E220_TX_GPIO, CONFIG_B1_E220_RX_GPIO,
                      CONFIG_B1_E220_M0_GPIO, CONFIG_B1_E220_M1_GPIO,
                      CONFIG_B1_E220_AUX_GPIO};
  for (unsigned i = 0; i < 5; ++i) {
    if (!GPIO_IS_VALID_GPIO(pins[i]))
      return ESP_ERR_INVALID_ARG;
    for (unsigned j = 0; j < i; ++j)
      if (pins[i] == pins[j])
        return ESP_ERR_INVALID_ARG;
  }
  if (!GPIO_IS_VALID_OUTPUT_GPIO(pins[0]) ||
      !GPIO_IS_VALID_OUTPUT_GPIO(pins[2]) ||
      !GPIO_IS_VALID_OUTPUT_GPIO(pins[3]))
    return ESP_ERR_INVALID_ARG;
  const char *cfg = CONFIG_B1_E220_EXPECTED_REGISTERS;
  uint8_t expected[8];
  if (strlen(cfg) != 16)
    return ESP_ERR_INVALID_ARG;
  for (unsigned i = 0; i < 8; ++i) {
    int hi = hex(cfg[2 * i]), lo = hex(cfg[2 * i + 1]);
    if (hi < 0 || lo < 0)
      return ESP_ERR_INVALID_ARG;
    expected[i] = (uint8_t)(hi * 16 + lo);
  }
  if (installed)
    return ESP_ERR_INVALID_STATE;
  gpio_config_t outs = {.pin_bit_mask =
                            (UINT64_C(1) << pins[2]) | (UINT64_C(1) << pins[3]),
                        .mode = GPIO_MODE_OUTPUT};
  gpio_config_t aux = {.pin_bit_mask = UINT64_C(1) << pins[4],
                       .mode = GPIO_MODE_INPUT};
  esp_err_t e = gpio_config(&outs);
  if (e != ESP_OK)
    return e;
  if ((e = gpio_config(&aux)) != ESP_OK)
    return e;
  gpio_set_level(pins[2], 1);
  gpio_set_level(pins[3], 1);
  uart_config_t u = {.baud_rate = CONFIG_B1_E220_UART_BAUD,
                     .data_bits = UART_DATA_8_BITS,
                     .parity = UART_PARITY_DISABLE,
                     .stop_bits = UART_STOP_BITS_1,
                     .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
                     .source_clk = UART_SCLK_DEFAULT};
  if ((e = uart_param_config(PORT, &u)) != ESP_OK)
    return e;
  if ((e = uart_set_pin(PORT, pins[0], pins[1], UART_PIN_NO_CHANGE,
                        UART_PIN_NO_CHANGE)) != ESP_OK)
    return e;
  if ((e = uart_driver_install(PORT, 1024, 0, 0, NULL, 0)) != ESP_OK)
    return e;
  installed = true;
  memset(&stream, 0, sizeof(stream));
  uint64_t deadline = clock_ms() + CONFIG_B1_E220_AUX_TIMEOUT_MS;
  if ((e = mode(3, deadline)) != ESP_OK)
    goto fail;
  uart_flush_input(PORT);
  const uint8_t request[] = {0xc1, 0, 8};
  uint8_t reply[11];
  size_t got = 0;
  if (uart_write_bytes(PORT, request, sizeof(request)) != sizeof(request)) {
    e = ESP_FAIL;
    goto fail;
  }
  while (got < sizeof(reply) && clock_ms() < deadline) {
    int n = uart_read_bytes(PORT, reply + got, sizeof(reply) - got, ticks(20));
    if (n < 0) {
      e = ESP_FAIL;
      goto fail;
    }
    got += (size_t)n;
  }
  if (got != 11 || reply[0] != 0xc1 || reply[1] != 0 || reply[2] != 8 ||
      memcmp(reply + 3, expected, 8)) {
    e = ESP_ERR_INVALID_RESPONSE;
    goto fail;
  }
  /* Caller commissions baud, transparent mode and RSSI-disabled framing.
   * No RF-frequency/power/secret register is guessed or written here. */
  if ((e = mode(0, clock_ms() + CONFIG_B1_E220_AUX_TIMEOUT_MS)) != ESP_OK)
    goto fail;
  printf("B1_RADIO {\"event\":\"REGISTER_READBACK_VERIFIED\",\"mtu\":%d}\n",
         CONFIG_B1_E220_FRAME_MTU);
  return ESP_OK;
fail:
  uart_driver_delete(PORT);
  installed = false;
  return e;
}
esp_err_t b1_e220_send(const uint8_t *p, size_t n, uint32_t timeout) {
  if (!installed || !p || !n || n > CONFIG_B1_E220_FRAME_MTU)
    return ESP_ERR_INVALID_ARG;
  uint64_t deadline = clock_ms() + timeout;
  esp_err_t e = ready(deadline);
  if (e != ESP_OK)
    return e;
  if (uart_write_bytes(PORT, p, n) != (int)n)
    return ESP_FAIL;
  uint64_t now = clock_ms();
  if (now >= deadline)
    return ESP_ERR_TIMEOUT;
  e = uart_wait_tx_done(PORT, ticks((uint32_t)(deadline - now)));
  if (e != ESP_OK)
    return e;
  return ready(
      deadline); /* UART/module submission only, not remote delivery. */
}
int b1_e220_receive(uint8_t *out, size_t cap, uint32_t timeout) {
  if (!installed)
    return -1;
  uint64_t deadline = clock_ms() + timeout;
  while (clock_ms() < deadline) {
    uint32_t idle = (AL_MAX_FRAME * 10000u + CONFIG_B1_E220_UART_BAUD - 1u) / CONFIG_B1_E220_UART_BAUD + 500u;
    if (al_stream_expire(&stream,last_byte_ms,clock_ms(),idle))
      printf("B1_RADIO {\"event\":\"PARTIAL_FRAME_IDLE_TIMEOUT\"}\n");
    uint8_t byte;
    int n = uart_read_bytes(PORT, &byte, 1, ticks(10));
    if (n < 0)
      return -1;
    if (!n)
      continue;
    last_byte_ms=clock_ms();
    size_t length = 0;
    int rc = al_stream_byte(&stream, byte, out, cap, &length);
    if (rc < 0)
      return -1;
    if (rc > 0)
      return (int)length;
  }
  return 0;
}
esp_err_t b1_e220_shutdown(uint32_t timeout) {
  if (!installed)
    return ESP_OK;
  esp_err_t e = mode(3, clock_ms() + timeout);
  uart_driver_delete(PORT);
  installed = false;
  stream.used = 0;
  return e;
}
