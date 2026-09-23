#include "b1.h"
#include "sdkconfig.h"
#include "cJSON.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "freertos/event_groups.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define WIFI_CONNECTED BIT0
static EventGroupHandle_t wifi_group;
static uint32_t message_counter;
static uint32_t highest_generation = 1;
static char owner[3] = "A1";

static uint64_t uptime_ms(void) { return (uint64_t)(esp_timer_get_time() / 1000); }

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_group, WIFI_CONNECTED);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(wifi_group, WIFI_CONNECTED);
        b1_stats.wifi_connects++;
        printf("B1_NET {\"event\":\"WIFI_CONNECTED\",\"monotonic_ms\":%llu}\n",
               (unsigned long long)uptime_ms());
    }
}

static void wifi_start(void)
{
    wifi_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    esp_event_handler_instance_t a, b;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, wifi_event, NULL, &a));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL, &b));
    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, CONFIG_B1_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_B1_WIFI_PASSWORD, sizeof(config.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_connect());
}

static int connect_gateway(const char *name)
{
    const char *host = strcmp(name, "A1") == 0 ? CONFIG_B1_A1_HOST : CONFIG_B1_A2_HOST;
    int port = strcmp(name, "A1") == 0 ? CONFIG_B1_A1_PORT : CONFIG_B1_A2_PORT;
    if (!host[0]) return -1;
    char service[8];
    snprintf(service, sizeof(service), "%d", port);
    struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM};
    struct addrinfo *addresses = NULL;
    if (getaddrinfo(host, service, &hints, &addresses) != 0) return -1;
    int fd = -1;
    for (struct addrinfo *addr = addresses; addr; addr = addr->ai_next) {
        fd = socket(addr->ai_family, addr->ai_socktype, addr->ai_protocol);
        if (fd < 0) continue;
        struct timeval timeout = {.tv_sec = 2};
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        if (connect(fd, addr->ai_addr, addr->ai_addrlen) == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(addresses);
    if (fd >= 0) b1_stats.gateway_connects++;
    return fd;
}

static cJSON *envelope(const char *type, const char *target, cJSON *payload)
{
    cJSON *root = cJSON_CreateObject();
    char id[32];
    snprintf(id, sizeof(id), "B1-%s-%08lx", b1_boot_id, (unsigned long)++message_counter);
    cJSON_AddStringToObject(root, "type", type);
    cJSON_AddStringToObject(root, "source", "B1");
    cJSON_AddStringToObject(root, "target", target);
    // The envelope carries uptime seconds. Gateway uses receipt wall time for physical B1.
    cJSON_AddNumberToObject(root, "timestamp", uptime_ms() / 1000.0);
    cJSON_AddStringToObject(root, "message_id", id);
    cJSON_AddItemToObject(root, "payload", payload);
    return root;
}

static bool send_json(int fd, cJSON *root)
{
    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!json) return false;
    size_t len = strlen(json);
    bool ok = len < 4095;
    size_t sent = 0;
    while (ok && sent < len) {
        int n = send(fd, json + sent, len - sent, 0);
        if (n <= 0) { ok = false; break; }
        sent += n;
    }
    if (ok) ok = send(fd, "\n", 1, 0) == 1;
    cJSON_free(json);
    return ok;
}

typedef struct { char line[2048]; size_t used; } rx_buffer_t;
static int receive_line(int fd, rx_buffer_t *rx, int wait_ms)
{
    fd_set set;
    FD_ZERO(&set);
    FD_SET(fd, &set);
    struct timeval tv = {.tv_sec = wait_ms / 1000, .tv_usec = (wait_ms % 1000) * 1000};
    int ready = select(fd + 1, &set, NULL, NULL, &tv);
    if (ready < 0) return -1;
    if (ready == 0) return 0;
    char ch;
    int n = recv(fd, &ch, 1, 0);
    if (n <= 0) return -1;
    if (ch == '\n') { rx->line[rx->used] = '\0'; rx->used = 0; return 1; }
    if (rx->used + 1 >= sizeof(rx->line)) { rx->used = 0; return -1; }
    rx->line[rx->used++] = ch;
    return 0;
}

static bool accept_ownership(cJSON *message, const char *gateway)
{
    cJSON *payload = cJSON_GetObjectItemCaseSensitive(message, "payload");
    cJSON *generation = cJSON_GetObjectItemCaseSensitive(payload, "generation");
    cJSON *new_owner = cJSON_GetObjectItemCaseSensitive(payload, "owner_gateway");
    if (!cJSON_IsNumber(generation) || !cJSON_IsString(new_owner) ||
        strcmp(new_owner->valuestring, gateway) != 0) return false;
    if (generation->valuedouble < highest_generation) {
        printf("B1_NET {\"event\":\"STALE_GENERATION\",\"gateway\":\"%s\",\"generation\":%d,\"current\":%lu}\n",
               gateway, generation->valueint, (unsigned long)highest_generation);
        return false;
    }
    highest_generation = generation->valueint;
    strlcpy(owner, gateway, sizeof(owner));
    printf("B1_NET {\"event\":\"REGISTERED\",\"gateway\":\"%s\",\"generation\":%lu,\"monotonic_ms\":%llu}\n",
           owner, (unsigned long)highest_generation, (unsigned long long)uptime_ms());
    return true;
}

static bool register_node(int fd, const char *gateway, rx_buffer_t *rx)
{
    for (int attempt = 0; attempt < 4; ++attempt) {
        cJSON *payload = cJSON_CreateObject();
        cJSON_AddStringToObject(payload, "node_id", "B1");
        cJSON_AddStringToObject(payload, "node_type", "SENSOR");
        cJSON_AddStringToObject(payload, "node_mode", "physical");
        b1_stats.registration_attempts++;
        if (!send_json(fd, envelope("NODE_REGISTER", gateway, payload))) return false;
        uint64_t deadline = uptime_ms() + 2000;
        while (uptime_ms() < deadline) {
            int result = receive_line(fd, rx, 100);
            if (result < 0) return false;
            if (result == 0) continue;
            cJSON *reply = cJSON_Parse(rx->line);
            cJSON *type = cJSON_GetObjectItemCaseSensitive(reply, "type");
            cJSON *source = cJSON_GetObjectItemCaseSensitive(reply, "source");
            cJSON *target = cJSON_GetObjectItemCaseSensitive(reply, "target");
            cJSON *body = cJSON_GetObjectItemCaseSensitive(reply, "payload");
            cJSON *accepted = cJSON_GetObjectItemCaseSensitive(body, "accepted");
            bool ack = cJSON_IsString(type) && strcmp(type->valuestring, "NODE_REGISTER_ACK") == 0 &&
                cJSON_IsString(source) && strcmp(source->valuestring, gateway) == 0 &&
                cJSON_IsString(target) && strcmp(target->valuestring, "B1") == 0 && cJSON_IsTrue(accepted);
            bool valid = ack && accept_ownership(reply, gateway);
            cJSON_Delete(reply);
            if (valid) { b1_stats.registration_success++; return true; }
            if (ack) return false;
        }
    }
    return false;
}

static cJSON *health_json(sensor_health_result_t health)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "score", health.health_score);
    cJSON_AddStringToObject(obj, "state", sensor_trust_state_name(health.state));
    cJSON_AddNumberToObject(obj, "flags", health.fault_flags);
    return obj;
}

static bool transmit_sample(int fd, const b1_sample_t *s)
{
    cJSON *payload = cJSON_CreateObject();
    cJSON_AddStringToObject(payload, "node_mode", "physical");
    cJSON_AddStringToObject(payload, "timestamp_source", "device_uptime");
    cJSON_AddStringToObject(payload, "boot_id", b1_boot_id);
    cJSON_AddNumberToObject(payload, "sample_seq", s->seq);
    cJSON_AddNumberToObject(payload, "device_monotonic_ms", (double)s->monotonic_ms);
    cJSON_AddBoolToObject(payload, "usable_for_control", s->usable);
    cJSON_AddBoolToObject(payload, "physical_read_ok", s->valid);
    cJSON_AddBoolToObject(payload, "test_injected", s->injected);
    cJSON_AddStringToObject(payload, "health_state", !s->usable ? "FAULT" :
        (s->temp_health.state == SENSOR_STATE_DEGRADED || s->hum_health.state == SENSOR_STATE_DEGRADED) ? "DEGRADED" : "HEALTHY");
    cJSON *data = cJSON_AddObjectToObject(payload, "data");
    if (s->valid) {
        cJSON_AddNumberToObject(data, "temperature", s->temperature);
        cJSON_AddNumberToObject(data, "humidity", s->humidity);
    }
    cJSON *health = cJSON_AddObjectToObject(payload, "health");
    cJSON_AddItemToObject(health, "temperature", health_json(s->temp_health));
    cJSON_AddItemToObject(health, "humidity", health_json(s->hum_health));
    cJSON *sampling = cJSON_AddObjectToObject(payload, "sampling");
    cJSON_AddNumberToObject(sampling, "next_interval_ms", s->next_interval_ms);
    cJSON_AddNumberToObject(sampling, "score", s->score);
    cJSON_AddStringToObject(sampling, "mode", s->mode);
    cJSON_AddStringToObject(sampling, "reason", s->reason);
    if (!send_json(fd, envelope("SENSOR_DATA", owner, payload))) return false;
    b1_stats.sensor_messages++;
    if (!s->usable || s->temp_health.state == SENSOR_STATE_DEGRADED ||
        s->hum_health.state == SENSOR_STATE_DEGRADED) {
        cJSON *alert = cJSON_CreateObject();
        cJSON_AddStringToObject(alert, "alert_type", "SENSOR_FAULT");
        cJSON_AddStringToObject(alert, "sensor_node_id", "B1");
        cJSON_AddStringToObject(alert, "health_state", s->usable ? "DEGRADED" : "FAULT");
        cJSON_AddStringToObject(alert, "message", s->injected ? "integration fault injection" : "sensor health anomaly");
        cJSON_AddNumberToObject(alert, "sample_seq", s->seq);
        if (!send_json(fd, envelope("ALERT", owner, alert))) return false;
        b1_stats.alerts++;
    }
    return true;
}

static void log_stats(void)
{
    printf("B1_STATS {\"wifi_connects\":%lu,\"gateway_connects\":%lu,\"registration_attempts\":%lu,"
           "\"registration_success\":%lu,\"sensor_samples\":%lu,\"sensor_messages\":%lu,"
           "\"alerts\":%lu,\"local_queue_drops\":%lu,\"gateway_failovers\":%lu}\n",
           (unsigned long)b1_stats.wifi_connects, (unsigned long)b1_stats.gateway_connects,
           (unsigned long)b1_stats.registration_attempts, (unsigned long)b1_stats.registration_success,
           (unsigned long)b1_stats.sensor_samples, (unsigned long)b1_stats.sensor_messages,
           (unsigned long)b1_stats.alerts, (unsigned long)b1_stats.local_queue_drops,
           (unsigned long)b1_stats.gateway_failovers);
}

void b1_network_task(void *arg)
{
    if (!CONFIG_B1_WIFI_SSID[0]) {
        printf("B1_NET {\"event\":\"WIFI_UNCONFIGURED\"}\n");
        while (true) { log_stats(); vTaskDelay(pdMS_TO_TICKS(10000)); }
    }
    wifi_start();
    uint64_t last_stats = 0;
    while (true) {
        if (!(xEventGroupWaitBits(wifi_group, WIFI_CONNECTED, pdFALSE, pdTRUE,
                                  pdMS_TO_TICKS(3000)) & WIFI_CONNECTED)) continue;
        char candidate[3];
        strlcpy(candidate, owner, sizeof(candidate));
        int fd = connect_gateway(candidate);
        if (fd < 0) {
            strlcpy(candidate, strcmp(owner, "A1") == 0 ? "A2" : "A1", sizeof(candidate));
            fd = connect_gateway(candidate);
        }
        if (fd < 0) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        rx_buffer_t rx = {0};
        if (!register_node(fd, candidate, &rx)) {
            close(fd);
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }
        if (strcmp(candidate, "A2") == 0) b1_stats.gateway_failovers++;
        bool connected = true;
        while (connected && (xEventGroupGetBits(wifi_group) & WIFI_CONNECTED)) {
            int result = receive_line(fd, &rx, 100);
            if (result < 0) break;
            if (result == 1) {
                cJSON *in = cJSON_Parse(rx.line);
                cJSON *type = cJSON_GetObjectItemCaseSensitive(in, "type");
                cJSON *source = cJSON_GetObjectItemCaseSensitive(in, "source");
                if (cJSON_IsString(type) && cJSON_IsString(source) &&
                    strcmp(source->valuestring, candidate) == 0 &&
                    strcmp(type->valuestring, "NODE_STATUS") == 0) {
                    if (!accept_ownership(in, candidate)) connected = false;
                }
                cJSON_Delete(in);
            }
            b1_sample_t sample;
            if (xQueueReceive(b1_queue, &sample, 0) == pdTRUE && !transmit_sample(fd, &sample)) {
                // Preserve the failed sample if space remains; queue is volatile and bounded.
                if (xQueueSendToFront(b1_queue, &sample, 0) != pdTRUE) b1_stats.local_queue_drops++;
                break;
            }
            if (uptime_ms() - last_stats > 10000) { log_stats(); last_stats = uptime_ms(); }
        }
        printf("B1_NET {\"event\":\"DISCONNECTED\",\"gateway\":\"%s\",\"monotonic_ms\":%llu}\n",
               candidate, (unsigned long long)uptime_ms());
        close(fd);
        vTaskDelay(pdMS_TO_TICKS(300));
    }
}
