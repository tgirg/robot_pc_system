#pragma once

#include <Arduino.h>

#define MOTOR_OUTPUT_ENABLED 0

void initMotorDriver();
void setMotorSpeed(int left, int right);
void stopMotors();
void emergencyStopMotors();
