#include "b1_lora_network.h"
#include "agri_lora.h"
#include "b1.h"
#include "b1_e220.h"
#include "b1_registration.h"
#include "b1_transport.h"
#include "b1_deep_sleep.h"
#include "b1_radio_schedule.h"
#include "freertos/task.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include "sdkconfig.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
static b1_registration_t registration = {.generation = 1, .owner = "A1"};
static uint8_t session[16], frame[AL_MAX_FRAME], raw[AL_MAX_MESSAGE + 1];
static al_receiver_t receiver;
static uint8_t gateway_sessions[2][16];
static bool gateway_known[2];
static const char *types[] = {"SENSOR_DATA",    "CONTROL_COMMAND",
                              "CONTROL_RESULT", "HEARTBEAT",
                              "ALERT",          "SERVER_POLICY",
                              "NODE_REGISTER",  "NODE_REGISTER_ACK",
                              "NODE_STATUS",    "ACK",
                              "PERSISTED_ACK"};
static const char *roles[] = {"SERVER", "A1", "A2", "B1", "B2", "C1", "C2"};
static uint64_t now_ms(void) { return (uint64_t)(esp_timer_get_time() / 1000); }
static bool text(const cJSON *m, const char *key, const char *wanted) {
  const cJSON *v = cJSON_GetObjectItemCaseSensitive(m, key);
  return cJSON_IsString(v) && !strcmp(v->valuestring, wanted);
}
static bool number(const cJSON *o, const char *key, uint32_t *value) {
  const cJSON *n = cJSON_GetObjectItemCaseSensitive(o, key);
  if (!n) {
    *value = 0;
    return true;
  }
  if (!cJSON_IsNumber(n) || !isfinite(n->valuedouble) || n->valuedouble < 0 ||
      n->valuedouble > UINT32_MAX || floor(n->valuedouble) != n->valuedouble)
    return false;
  *value = (uint32_t)n->valuedouble;
  return true;
}
/* Match common.lora.codec's sequence/generation precedence. */
static bool wire_numbers(const cJSON *m, uint32_t *sequence, uint32_t *generation) {
 const cJSON *p=cJSON_GetObjectItemCaseSensitive(m,"payload");
 const cJSON *seq_owner=cJSON_GetObjectItemCaseSensitive(m,"sequence")?m:p;
 const char *seq_key=seq_owner==m?"sequence":"sample_seq";
 const cJSON *gen_owner=cJSON_GetObjectItemCaseSensitive(m,"generation")?m:p;
 const char *gen_key=gen_owner==m?"generation":(cJSON_GetObjectItemCaseSensitive(p,"gateway_generation")?"gateway_generation":"generation");
 return number(seq_owner,seq_key,sequence) && number(gen_owner,gen_key,generation);
}
/* Deterministic key ordering, bounded depth. Number spelling is cJSON's
 * portable representation; this is not a claim of RFC8785/JCS signing
 * semantics. */
static bool sort_json(cJSON *v, unsigned depth) {
  if (depth > 16)
    return false;
  for (cJSON *c = v->child; c; c = c->next)
    if (!sort_json(c, depth + 1))
      return false;
  if (!cJSON_IsObject(v))
    return true;
  cJSON *sorted = NULL, *c = v->child;
  while (c) {
    cJSON *next = c->next, *before = NULL, *at = sorted;
    while (at && strcmp(at->string, c->string) < 0) {
      before = at;
      at = at->next;
    }
    c->prev = before;
    c->next = at;
    if (at)
      at->prev = c;
    if (before)
      before->next = c;
    else
      sorted = c;
    c = next;
  }
  v->child = sorted;
  return true;
}
static bool transmit(cJSON *m, uint64_t deadline) {
  bool ok = false;
  char *json = NULL;
  al_frame_t meta = {.source = 3};
  cJSON *t = cJSON_GetObjectItemCaseSensitive(m, "type"),
        *to = cJSON_GetObjectItemCaseSensitive(m, "target"),
        *id = cJSON_GetObjectItemCaseSensitive(m, "message_id");
  if (!cJSON_IsString(t) || !cJSON_IsString(to) || !cJSON_IsString(id) ||
      strlen(id->valuestring) > 128)
    goto done;
  unsigned kind = 0;
  while (kind < 11 && strcmp(types[kind], t->valuestring))
    kind++;
  unsigned dest = 0;
  while (dest < 7 && strcmp(roles[dest], to->valuestring))
    dest++;
  if (kind == 11 || dest == 7)
    goto done;
  int zone = al_zone(3, dest, kind);
  if (zone < 0)
    goto done;
  meta.type = kind;
  meta.destination = dest;
  meta.zone = zone;
  memcpy(meta.session, session, 16);
  uint8_t digest[32];
  if (mbedtls_sha256((const uint8_t *)id->valuestring, strlen(id->valuestring),
                     digest, 0))
    goto done;
  memcpy(meta.logical, digest, 16);
  if (!wire_numbers(m,&meta.sequence,&meta.generation)) goto done;
  if (!sort_json(m, 0))
    goto done;
  json = cJSON_PrintUnformatted(m);
  if (!json)
    goto done;
  size_t n = strlen(json), chunk = CONFIG_B1_E220_FRAME_MTU - AL_HEADER;
  if (!n || n > AL_MAX_MESSAGE || (n + chunk - 1) / chunk > AL_MAX_FRAGMENTS)
    goto done;
  for (unsigned i = 0; i < (n + chunk - 1) / chunk; ++i) {
    size_t bytes = 0;
    uint64_t now = now_ms();
    if (now >= deadline)
      goto done;
    if (!al_fragment((uint8_t *)json, n, &meta, CONFIG_B1_E220_FRAME_MTU, i,
                     frame, sizeof(frame), &bytes))
      goto done;
    uint32_t wait = (uint32_t)(deadline - now);
    if (wait > 2000)
      wait = 2000;
    if (b1_e220_send(frame, bytes, wait) != ESP_OK)
      goto done;
  }
  ok = true;
done:
  cJSON_free(json);
  cJSON_Delete(m);
  return ok;
}
static cJSON *receive(const char *gateway, uint64_t deadline,
                      bool registering) {
  while (now_ms() < deadline) {
    uint32_t wait = (uint32_t)(deadline - now_ms());
    if (wait > 200)
      wait = 200;
    int n = b1_e220_receive(frame, sizeof(frame), wait);
    if (n < 0)
      return NULL;
    if (!n)
      continue;
    al_frame_t f;
    if (!al_decode(frame, (size_t)n, &f) || f.destination != 3 ||
        f.source != (uint8_t)(!strcmp(gateway, "A1") ? 1 : 2))
      continue;
    unsigned g = f.source - 1;
    if (!registering &&
        (!gateway_known[g] || memcmp(gateway_sessions[g], f.session, 16)))
      continue;
    size_t length = 0;
    al_frame_t completed;
    int rc = al_receive(&receiver, frame, (size_t)n, now_ms(), raw,
                        AL_MAX_MESSAGE, &length, &completed);
    if (rc != 1)
      continue;
    raw[length] = 0;
    cJSON *m = cJSON_ParseWithLength((char *)raw, length);
    uint32_t seq = 0, generation = 0;
    cJSON *payload = cJSON_GetObjectItemCaseSensitive(m, "payload");
    cJSON *id = cJSON_GetObjectItemCaseSensitive(m, "message_id");
    uint8_t hash[32];
    if (!wire_numbers(m,&seq,&generation) ||
        seq != completed.sequence || generation != completed.generation ||
        (cJSON_GetObjectItemCaseSensitive(payload, "generation") && generation < registration.generation) ||
        !text(m, "source", gateway) || !text(m, "target", "B1") ||
        !cJSON_IsString(id) || strlen(id->valuestring) > 128 ||
        mbedtls_sha256((uint8_t *)id->valuestring, strlen(id->valuestring),
                       hash, 0) ||
        memcmp(hash, completed.logical, 16) ||
        !text(m, "type", types[completed.type])) {
      cJSON_Delete(m);
      continue;
    }
    if (registering) {
      memcpy(gateway_sessions[g], completed.session, 16);
      gateway_known[g] = true;
    }
    return m;
  }
  return NULL;
}
static bool register_radio(const char *gateway, uint64_t deadline) {
  cJSON *p = cJSON_CreateObject();
  cJSON_AddStringToObject(p, "node_id", "B1");
  cJSON_AddStringToObject(p, "node_type", "SENSOR");
  cJSON_AddStringToObject(p, "node_mode", "physical");
  cJSON_AddStringToObject(p, "boot_id", b1_boot_id);
  cJSON_AddNumberToObject(p, "generation", registration.generation);
  if (!transmit(b1_envelope("NODE_REGISTER", gateway, p, now_ms() / 1000.0),
                deadline))
    return false;
  cJSON *m = receive(gateway, deadline, true);
  b1_registration_result_t result =
      b1_registration_reply(&registration, m, gateway);
  cJSON_Delete(m);
  printf("B1_RADIO "
         "{\"event\":\"REGISTER_RESULT\",\"result\":%d,\"generation\":%lu}\n",
         result, (unsigned long)registration.generation);
#if CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL
  if (result==B1_REG_ACCEPTED || result==B1_REG_NOT_OWNER) {
    if(!b1_sleep_epoch_commit(registration.generation,registration.owner))return false;
  }
#endif
  return result == B1_REG_ACCEPTED;
}
static bool send_record(const b1_record_t *record, uint64_t deadline) {
  const char *line = record->wire;
  while (*line) {
    const char *end = strchr(line, '\n');
    if (!end)
      return false;
    cJSON *m = cJSON_ParseWithLength(line, (size_t)(end - line));
    if (!m)
      return false;
    cJSON_ReplaceItemInObject(m, "target",
                              cJSON_CreateString(registration.owner));
    cJSON *p = cJSON_GetObjectItemCaseSensitive(m, "payload");
    uint64_t now = now_ms();
    if (!strcmp(record->boot_id, b1_boot_id) && now >= record->acquired_ms)
      cJSON_AddNumberToObject(p, "delivery_age_ms",
                              (double)(now - record->acquired_ms));
    else
      cJSON_AddNullToObject(p, "delivery_age_ms");
    if (!transmit(m, deadline))
      return false;
    line = end + 1;
  }
  return true;
}
static void ack(cJSON *m) {
  if (!text(m, "type", "PERSISTED_ACK"))
    return;
  cJSON *p = cJSON_GetObjectItemCaseSensitive(m, "payload"),
        *id = cJSON_GetObjectItemCaseSensitive(p, "ack_message_id");
  if (cJSON_IsString(id) && text(p, "scope", "GATEWAY_OUTBOX") &&
      text(p, "delivery_contract", "gateway-durable-v1") &&
      cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(p, "persisted")))
    b1_queue_ack(id->valuestring);
}
bool b1_lora_run_window(uint32_t budget) {
  if (budget < 100 || budget > 30000)
    return false;
  uint64_t deadline = now_ms() + budget;
  if (b1_e220_init() != ESP_OK) {
    printf("B1_RADIO {\"event\":\"INIT_FAILED\"}\n");
    return false;
  }
  esp_fill_random(session, sizeof(session));
  al_receiver_init(&receiver);
  memset(gateway_known, 0, sizeof(gateway_known));
  char preferred[3];
  memcpy(preferred, registration.owner, 3);
  bool registered = false;
  for (unsigned i = 0; i < 2 && now_ms() < deadline; ++i) {
    const char *name =
        i == 0 ? preferred : (!strcmp(preferred, "A1") ? "A2" : "A1");
    uint64_t limit = now_ms() + 2000;
    if (limit > deadline)
      limit = deadline;
    if (register_radio(name, limit)) {
      registered = true;
      break;
    }
  }
  static b1_record_t record;
  while (registered && now_ms() < deadline) {
    if (b1_queue_next(&record, now_ms()) && !send_record(&record, deadline))
      break;
    uint64_t limit = now_ms() + 200;
    if (limit > deadline)
      limit = deadline;
    cJSON *m = receive(registration.owner, limit, false);
    if (m) {
      if (text(m, "type", "NODE_STATUS") && cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(m,"payload"),"generation")) {
        cJSON_ReplaceItemInObject(m,"type",cJSON_CreateString("NODE_REGISTER_ACK"));
        cJSON_AddTrueToObject(cJSON_GetObjectItemCaseSensitive(m,"payload"),"accepted");
        registered = b1_registration_reply(&registration,m,registration.owner)==B1_REG_ACCEPTED;
      }
#if CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL
      if(!b1_sleep_epoch_commit(registration.generation,registration.owner))registered=false;
#endif
      if(registered)ack(m);
      cJSON_Delete(m);
    }
    if (!b1_queue_pending_count())
      break;
  }
  bool stopped = b1_e220_shutdown(2000) == ESP_OK;
  return registered && stopped;
}
static TaskHandle_t network_task;
void b1_lora_notify_pending(void) {
#if !CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL
  if (network_task) xTaskNotifyGive(network_task);
#endif
}
void b1_lora_network_task(void *arg) {
  (void)arg;
  network_task = xTaskGetCurrentTaskHandle();
  b1_radio_schedule_t schedule;
  b1_radio_schedule_init(&schedule);
  while (true) {
    unsigned before = b1_queue_pending_count();
    if (b1_radio_schedule_due(&schedule, now_ms(), before != 0)) {
      uint32_t confirmed_before = b1_queue_acknowledged_count();
      b1_lora_run_window(10000); /* This task is the only ordinary UART owner. */
      unsigned after = b1_queue_pending_count();
      b1_radio_schedule_finish(&schedule, now_ms(), after != 0, b1_queue_acknowledged_count() != confirmed_before);
    }
    uint32_t delay = b1_radio_schedule_wait(&schedule, now_ms(), b1_queue_pending_count()!=0);
    TickType_t wait = delay == UINT32_MAX ? portMAX_DELAY : pdMS_TO_TICKS(delay);
    if (delay && !wait) wait = 1;
    /* Notifications coalesce. HIGH during backoff wakes this gate but cannot
     * start another RF window early. New queue admission never touches UART. */
    ulTaskNotifyTake(pdTRUE, wait);
  }
}
uint32_t b1_lora_generation(void) { return registration.generation; }
const char *b1_lora_owner(void) { return registration.owner; }
void b1_lora_restore_owner(uint32_t generation, const char *owner) {
  if (generation >= registration.generation && owner &&
      (!strcmp(owner, "A1") || !strcmp(owner, "A2"))) {
    registration.generation = generation;
    memcpy(registration.owner, owner, 3);
    registration.confirmed = true;
  }
}
