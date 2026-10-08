#include "b1.h"
#include "esp_log.h"
#include "b1_storage.h"
#include "esp_system.h"
#if CONFIG_SPIRAM
#include "esp_psram.h"
#endif
#include "nvs_flash.h"
#include <stdio.h>

b1_stats_t b1_stats;
char b1_boot_id[B1_BOOT_ID_SIZE];

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    // Never erase NVS on error: it can contain unacknowledged critical data.
    if (err != ESP_OK || !b1_queue_init()) {
        printf("B1_DELIVERY {\"event\":\"STORAGE_INIT_FAILED_PRESERVED\"}\n");
        return;
    }
    b1_new_boot_identity();
    b1_runtime_init();
    size_t psram_runtime = 0;
#if CONFIG_SPIRAM
    psram_runtime = esp_psram_get_size();
#endif
    printf("B1_BEGIN {\"boot_id\":\"%s\",\"queue_capacity\":16,\"heap_after_boot\":%lu,\"psram_runtime_bytes\":%lu}\n",
        b1_boot_id, (unsigned long)esp_get_free_heap_size(), (unsigned long)psram_runtime);
    xTaskCreate(b1_sensor_task, "b1_sensor", 12288, NULL, 5, NULL);
    xTaskCreate(b1_network_task, "b1_network", 16384, NULL, 5, NULL);
}
