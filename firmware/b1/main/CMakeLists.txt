idf_component_register(SRCS "main.c" "b1_sensor.c" "b1_network.c" "b1_policy.c" "b1_telemetry.c" "b1_queue.c" "b1_outbox.c" "b1_storage.c" "b1_checkpoint.c" "b1_store_backend.c" "b1_runtime.c" "b1_registration.c" "b1_e220.c" "b1_lora_network.c" "b1_radio_schedule.c" "b1_snapshot.c" "b1_deep_sleep.c"
    INCLUDE_DIRS "."
    REQUIRES esp_hw_support driver esp_wifi esp_netif nvs_flash json esp_timer esp_pm sensor_trust adaptive_sense agri_lora mbedtls)
