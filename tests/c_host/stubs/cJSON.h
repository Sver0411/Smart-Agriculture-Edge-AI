#pragma once
// Host dispatch stub only. Real serialization/RF require device integration.
typedef struct { int unused; } cJSON;
cJSON *cJSON_CreateObject(void);
cJSON *cJSON_CreateArray(void);
cJSON *cJSON_CreateString(const char *value);
void cJSON_AddItemToArray(cJSON *array, cJSON *item);
cJSON *cJSON_AddObjectToObject(cJSON *obj, const char *name);
void cJSON_AddNumberToObject(cJSON *obj, const char *name, double value);
void cJSON_AddStringToObject(cJSON *obj, const char *name, const char *value);
void cJSON_AddBoolToObject(cJSON *obj, const char *name, int value);
void cJSON_AddNullToObject(cJSON *obj, const char *name);
void cJSON_AddItemToObject(cJSON *obj, const char *name, cJSON *child);
