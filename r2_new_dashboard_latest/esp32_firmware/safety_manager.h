#pragma once

#include <Arduino.h>
#include "vehicle_config.h"

enum RobotState : uint8_t {
  STATE_SAFE = 0,
  STATE_NORMAL = 1,
  STATE_DEBUG = 2,
  STATE_BLOCKED = 3
};

class SafetyManager {
public:
  void begin();
  void enterSafe(uint32_t faultFlag);
  void enterBlocked(uint32_t faultFlag);
  bool armNormal(const VehicleConfig& config, bool pca9685Ok, bool pcntOk, char* reason, size_t reasonSize);
  bool armDebug(char* reason, size_t reasonSize);
  void disarm();
  RobotState state() const;
  bool armed() const;
  uint32_t faultFlags() const;
  const char* stateName() const;
  bool canApplyDrive() const;

private:
  RobotState _state = STATE_SAFE;
  bool _armed = false;
  uint32_t _faultFlags = 0;
};

static const uint32_t FAULT_NONE = 0;
static const uint32_t FAULT_CONFIG = 1UL << 0;
static const uint32_t FAULT_PCA9685 = 1UL << 1;
static const uint32_t FAULT_UNCALIBRATED_SERVO = 1UL << 2;
static const uint32_t FAULT_DIMENSIONS_UNSET = 1UL << 3;
static const uint32_t FAULT_ENCODER_CPR_UNSET = 1UL << 4;
static const uint32_t FAULT_COMMAND_TIMEOUT = 1UL << 5;
static const uint32_t FAULT_EXTERNAL_ESTOP = 1UL << 6;
static const uint32_t FAULT_BAD_COMMAND = 1UL << 7;
static const uint32_t FAULT_BLOCKED = 1UL << 8;
static const uint32_t FAULT_PCNT = 1UL << 9;
