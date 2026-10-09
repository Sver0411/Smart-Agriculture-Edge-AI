#include "b1.h"
#include "b1_storage.h"
#include "b1_store_backend.h"
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

static b1_store_result_t result(esp_err_t err) {
    if(err==ESP_OK)return B1_STORE_OK;
    if(err==ESP_ERR_NVS_NOT_FOUND)return B1_STORE_MISSING;
    printf("B1_DELIVERY {\"event\":\"STORAGE_FAILURE\",\"code\":%d}\n",err);
    return B1_STORE_ERROR;
}
static void key_for(unsigned slot,char key[8]) { snprintf(key,8,"q%02u",slot); }
static b1_store_result_t read_blob(void *ctx,unsigned slot,unsigned char *p,size_t *n) {
    (void)ctx;char key[8];key_for(slot,key);return result(nvs_get_blob(handle,key,p,n));
}
static b1_store_result_t write_blob(void *ctx,unsigned slot,const unsigned char *p,size_t n) {
    (void)ctx;char key[8];key_for(slot,key);return result(nvs_set_blob(handle,key,p,n));
}
static b1_store_result_t remove_blob(void *ctx,unsigned slot) {
    (void)ctx;char key[8];key_for(slot,key);return result(nvs_erase_key(handle,key));
}
static b1_store_result_t commit_blob(void *ctx) { (void)ctx;return result(nvs_commit(handle)); }
static b1_store_backend_t backend={.read=read_blob,.write=write_blob,.remove=remove_blob,.commit=commit_blob};

bool b1_storage_save(void *context,unsigned slot,const b1_record_t *r) {
    (void)context;return b1_backend_save(&backend,slot,r);
}
bool b1_storage_init(b1_outbox_t *q) {
    mutex=xSemaphoreCreateMutex();
    if(!mutex||nvs_open("b1_delivery",NVS_READWRITE,&handle)!=ESP_OK)return false;
    bool ok=b1_backend_load(&backend,q);
    if(!ok)printf("B1_DELIVERY {\"event\":\"CORRUPT_OR_INCOMPATIBLE_CHECKPOINT\"}\n");
    return ok; /* never erase on corruption or incompatibility */
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

/* Reserve 256 committed boot counters at a time. RTC lease amortizes flash
 * writes; a cold/invalid-RTC boot abandons the unused range before reuse. */
#include "b1_snapshot.h"
bool b1_sleep_boot_identity(b1_sleep_identity_t *id,bool rtc_valid) {
 uint64_t high=0;esp_err_t err=nvs_get_u64(handle,"boot_counter",&high);
 if(err!=ESP_OK && err!=ESP_ERR_NVS_NOT_FOUND)return false;
 bool reserve;uint64_t counter;
 if(!b1_boot_lease_take(id,high,rtc_valid && err==ESP_OK,&reserve,&counter))return false;
 if(reserve && (nvs_set_u64(handle,"boot_counter",id->boot_counter_limit)!=ESP_OK || nvs_commit(handle)!=ESP_OK))return false;
 uint8_t mac[6];
 if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return false;
 snprintf(b1_boot_id,B1_BOOT_ID_SIZE,"%02x%02x%02x%02x%02x%02x-%016llx-%08lx%08lx%08lx%08lx",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5],(unsigned long long)counter,(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());return true;
}
