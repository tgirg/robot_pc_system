#include "safety_manager.h"

static void copyReason(char* reason, size_t reasonSize, const char* message) {
  if (reason != nullptr && reasonSize > 0) {
    snprintf(reason, reasonSize, "%s", message);
  }
}

void SafetyManager::begin() {
  _state = STATE_SAFE;
  _armed = false;
  _faultFlags = FAULT_NONE;
}

void SafetyManager::enterSafe(uint32_t faultFlag) {
  _state = STATE_SAFE;
  _armed = false;
  if (faultFlag == FAULT_NONE) {
    _faultFlags = FAULT_NONE;
  } else {
    _faultFlags |= faultFlag;
  }
}

void SafetyManager::enterBlocked(uint32_t faultFlag) {
  _state = STATE_BLOCKED;
  _armed = false;
  _faultFlags |= faultFlag | FAULT_BLOCKED;
}

bool SafetyManager::armNormal(const VehicleConfig& config, bool pca9685Ok, bool pcntOk, char* reason, size_t reasonSize) {
  if (!pca9685Ok) {
    _faultFlags |= FAULT_PCA9685;
    copyReason(reason, reasonSize, "PCA9685 not detected");
    return false;
  }
  if (!pcntOk) {
    _faultFlags |= FAULT_PCNT;
    copyReason(reason, reasonSize, "PCNT encoder counter not available");
    return false;
  }
  if (config.motion.wheelbaseM <= 0.0f ||
      config.motion.trackWidthM <= 0.0f ||
      config.motion.wheelDiameterM <= 0.0f ||
      config.motion.maxWheelRpm <= 0.0f) {
    _faultFlags |= FAULT_DIMENSIONS_UNSET;
    copyReason(reason, reasonSize, "vehicle dimensions or max rpm unset");
    return false;
  }
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    if (!config.servos[i].calibrated) {
      _faultFlags |= FAULT_UNCALIBRATED_SERVO;
      copyReason(reason, reasonSize, "servo calibration required");
      return false;
    }
    if ((config.pidEnabled || config.motors[i].pidEnabled) &&
        config.encoders[i].countsPerWheelRev == 0 &&
        config.motors[i].countsPerWheelRev == 0) {
      _faultFlags |= FAULT_ENCODER_CPR_UNSET;
      copyReason(reason, reasonSize, "counts_per_wheel_rev required for PID");
      return false;
    }
  }
  _faultFlags = FAULT_NONE;
  _state = STATE_NORMAL;
  _armed = true;
  copyReason(reason, reasonSize, "armed");
  return true;
}

bool SafetyManager::armDebug(char* reason, size_t reasonSize) {
  _faultFlags = FAULT_NONE;
  _state = STATE_DEBUG;
  _armed = true;
  copyReason(reason, reasonSize, "debug armed");
  return true;
}

void SafetyManager::disarm() {
  _state = STATE_SAFE;
  _armed = false;
}

RobotState SafetyManager::state() const {
  return _state;
}

bool SafetyManager::armed() const {
  return _armed;
}

uint32_t SafetyManager::faultFlags() const {
  return _faultFlags;
}

const char* SafetyManager::stateName() const {
  switch (_state) {
    case STATE_NORMAL:
      return "NORMAL";
    case STATE_DEBUG:
      return "DEBUG";
    case STATE_BLOCKED:
      return "BLOCKED";
    default:
      return "SAFE";
  }
}

bool SafetyManager::canApplyDrive() const {
  return _armed && _state == STATE_NORMAL;
}
