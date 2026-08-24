#pragma once

#include <Arduino.h>
#include "vehicle_config.h"

class Pca9685ServoArray {
public:
  bool begin(uint8_t address);
  bool connected() const;
  uint8_t address() const;
  uint32_t failureCount() const;
  void safeCenterCalibrated(const VehicleConfig& config);
  bool setLogicalTargetDeg(uint8_t logical, float angleDeg, const VehicleConfig& config, bool debugAllowed);
  bool debugSetLogicalPulse(uint8_t logical, uint16_t pulseUs, const VehicleConfig& config);
  bool update(uint32_t nowMs, const VehicleConfig& config);
  float logicalEstimatedDeg(uint8_t logical) const;

private:
  uint8_t _address = DEFAULT_PCA9685_ADDRESS;
  bool _connected = false;
  uint32_t _failureCount = 0;
  uint32_t _lastUpdateMs = 0;
  float _currentDeg[WHEEL_COUNT] = {0, 0, 0, 0};
  float _targetDeg[WHEEL_COUNT] = {0, 0, 0, 0};

  bool ping();
  bool write8(uint8_t reg, uint8_t value);
  uint8_t read8(uint8_t reg);
  bool setPwmFrequency(float hz);
  bool setPwm(uint8_t channel, uint16_t onTick, uint16_t offTick);
  bool writePulse(uint8_t channel, uint16_t pulseUs);
  uint16_t pulseForAngle(float angleDeg, const ServoConfig& servo) const;
};
