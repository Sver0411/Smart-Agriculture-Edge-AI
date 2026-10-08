#include "b1.h"
#include "b1_storage.h"
#include "nvs.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "freertos/semphr.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static nvs_handle_t handle;
static SemaphoreHandle_t mutex;

void b1_storage_lock(void) { xSemaphoreTake(mutex, portMAX_DELAY); }
void b1_storage_unlock(void) { xSemaphoreGive(mutex); }

bool b1_storage_save(void *context, unsigned slot, const b1_record_t *record)
{
    (void)context;
    char key[8]; snprintf(key, sizeof(key), "q%02u", slot);
    esp_err_t err;
    if (record) {
        size_t size = offsetof(b1_record_t, wire) + strlen(record->wire) + 1;
        err = nvs_set_blob(handle, key, record, size);
    } else {
        err = nvs_erase_key(handle, key);
        if (err == ESP_ERR_NVS_NOT_FOUND) return true;
    }
    if (err == ESP_OK) err = nvs_commit(handle);
    if (err != ESP_OK)
        printf("B1_DELIVERY {\"event\":\"STORAGE_FAILURE\",\"slot\":%u,\"code\":%d}\n", slot, err);
    return err == ESP_OK;
}

bool b1_storage_init(b1_outbox_t *q)
{
    mutex = xSemaphoreCreateMutex();
    if (!mutex || nvs_open("b1_delivery", NVS_READWRITE, &handle) != ESP_OK) return false;
    b1_outbox_init(q, b1_storage_save, NULL);
    static b1_record_t record;
    for (unsigned slot = 0; slot < B1_OUTBOX_CAPACITY; slot++) {
        char key[8]; snprintf(key, sizeof(key), "q%02u", slot);
        size_t size = sizeof(record);
        memset(&record, 0, sizeof(record));
        esp_err_t err = nvs_get_blob(handle, key, &record, &size);
        if (err == ESP_ERR_NVS_NOT_FOUND) continue;
        if (err != ESP_OK || size <= offsetof(b1_record_t, wire) ||
            size > sizeof(record) || !b1_outbox_restore(q, slot, &record)) {
            printf("B1_DELIVERY {\"event\":\"CORRUPT_OR_INCOMPATIBLE_CHECKPOINT\",\"slot\":%u}\n", slot);
            return false; /* preserve evidence; never auto-erase */
        }
    }
    return true;
}

void b1_new_boot_identity(void)
{
    uint64_t count = 0;
    esp_err_t err = nvs_get_u64(handle, "boot_counter", &count);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) abort();
    if (count == UINT64_MAX) abort();
    ESP_ERROR_CHECK(nvs_set_u64(handle, "boot_counter", ++count));
    ESP_ERROR_CHECK(nvs_commit(handle));
    uint8_t mac[6]; ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    /* Device MAC + committed boot counter + 128 random bits. Counter alone
     * cannot disambiguate an externally erased/factory-replaced NVS. */
    snprintf(b1_boot_id, B1_BOOT_ID_SIZE,
        "%02x%02x%02x%02x%02x%02x-%016llx-%08lx%08lx%08lx%08lx",
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], (unsigned long long)count,
        (unsigned long)esp_random(), (unsigned long)esp_random(),
        (unsigned long)esp_random(), (unsigned long)esp_random());
}
