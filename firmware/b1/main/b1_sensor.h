#pragma once
#include <stdbool.h>
bool b1_sensor_init(void);
bool b1_sensor_read(float *, float *);
bool b1_sensor_shutdown(void);
