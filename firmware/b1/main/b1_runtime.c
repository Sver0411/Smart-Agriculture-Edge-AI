#include "b1.h"
#include "sdkconfig.h"
#include "esp_pm.h"
#include "esp_log.h"

void b1_runtime_init(void)
{
#if CONFIG_B1_LIGHT_SLEEP
    // IDF's automatic light sleep retains RAM and cooperates with both tasks.
    // Never deep-sleep/reset policy state between measurements.
    esp_pm_config_t pm = {.max_freq_mhz = 160, .min_freq_mhz = 40,
                          .light_sleep_enable = true};
    ESP_ERROR_CHECK(esp_pm_configure(&pm));
    ESP_LOGI("B1", "automatic light sleep enabled; current consumption unmeasured");
#endif
}
