#include "b1.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_system.h"
#if CONFIG_SPIRAM
#include "esp_psram.h"
#endif
#include "nvs_flash.h"
#include <stdio.h>

QueueHandle_t b1_queue;
b1_stats_t b1_stats;
char b1_boot_id[16];

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    snprintf(b1_boot_id, sizeof(b1_boot_id), "%08lx", (unsigned long)esp_random());
    b1_queue = xQueueCreate(16, sizeof(b1_sample_t));
    if (!b1_queue) abort();
    size_t psram_runtime = 0;
#if CONFIG_SPIRAM
    psram_runtime = esp_psram_get_size();
#endif
    printf("B1_BEGIN {\"boot_id\":\"%s\",\"queue_capacity\":16,\"heap_after_boot\":%lu,\"psram_runtime_bytes\":%lu}\n",
        b1_boot_id, (unsigned long)esp_get_free_heap_size(), (unsigned long)psram_runtime);
    xTaskCreate(b1_sensor_task, "b1_sensor", 6144, NULL, 5, NULL);
    xTaskCreate(b1_network_task, "b1_network", 8192, NULL, 5, NULL);
}
