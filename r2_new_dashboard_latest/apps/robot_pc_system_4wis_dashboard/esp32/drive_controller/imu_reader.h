#pragma once

#include <Arduino.h>

#define USE_REAL_IMU 0
#define IMU_TYPE_MPU6050 1

void initImu();
void updateImu();
bool hasImu();
float getYaw();
float getPitch();
float getRoll();
float getGyroX();
float getGyroY();
float getGyroZ();
const char* getImuStatus();
