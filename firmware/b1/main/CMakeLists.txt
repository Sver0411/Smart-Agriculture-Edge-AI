idf_component_register(SRCS "main.c" "b1_sensor.c" "b1_network.c" "b1_policy.c" "b1_telemetry.c" "b1_queue.c" "b1_runtime.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_wifi esp_netif nvs_flash json esp_timer esp_pm sensor_trust adaptive_sense)
