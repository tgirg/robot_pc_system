#pragma once

#include <Arduino.h>
#include "vehicle_config.h"

class MotorControllerArray {
public:
  void begin();
  void brakeAll();
  void setLogicalPwm(uint8_t logical, int16_t pwm, const VehicleConfig& config);
  void setAllLogicalPwm(const int16_t pwm[WHEEL_COUNT], const VehicleConfig& config);
  void update();
  int16_t logicalOutput(uint8_t logical, const VehicleConfig& config) const;

private:
  int16_t _targetPhysical[WHEEL_COUNT] = {0, 0, 0, 0};
  int16_t _currentPhysical[WHEEL_COUNT] = {0, 0, 0, 0};
  int8_t _lastDir[WHEEL_COUNT] = {0, 0, 0, 0};

  void setupPwm(uint8_t pin, uint8_t channel);
  void writePwm(uint8_t channel, uint16_t duty);
  void writePhysical(uint8_t physical, int16_t signedPwm);
  int8_t signOf(int16_t value) const;
};

