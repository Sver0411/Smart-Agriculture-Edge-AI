#include "b1_registration.h"
#include <math.h>
#include <string.h>
static bool string_eq(const cJSON *o, const char *key, const char *value) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    return cJSON_IsString(v) && !strcmp(v->valuestring,value);
}
b1_registration_result_t b1_registration_reply(b1_registration_t *s, const cJSON *m, const char *gateway) {
    if (!s || !gateway || (strcmp(gateway,"A1") && strcmp(gateway,"A2")) ||
        !string_eq(m,"source",gateway) || !string_eq(m,"target","B1") ||
        !string_eq(m,"type","NODE_REGISTER_ACK")) return B1_REG_INVALID_REPLY;
    const cJSON *p=cJSON_GetObjectItemCaseSensitive(m,"payload");
    const cJSON *g=cJSON_GetObjectItemCaseSensitive(p,"generation");
    const cJSON *o=cJSON_GetObjectItemCaseSensitive(p,"owner_gateway");
    const cJSON *a=cJSON_GetObjectItemCaseSensitive(p,"accepted");
    if (!cJSON_IsNumber(g) || !isfinite(g->valuedouble) || g->valuedouble<1 ||
        g->valuedouble>UINT32_MAX || floor(g->valuedouble)!=g->valuedouble ||
        !cJSON_IsString(o) || (strcmp(o->valuestring,"A1") && strcmp(o->valuestring,"A2")) ||
        !cJSON_IsBool(a)) return B1_REG_INVALID_REPLY;
    uint32_t generation=(uint32_t)g->valuedouble;
    if (generation<s->generation || (s->confirmed && generation==s->generation &&
        strcmp(s->owner,o->valuestring))) return B1_REG_STALE_GENERATION;
    if (cJSON_IsTrue(a) && strcmp(o->valuestring,gateway)) return B1_REG_INVALID_REPLY;
    if (!cJSON_IsTrue(a) && !string_eq(p,"reason","NOT_OWNER"))
        return string_eq(p,"reason","STALE_GENERATION") ? B1_REG_STALE_GENERATION : B1_REG_INVALID_REPLY;
    s->generation=generation;
    memcpy(s->owner,o->valuestring,3);
    s->confirmed=true;
    return cJSON_IsTrue(a) ? B1_REG_ACCEPTED : B1_REG_NOT_OWNER;
}
