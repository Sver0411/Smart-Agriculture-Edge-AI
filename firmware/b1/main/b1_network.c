#include "b1.h"
#include "b1_transport.h"
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
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define WIFI_CONNECTED BIT0
static EventGroupHandle_t wifi_group;
static uint32_t highest_generation = 1;
static char owner[3] = "A1";
static bool has_owner;

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
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_MIN_MODEM));
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
    if (!cJSON_IsNumber(generation) || !isfinite(generation->valuedouble) ||
        generation->valuedouble < 1 || generation->valuedouble > UINT32_MAX ||
        floor(generation->valuedouble) != generation->valuedouble || !cJSON_IsString(new_owner) ||
        strcmp(new_owner->valuestring, gateway) != 0) return false;
    if (generation->valuedouble < highest_generation) {
        printf("B1_NET {\"event\":\"STALE_GENERATION\",\"gateway\":\"%s\",\"generation\":%d,\"current\":%lu}\n",
               gateway, generation->valueint, (unsigned long)highest_generation);
        return false;
    }
    if (has_owner && generation->valuedouble == highest_generation && strcmp(owner, gateway) != 0) return false;
    highest_generation = (uint32_t)generation->valuedouble;
    strlcpy(owner, gateway, sizeof(owner));
    has_owner = true;
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
        cJSON_AddNumberToObject(payload, "generation", highest_generation);
        b1_stats.registration_attempts++;
        if (!send_json(fd, b1_envelope("NODE_REGISTER", gateway, payload, uptime_ms() / 1000.0))) return false;
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

static bool tcp_send_payload(void *context, const char *type, cJSON *payload)
{
    int fd = *(int *)context;
    return send_json(fd, b1_envelope(type, owner, payload, uptime_ms() / 1000.0));
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
                cJSON *target = cJSON_GetObjectItemCaseSensitive(in, "target");
                if (cJSON_IsString(type) && cJSON_IsString(source) &&
                    strcmp(source->valuestring, candidate) == 0 &&
                    cJSON_IsString(target) && strcmp(target->valuestring, "B1") == 0 &&
                    strcmp(type->valuestring, "NODE_STATUS") == 0) {
                    if (!accept_ownership(in, candidate)) connected = false;
                }
                cJSON_Delete(in);
            }
            b1_sample_t sample;
            if (xQueueReceive(b1_queue, &sample, 0) == pdTRUE && !b1_transmit_sample(&(b1_transport_t){.context = &fd, .send = tcp_send_payload}, &sample)) {
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
