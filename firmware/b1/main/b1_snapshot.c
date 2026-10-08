#include "b1_snapshot.h"
#include "agri_lora.h"
#include <limits.h>
#include <math.h>
#include <string.h>
#include <float.h>
bool b1_boot_lease_take(b1_sleep_identity_t *id, uint64_t high, bool rtc,
                        bool *reserve, uint64_t *counter) {
  if (!id || !reserve || !counter)
    return false;
  *reserve = !(rtc && id->boot_counter_limit == high && id->next_boot_counter &&
               id->next_boot_counter <= high);
  if (*reserve) {
    if (high > UINT64_MAX - 257)
      return false;
    id->next_boot_counter = high + 1;
    id->boot_counter_limit = high + 256;
  }
  *counter = id->next_boot_counter++;
  return true;
}
_Static_assert(sizeof(float) == 4 && sizeof(double) == 8,
               "IEEE754 sizes required");
_Static_assert(FLT_RADIX == 2 && FLT_MANT_DIG == 24 && DBL_MANT_DIG == 53,
               "IEEE754 binary32/binary64 required");
typedef struct {
  uint8_t *out;
  const uint8_t *in;
  size_t n, at;
  bool ok;
} cursor_t;
static uint64_t word(cursor_t *c, uint64_t v, unsigned n) {
  if (!c->ok || n > c->n - c->at) {
    c->ok = false;
    return 0;
  }
  uint64_t r = 0;
  for (unsigned i = 0; i < n; i++) {
    if (c->in)
      r |= (uint64_t)c->in[c->at + i] << (8 * i);
    else
      c->out[c->at + i] = (uint8_t)(v >> (8 * i));
  }
  c->at += n;
  return c->in ? r : v;
}
static void bytes(cursor_t *c, char *p, size_t n) {
  for (size_t i = 0; i < n; i++)
    p[i] = (char)word(c, (uint8_t)p[i], 1);
}
static void u32(cursor_t *c, uint32_t *p) { *p = (uint32_t)word(c, *p, 4); }
static void u64(cursor_t *c, uint64_t *p) { *p = word(c, *p, 8); }
static void integer(cursor_t *c, int *p) {
  uint32_t v = (uint32_t)*p;
  u32(c, &v);
  if (c->in) {
    if (v > INT_MAX && v != UINT32_MAX)
      c->ok = false;
    *p = v == UINT32_MAX ? -1 : (int)(v & INT_MAX);
  }
}
static void boolean(cursor_t *c, bool *p) {
  uint64_t v = word(c, *p, 1);
  if (v > 1)
    c->ok = false;
  *p = v != 0;
}
static void f32(cursor_t *c, float *p) {
  uint32_t v;
  memcpy(&v, p, 4);
  u32(c, &v);
  memcpy(p, &v, 4);
  if (!isfinite(*p))
    c->ok = false;
}
static void f64(cursor_t *c, double *p) {
  uint64_t v;
  memcpy(&v, p, 8);
  u64(c, &v);
  memcpy(p, &v, 8);
  if (!isfinite(*p))
    c->ok = false;
}
static void size16(cursor_t *c, size_t *p) {
  uint64_t v = word(c, *p, 2);
  if (!c->in && *p > UINT16_MAX)
    c->ok = false;
  *p = (size_t)v;
}
static void trust_config(cursor_t *c, sensor_trust_config_t *p) {
  f32(c, &p->min_value);
  f32(c, &p->max_value);
  f32(c, &p->stuck_epsilon);
  integer(c, &p->stuck_window);
  f32(c, &p->spike_threshold);
  integer(c, &p->drift_window);
  f32(c, &p->drift_threshold);
  integer(c, &p->missing_limit);
}
/* Configuration fingerprint includes all mathematical parameters and ladder
 * CONTENTS, never pointer addresses. Dynamic control threshold is state below.
 */
static bool fingerprint(b1_policy_t *p, uint32_t *hash) {
  uint8_t buf[512];
  cursor_t c = {.out = buf, .n = sizeof(buf), .ok = true};
  trust_config(&c, &p->temperature.config);
  trust_config(&c, &p->humidity.config);
  for (unsigned i = 0; i < 4; i++) {
    boolean(&c, &p->cd_config.channels[i].use);
    f32(&c, &p->cd_config.channels[i].noise_floor);
  }
  f32(&c, &p->cd_config.variety_window_s);
  f32(&c, &p->cd_config.roc_window_s);
  f32(&c, &p->cd_config.baseline_tau_s);
  f32(&c, &p->cd_config.min_interval_s);
  f32(&c, &p->cd_config.event_threshold);
  f32(&c, &p->cd_config.event_min_duration_s);
  f32(&c, &p->as_config.min_interval);
  f32(&c, &p->as_config.default_interval);
  f32(&c, &p->as_config.max_interval);
  f32(&c, &p->as_config.stable_threshold);
  f32(&c, &p->as_config.active_threshold);
  f32(&c, &p->as_config.hysteresis_fraction);
  f32(&c, &p->as_config.heartbeat_s);
  f32(&c, &p->as_config.delta_threshold);
  for (unsigned i = 0; i < 3; i++) {
    size_t n = p->as_config.ladder_len[i];
    size16(&c, &n);
    if (n == 0 || n > 16 || !p->as_config.ladders[i])
      return false;
    integer(&c, &p->as_config.ladder_confirm[i]);
    for (size_t j = 0; j < n; j++) {
      float v = p->as_config.ladders[i][j];
      f32(&c, &v);
    }
  }
  boolean(&c, &p->as_config.up_first_sample);
  boolean(&c, &p->as_config.up_on_event);
  boolean(&c, &p->as_config.up_on_state_change);
  boolean(&c, &p->as_config.up_on_interval_change);
  for (unsigned i = 0; i < 4; i++) {
    boolean(&c, &p->as_config.delta_channel_use[i]);
    f32(&c, &p->as_config.delta_noise_floor[i]);
  }
  f32(&c, &p->fault_interval_s);
  f32(&c, &p->degraded_interval_s);
  f32(&c, &p->fault_reminder_s);
  if(!c.ok)return false;
  *hash=al_crc32(buf,c.at);return true;
}
static void trust_state(cursor_t *c, sensor_trust_t *p) {
  boolean(c, &p->initialised);
  integer(c, &p->window_capacity);
  integer(c, &p->window_count);
  integer(c, &p->window_head);
  if (p->window_capacity != (p->config.stuck_window > p->config.drift_window
                                 ? p->config.stuck_window
                                 : p->config.drift_window) ||
      p->window_capacity < 1 || p->window_capacity > 64 ||
      p->window_count < 0 || p->window_count > p->window_capacity ||
      p->window_head < 0 || p->window_head >= p->window_capacity)
    c->ok = false;
  for (unsigned i = 0; i < 64; i++) {
    f32(c, &p->window[i].value);
    u64(c, &p->window[i].timestamp_ms);
  }
  integer(c, &p->consecutive_invalid);
  boolean(c, &p->has_last_valid);
  f32(c, &p->last_valid_value);
  u64(c, &p->last_valid_ts);
  boolean(c, &p->spike_pending);
  f32(c, &p->spike_reference);
  integer(c, &p->spike_confirmed_count);
  integer(c, &p->drift_streak);
  integer(c, &p->drift_direction);
  integer(c, &p->last_result.health_score);
  uint32_t state = p->last_result.state;
  u32(c, &state);
  p->last_result.state = (sensor_health_state_t)state;
  u32(c, &p->last_result.fault_flags);
  if (!p->initialised || p->consecutive_invalid < 0 ||
      p->spike_confirmed_count < 0 || p->spike_confirmed_count == INT_MAX ||
      p->drift_streak < 0 || p->drift_streak == INT_MAX ||
      p->drift_direction < -1 || p->drift_direction > 1 || state > 2 ||
      p->last_result.health_score < 0 || p->last_result.health_score > 100 ||
      (p->last_result.fault_flags & ~FAULT_ALL))
    c->ok = false;
}
static void state(cursor_t *c, b1_policy_t *p, b1_sleep_identity_t *id) {
  u32(c, &id->sequence);
  u32(c, &id->generation);
  bytes(c, id->owner, 3);
  bytes(c, id->previous_boot, B1_BOOT_ID_SIZE);
  u64(c, &id->saved_ms);
  u64(c, &id->planned_sleep_ms);
  u64(c, &id->next_boot_counter);
  u64(c, &id->boot_counter_limit);
  if ((id->next_boot_counter || id->boot_counter_limit) &&
      (!id->next_boot_counter || id->boot_counter_limit == UINT64_MAX ||
       id->next_boot_counter > id->boot_counter_limit + 1))
    c->ok = false;
  if (id->generation < 1 || id->owner[2] != 0 ||
      (memcmp(id->owner, "A1", 3) && memcmp(id->owner, "A2", 3)) ||
      !memchr(id->previous_boot, 0, B1_BOOT_ID_SIZE) ||
      id->planned_sleep_ms < 1000 || id->planned_sleep_ms > 86400000)
    c->ok = false;
  trust_state(c, &p->temperature);
  trust_state(c, &p->humidity);
  for (unsigned i = 0; i < 4; i++) {
    size_t expected_cap = p->detector.hist_cap[i];
    size16(c, &p->detector.hist_len[i]);
    size16(c, &p->detector.hist_cap[i]);
    if (c->in && p->detector.hist_cap[i] != expected_cap)
      c->ok = false;
    if (p->detector.hist_cap[i] < 1 || p->detector.hist_cap[i] > 64 ||
        p->detector.hist_len[i] > p->detector.hist_cap[i])
      c->ok = false;
    for (unsigned j = 0; j < 64; j++) {
      f64(c, &p->detector.hist[i][j].t);
      f32(c, &p->detector.hist[i][j].value);
    }
    f32(c, &p->detector.ema[i]);
    boolean(c, &p->detector.ema_valid[i]);
    f64(c, &p->detector.last_t[i]);
    boolean(c, &p->detector.has_last[i]);
  }
  f64(c, &p->detector.event_potential_start);
  boolean(c, &p->detector.event_active);
  boolean(c, &p->detector.hist_truncated);
  uint32_t st = p->scheduler.state;
  u32(c, &st);
  p->scheduler.state = (as_state_t)st;
  f32(c, &p->scheduler.interval);
  if (st >= AS_NUM_STATES ||
      p->scheduler.interval < p->as_config.min_interval ||
      p->scheduler.interval > p->as_config.max_interval)
    c->ok = false;
  for (unsigned i = 0; i < 3; i++) {
    integer(c, &p->scheduler.ladder_pos[i]);
    integer(c, &p->scheduler.rung_count[i]);
    if (p->scheduler.ladder_pos[i] < 0 ||
        (size_t)p->scheduler.ladder_pos[i] >= p->as_config.ladder_len[i] ||
        p->scheduler.rung_count[i] < 0 ||
        p->scheduler.rung_count[i] >= p->as_config.ladder_confirm[i])
      c->ok = false;
  }
  uint64_t samples = p->scheduler.n_samples;
  u64(c, &samples);
  if (samples >= ULONG_MAX)
    c->ok = false;
  p->scheduler.n_samples = (unsigned long)samples;
  f64(c, &p->scheduler.last_upload_t);
  boolean(c, &p->scheduler.has_uploaded);
  for (unsigned i = 0; i < 4; i++) {
    f32(c, &p->scheduler.last_upload_values[i]);
    boolean(c, &p->scheduler.last_upload_valid[i]);
  }
  f32(c, &p->scheduler.last_interval);
  boolean(c, &p->scheduler.prev_event_active);
  boolean(c, &p->untrusted);
  boolean(c, &p->has_health);
  boolean(c, &p->last_valid);
  st = p->last_health;
  u32(c, &st);
  p->last_health = (sensor_health_state_t)st;
  if (st > 2)
    c->ok = false;
  u32(c, &p->last_temp_flags);
  u32(c, &p->last_hum_flags);
  f64(c, &p->last_notification_t);
  f32(c, &p->temperature_threshold);
  f32(c, &p->temperature_margin);
  f32(c, &p->reported_temperature);
  boolean(c, &p->has_reported_temperature);
  boolean(c, &p->has_confirmed);
  u32(c, &p->confirmed_seq);
  u64(c, &p->confirmed_ms);
  if (p->confirmed_seq > id->sequence || p->confirmed_ms > id->saved_ms ||
      p->temperature_margin < 0 || (p->last_temp_flags & ~FAULT_ALL) ||
      (p->last_hum_flags & ~FAULT_ALL))
    c->ok = false;
}
/* Reject impossible active timestamps and state sizes even with a valid CRC. */
static bool valid_time(const b1_policy_t *p, const b1_sleep_identity_t *id) {
  const sensor_trust_t *trust[2] = {&p->temperature, &p->humidity};
  for (unsigned ch = 0; ch < 2; ch++) {
    const sensor_trust_t *t = trust[ch];
    if (t->has_last_valid && t->last_valid_ts > id->saved_ms)
      return false;
    for (int j = 0; j < t->window_count; j++)
      if (t->window[(t->window_head + j) % t->window_capacity].timestamp_ms >
          id->saved_ms)
        return false;
  }
  double end = id->saved_ms / 1000.0;
  for (unsigned ch = 0; ch < 4; ch++) {
    if (p->detector.has_last[ch] &&
        (p->detector.last_t[ch] < 0 || p->detector.last_t[ch] > end))
      return false;
    for (size_t j = 0; j < p->detector.hist_len[ch]; j++)
      if (p->detector.hist[ch][j].t < 0 || p->detector.hist[ch][j].t > end ||
          (j && p->detector.hist[ch][j].t < p->detector.hist[ch][j - 1].t))
        return false;
  }
  return p->detector.event_potential_start <= end &&
         p->last_notification_t >= 0 && p->last_notification_t <= end &&
         (!p->scheduler.has_uploaded || (p->scheduler.last_upload_t >= 0 &&
                                         p->scheduler.last_upload_t <= end));
}
static uint32_t checksum(const uint8_t *b, size_t n) {
  /* Include header metadata in integrity, with zeroed CRC field. */
  uint32_t crc = ~0u;
  for (size_t i = 0; i < n; i++) {
    uint8_t x = (i >= 12 && i < 16) ? 0 : b[i];
    crc ^= x;
    for (unsigned k = 0; k < 8; k++)
      crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320u : 0);
  }
  return ~crc;
}
bool b1_snapshot_encode(const b1_policy_t *p, const b1_sleep_identity_t *id,
                        uint8_t *out, size_t cap, size_t *length) {
  if (!p || !id || !out || !length || cap < 16 || cap > B1_SNAPSHOT_MAX)
    return false;
  /* Scratch protects input from the shared field walk; all pointers stay local.
   */
  b1_policy_t copy = *p;
  b1_sleep_identity_t identity = *id;
  cursor_t c = {.out = out, .n = cap, .ok = true};
  word(&c, 0x53413142, 4);
  word(&c, B1_SNAPSHOT_VERSION, 2);
  word(&c, 0, 2);
  uint32_t config_hash;
  if(!fingerprint(&copy,&config_hash))return false;
  word(&c,config_hash,4);
  word(&c, 0, 4);
  state(&c, &copy, &identity);
  if (!c.ok || !valid_time(&copy, &identity))
    return false;
  out[6] = (uint8_t)c.at;
  out[7] = (uint8_t)(c.at >> 8);
  uint32_t crc = checksum(out, c.at);
  for (unsigned i = 0; i < 4; i++)
    out[12 + i] = (uint8_t)(crc >> (8 * i));
  *length = c.at;
  return true;
}
b1_restore_result_t b1_snapshot_restore(b1_policy_t *p, b1_sleep_identity_t *id,
                                        const uint8_t *in, size_t n,
                                        uint32_t minimum_generation,
                                        bool trusted, uint64_t elapsed,
                                        uint64_t *current) {
  if (!p || !id || !in || !current || n < 16 || n > B1_SNAPSHOT_MAX)
    return B1_RESTORE_REJECTED;
  b1_policy_t temp;
  if (!b1_policy_init(&temp))
    return B1_RESTORE_REJECTED;
  uint32_t config_hash;
  if(!fingerprint(&temp,&config_hash))return B1_RESTORE_REJECTED;
  b1_sleep_identity_t identity = {0};
  cursor_t c = {.in = in, .n = n, .ok = true};
  if (word(&c, 0, 4) != 0x53413142 || word(&c, 0, 2) != B1_SNAPSHOT_VERSION ||
      word(&c, 0, 2) != n || word(&c, 0, 4) != config_hash ||
      word(&c, 0, 4) != checksum(in, n))
    return B1_RESTORE_REJECTED;
  state(&c, &temp, &identity);
  if (!c.ok || !valid_time(&temp, &identity) || c.at != n ||
      identity.generation < minimum_generation ||
      identity.saved_ms > UINT64_MAX - elapsed ||
      (trusted && elapsed > 86400000))
    return B1_RESTORE_REJECTED;
  b1_restore_result_t result = B1_RESTORE_CONTINUOUS;
  if (!trusted) {
    /* A guessed duration must not fabricate EMA/ROC/debounce continuity. Keep
     * sequence/epoch/provenance but require a newly confirmed report baseline.
     */
    float threshold = temp.temperature_threshold,
          margin = temp.temperature_margin;
    b1_policy_init(&temp);
    temp.temperature_threshold = threshold;
    temp.temperature_margin = margin;
    *current = 0;
    result = B1_RESTORE_TIME_UNKNOWN;
  } else
    *current = identity.saved_ms + elapsed;
  *p = temp;
  p->detector.cfg = &p->cd_config;
  p->scheduler.cfg = &p->as_config;
  *id = identity;
  return result;
}
bool b1_sleep_next_sequence(b1_sleep_identity_t *id, uint32_t *seq) {
  if (!id || !seq || id->sequence == UINT32_MAX)
    return false;
  *seq = ++id->sequence;
  return true;
}
bool b1_epoch_encode(uint32_t gen, const char *owner, uint8_t out[16]) {
  if (!out || !owner || gen < 1 || (strcmp(owner, "A1") && strcmp(owner, "A2")))
    return false;
  memset(out, 0, 16);
  cursor_t c = {.out = out, .n = 16, .ok = true};
  word(&c, 0x45313142, 4);
  word(&c, gen, 4);
  word(&c, owner[1], 1);
  c.at = 12;
  word(&c, al_crc32(out, 12), 4);
  return true;
}
bool b1_epoch_decode(const uint8_t in[16], uint32_t *gen, char owner[3]) {
  if (!in || !gen || !owner)
    return false;
  cursor_t c = {.in = in, .n = 16, .ok = true};
  if (word(&c, 0, 4) != 0x45313142)
    return false;
  uint32_t g = (uint32_t)word(&c, 0, 4);
  unsigned o = (unsigned)word(&c, 0, 1);
  c.at = 12;
  if (g < 1 || (o != '1' && o != '2') || word(&c, 0, 4) != al_crc32(in, 12))
    return false;
  *gen = g;
  owner[0] = 'A';
  owner[1] = (char)o;
  owner[2] = 0;
  return true;
}
