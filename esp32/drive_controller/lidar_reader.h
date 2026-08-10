#pragma once

#include <Arduino.h>

#ifndef USE_REAL_LIDAR
#define USE_REAL_LIDAR 0
#endif

#ifndef LIDAR_TYPE_UNKNOWN
#define LIDAR_TYPE_UNKNOWN 0
#endif

#ifndef LIDAR_TYPE_UART
#define LIDAR_TYPE_UART 1
#endif

#ifndef LIDAR_TYPE_I2C
#define LIDAR_TYPE_I2C 2
#endif

#ifndef LIDAR_TYPE
#define LIDAR_TYPE LIDAR_TYPE_UNKNOWN
#endif

void initLidar();
void updateLidar();
bool hasLidar();
int getFrontDistanceMm();
int getLeftDistanceMm();
int getRightDistanceMm();
int getRearDistanceMm();
const char* getLidarStatusText();
