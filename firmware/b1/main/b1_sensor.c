#include "b1.h"
#include "b1_sensor.h"
#include "b1_policy.h"
#include "driver/i2c.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "sdkconfig.h"
#include <stdio.h>
#include <math.h>
#include <string.h>

#define SHT30_ADDR 0x44
#define I2C_PORT I2C_NUM_0

static uint8_t crc8(const uint8_t *data)
{
    uint8_t crc = 0xff;
    for (int i = 0; i < 2; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
    return crc;
}

bool b1_sensor_read(float *temperature, float *humidity)
{
    const uint8_t cmd[2] = {0x24, 0x00};
    uint8_t rx[6];
    if (i2c_master_write_to_device(I2C_PORT, SHT30_ADDR, cmd, 2, pdMS_TO_TICKS(100)) != ESP_OK)
        return false;
    vTaskDelay(pdMS_TO_TICKS(20));
    if (i2c_master_read_from_device(I2C_PORT, SHT30_ADDR, rx, 6, pdMS_TO_TICKS(100)) != ESP_OK)
        return false;
    if (crc8(rx) != rx[2] || crc8(rx + 3) != rx[5]) return false;
    uint16_t raw_t = ((uint16_t)rx[0] << 8) | rx[1];
    uint16_t raw_h = ((uint16_t)rx[3] << 8) | rx[4];
    *temperature = -45.0f + 175.0f * raw_t / 65535.0f;
    *humidity = 100.0f * raw_h / 65535.0f;
    return true;
}

static bool sensor_installed;
bool b1_sensor_init(void) {
    i2c_config_t cfg = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = CONFIG_B1_SDA_GPIO,
        .scl_io_num = CONFIG_B1_SCL_GPIO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 100000,
    };
    if(i2c_param_config(I2C_PORT,&cfg)!=ESP_OK)return false;
    if(i2c_driver_install(I2C_PORT,cfg.mode,0,0,0)!=ESP_OK)return false;
    sensor_installed=true;
    // Actual bus probe; previous wiring is never assumed successful.
    i2c_cmd_handle_t command = i2c_cmd_link_create();
    i2c_master_start(command);
    i2c_master_write_byte(command, (SHT30_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_stop(command);
    esp_err_t probe = i2c_master_cmd_begin(I2C_PORT, command, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(command);
    printf("B1_NET {\"event\":\"SHT30_PROBE\",\"address\":68,\"sda\":%d,\"scl\":%d,\"ok\":%s}\n",
        CONFIG_B1_SDA_GPIO, CONFIG_B1_SCL_GPIO, probe == ESP_OK ? "true" : "false");
    return probe==ESP_OK;
}
bool b1_sensor_shutdown(void) {
    if(!sensor_installed)return true;
    if(i2c_driver_delete(I2C_PORT)!=ESP_OK)return false;
    sensor_installed=false;return true;
}
void b1_sensor_task(void *arg) {
    (void)arg;
    b1_sensor_init();
    static b1_policy_t policy;
    if (!b1_policy_init(&policy)) abort();
    uint32_t sequence = 0;
    while (true) {
        b1_sample_t reported;
        if (b1_queue_take_confirmed(&reported)) b1_policy_mark_reported(&policy, &reported);
        b1_sample_t s = {0};
        if (sequence == UINT32_MAX) {
            printf("B1_DELIVERY {\"event\":\"SEQUENCE_EXHAUSTED_REBOOT_REQUIRED\"}\n");
            while (true) vTaskDelay(pdMS_TO_TICKS(10000));
        }
        s.seq = ++sequence;
        s.monotonic_ms = (uint64_t)(esp_timer_get_time() / 1000);
        s.valid = b1_sensor_read(&s.temperature, &s.humidity);
#if CONFIG_B1_TEST_FAULT_INJECTION
        if (s.valid && s.seq >= 10 && s.seq <= 14) {
            s.temperature = 150.0f;
            s.injected = true;
        }
#endif
        b1_policy_update(&policy, &s);
        b1_stats.sensor_samples++;
        char temp_text[24], hum_text[24], score_text[24];
        if (isfinite(s.score)) snprintf(score_text, sizeof(score_text), "%.3f", s.score);
        else strlcpy(score_text, "null", sizeof(score_text));
        if (s.valid) {
            snprintf(temp_text, sizeof(temp_text), "%.3f", s.temperature);
            snprintf(hum_text, sizeof(hum_text), "%.3f", s.humidity);
        } else {
            strlcpy(temp_text, "null", sizeof(temp_text));
            strlcpy(hum_text, "null", sizeof(hum_text));
        }
        printf("B1_SAMPLE {\"seq\":%lu,\"monotonic_ms\":%llu,\"read_ok\":%s,"
               "\"temperature\":%s,\"humidity\":%s,\"injected\":%s,"
               "\"temp_health\":\"%s\",\"temp_flags\":%lu,"
               "\"hum_health\":\"%s\",\"hum_flags\":%lu,"
               "\"usable\":%s,\"score\":%s,\"mode\":\"%s\","
               "\"upload_requested\":%s,\"detected_event\":%s,"
               "\"next_interval_ms\":%lu,\"reason\":\"%s\",\"min_free_heap\":%lu}\n",
               (unsigned long)s.seq, (unsigned long long)s.monotonic_ms,
               s.valid ? "true" : "false", temp_text, hum_text,
               s.injected ? "true" : "false",
               sensor_trust_state_name(s.temp_health.state), (unsigned long)s.temp_health.fault_flags,
               sensor_trust_state_name(s.hum_health.state), (unsigned long)s.hum_health.fault_flags,
               s.usable ? "true" : "false", score_text, s.mode,
               s.upload_requested ? "true" : "false", s.detected_event ? "true" : "false",
               (unsigned long)s.next_interval_ms, s.reason,
               (unsigned long)esp_get_minimum_free_heap_size());
        b1_queue_sample(&s);
        vTaskDelay(pdMS_TO_TICKS(s.next_interval_ms));
    }
}
