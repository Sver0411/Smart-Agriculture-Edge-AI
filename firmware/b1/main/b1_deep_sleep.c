#include "b1_deep_sleep.h"
#include "b1.h"
#include "b1_e220.h"
#include "b1_lora_network.h"
#include "b1_sensor.h"
#include "b1_storage.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs.h"
#include "sdkconfig.h"
#include <stdio.h>
#include <string.h>
static RTC_DATA_ATTR uint8_t snapshot[B1_SNAPSHOT_MAX];
static RTC_DATA_ATTR uint32_t snapshot_length;
static b1_policy_t policy;
static b1_sleep_identity_t identity;
static uint32_t durable_epoch = 1;
static char durable_owner[3] = "A1";
static nvs_handle_t epoch_handle;
static bool epoch_ready;
__attribute__((weak)) bool b1_deep_elapsed(const b1_sleep_identity_t *id,
                                           uint64_t *elapsed, uint64_t *error) {
  (void)id;
  (void)elapsed;
  (void)error;
  return false;
}
bool b1_sleep_epoch_load(uint32_t *generation, char owner[3]) {
  if (nvs_open("b1_sleep", NVS_READWRITE, &epoch_handle) != ESP_OK)
    return false;
  uint8_t bytes[16];
  size_t n = sizeof(bytes);
  esp_err_t err = nvs_get_blob(epoch_handle, "epoch", bytes, &n);
  if (err != ESP_ERR_NVS_NOT_FOUND &&
      (err != ESP_OK || n != sizeof(bytes) ||
       !b1_epoch_decode(bytes, &durable_epoch, durable_owner)))
    return false;
  epoch_ready = true;
  *generation = durable_epoch;
  memcpy(owner, durable_owner, 3);
  return true;
}
bool b1_sleep_epoch_commit(uint32_t generation, const char *owner) {
  if (!epoch_ready || generation < durable_epoch || !owner ||
      (generation == durable_epoch && strcmp(owner, durable_owner)))
    return false;
  if (generation == durable_epoch)
    return true;
  uint8_t bytes[16];
  if (!b1_epoch_encode(generation, owner, bytes) ||
      nvs_set_blob(epoch_handle, "epoch", bytes, sizeof(bytes)) != ESP_OK ||
      nvs_commit(epoch_handle) != ESP_OK) {
    printf("B1_SLEEP {\"event\":\"EPOCH_COMMIT_FAILED\"}\n");
    return false;
  }
  durable_epoch = generation;
  memcpy(durable_owner, owner, 3);
  return true;
}
static uint64_t runtime_ms(void) {
  return (uint64_t)(esp_timer_get_time() / 1000);
}
static void failure_backoff(void) {
  snapshot_length = 0;
  printf("B1_SLEEP {\"event\":\"SLEEP_ABORTED_CONSERVATIVE_BACKOFF\"}\n");
  while (true)
    vTaskDelay(pdMS_TO_TICKS(60000));
}
void b1_deep_sleep_task(void *arg) {
  (void)arg;
  gpio_deep_sleep_hold_dis();
  gpio_hold_dis(CONFIG_B1_E220_M0_GPIO);
  gpio_hold_dis(CONFIG_B1_E220_M1_GPIO);
  esp_sleep_wakeup_cause_t wake = esp_sleep_get_wakeup_cause();
  uint64_t restored_clock = 0, elapsed = 0, error = 0;
  printf("B1_SLEEP {\"event\":\"WAKE\",\"cause\":%d,\"reset_reason\":%d}\n",
         wake, esp_reset_reason());
  char owner[3];
  uint32_t generation;
  if (!b1_policy_init(&policy) || !b1_sleep_epoch_load(&generation, owner))
    failure_backoff();
  identity = (b1_sleep_identity_t){.generation = generation,
                                   .planned_sleep_ms = 60000};
  memcpy(identity.owner, owner, 3);
  b1_restore_result_t restore = B1_RESTORE_REJECTED;
  if (wake == ESP_SLEEP_WAKEUP_TIMER && snapshot_length > 0 &&
      snapshot_length <= sizeof(snapshot)) {
    /* First validate RTC structure before calling any board-specific time hook.
     */
    restore = b1_snapshot_restore(&policy, &identity, snapshot, snapshot_length,
                                  generation, false, 0, &restored_clock);
    if (restore != B1_RESTORE_REJECTED &&
        b1_deep_elapsed(&identity, &elapsed, &error) &&
        error <= CONFIG_B1_DEEP_MAX_CLOCK_ERROR_MS)
      restore =
          b1_snapshot_restore(&policy, &identity, snapshot, snapshot_length,
                              generation, true, elapsed, &restored_clock);
  }
  if (restore == B1_RESTORE_REJECTED) {
    b1_policy_init(&policy);
    identity = (b1_sleep_identity_t){.generation = generation,
                                     .planned_sleep_ms = 60000};
    memcpy(identity.owner, owner, 3);
    restored_clock = 0;
  }
  /* Boot IDs always change across esp_timer reset. Old outbox records retain
   * their original ID and unknown delivery_age; old ACK cannot advance policy.
   */
  if (!b1_sleep_boot_identity(&identity, wake == ESP_SLEEP_WAKEUP_TIMER &&
                                             restore != B1_RESTORE_REJECTED))
    failure_backoff();
  if (!b1_sleep_epoch_commit(identity.generation, identity.owner))
    failure_backoff();
  b1_lora_restore_owner(identity.generation, identity.owner);
  printf("B1_SLEEP "
         "{\"event\":\"RESTORE\",\"result\":%d,\"elapsed_trusted\":%s,\"clock_"
         "error_ms\":%llu,\"generation\":%lu,\"boot_id\":\"%s\"}\n",
         restore, restore == B1_RESTORE_CONTINUOUS ? "true" : "false",
         (unsigned long long)error, (unsigned long)identity.generation,
         b1_boot_id);
  snapshot_length = 0; /* snapshot is not reusable after an abnormal reset */
  uint64_t began = runtime_ms();
  bool sensor_ready = b1_sensor_init();
  b1_sample_t sample = {0};
  if (!b1_sleep_next_sequence(&identity, &sample.seq))
    failure_backoff();
  uint64_t runtime = runtime_ms();
  if (restored_clock > UINT64_MAX - runtime)
    failure_backoff();
  sample.monotonic_ms = restored_clock + runtime;
  sample.valid =
      sensor_ready && b1_sensor_read(&sample.temperature, &sample.humidity);
  b1_policy_update(&policy, &sample);
  b1_stats.sensor_samples++;
  printf("B1_SLEEP "
         "{\"event\":\"SAMPLE\",\"seq\":%lu,\"valid\":%s,\"upload_requested\":%"
         "s,\"mode\":\"%s\"}\n",
         (unsigned long)sample.seq, sample.valid ? "true" : "false",
         sample.upload_requested ? "true" : "false", sample.mode);
  /* Transport age uses current runtime, policy time uses the restored clock. */
  b1_sample_t transport_sample = sample;
  transport_sample.monotonic_ms = runtime;
  if (sample.upload_requested && !b1_queue_sample(&transport_sample))
    printf("B1_SLEEP {\"event\":\"ADMISSION_FAILED_HIGH_PRESERVED\"}\n");
  if (b1_queue_pending_count())
    b1_lora_run_window(CONFIG_B1_DEEP_COMM_WINDOW_MS);
  b1_sample_t confirmed;
  if (b1_queue_take_confirmed(&confirmed)) {
    if (confirmed.monotonic_ms > UINT64_MAX - restored_clock)
      failure_backoff();
    confirmed.monotonic_ms += restored_clock;
    b1_policy_mark_reported(&policy, &confirmed);
  }
  identity.generation = b1_lora_generation();
  memcpy(identity.owner, b1_lora_owner(), 3);
  if (!b1_sleep_epoch_commit(identity.generation, identity.owner))
    failure_backoff();
  if (!b1_sensor_shutdown() ||
      b1_e220_shutdown(CONFIG_B1_E220_AUX_TIMEOUT_MS) != ESP_OK)
    failure_backoff();
  if(!GPIO_IS_VALID_OUTPUT_GPIO(CONFIG_B1_E220_M0_GPIO) || !GPIO_IS_VALID_OUTPUT_GPIO(CONFIG_B1_E220_M1_GPIO))failure_backoff();
  gpio_config_t radio_off = {.pin_bit_mask =
                                 (UINT64_C(1) << CONFIG_B1_E220_M0_GPIO) |
                                 (UINT64_C(1) << CONFIG_B1_E220_M1_GPIO),
                             .mode = GPIO_MODE_OUTPUT};
  if (!GPIO_IS_VALID_OUTPUT_GPIO(CONFIG_B1_E220_M0_GPIO) ||
      !GPIO_IS_VALID_OUTPUT_GPIO(CONFIG_B1_E220_M1_GPIO) ||
      gpio_config(&radio_off) != ESP_OK ||
      gpio_set_level(CONFIG_B1_E220_M0_GPIO, 1) != ESP_OK ||
      gpio_set_level(CONFIG_B1_E220_M1_GPIO, 1) != ESP_OK)
    failure_backoff();
  /* Hold M0/M1 in module mode3 during ESP sleep; verify board voltage/current.
   */
  if (gpio_hold_en(CONFIG_B1_E220_M0_GPIO) != ESP_OK ||
      gpio_hold_en(CONFIG_B1_E220_M1_GPIO) != ESP_OK)
    failure_backoff();
  gpio_deep_sleep_hold_en();
  runtime=runtime_ms();
  if(restored_clock>UINT64_MAX-runtime)failure_backoff();
  identity.saved_ms = restored_clock + runtime;
  identity.planned_sleep_ms = sample.next_interval_ms;
  if (identity.planned_sleep_ms < CONFIG_B1_DEEP_MIN_SLEEP_MS)
    identity.planned_sleep_ms = CONFIG_B1_DEEP_MIN_SLEEP_MS;
  if (identity.planned_sleep_ms > 86400000)
    identity.planned_sleep_ms = 86400000;
  memcpy(identity.previous_boot, b1_boot_id, sizeof(identity.previous_boot));
  size_t length = 0;
  if (!b1_snapshot_encode(&policy, &identity, snapshot, sizeof(snapshot),
                          &length))
    failure_backoff();
  snapshot_length = (uint32_t)length;
  if (esp_sleep_enable_timer_wakeup(identity.planned_sleep_ms * 1000) != ESP_OK)
    failure_backoff();
  printf("B1_SLEEP "
         "{\"event\":\"ENTER\",\"snapshot_bytes\":%u,\"planned_sleep_ms\":%llu,"
         "\"awake_ms\":%llu,\"pending\":%u}\n",
         (unsigned)snapshot_length, (unsigned long long)identity.planned_sleep_ms,
         (unsigned long long)(runtime_ms() - began), b1_queue_pending_count());
  fflush(stdout);
  esp_deep_sleep_start();
}
