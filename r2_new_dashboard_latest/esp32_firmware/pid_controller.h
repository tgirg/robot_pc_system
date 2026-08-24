#pragma once

#include <Arduino.h>
#include "vehicle_config.h"

class PidController {
public:
  void reset();
  int16_t update(float targetRpm, float measuredRpm, const MotorConfig& config, float dtSeconds);

private:
  float _integral = 0.0f;
  float _previousError = 0.0f;
};

