#pragma once

#include <Arduino.h>
#include "board_pins.h"

static const uint16_t CONFIG_SCHEMA_VERSION = 1;
static const uint32_t CONTROL_PERIOD_US = 10000;
static const uint32_t TELEMETRY_PERIOD_MS = 50;
static const uint32_t COMMAND_WARN_MS = 200;
static const uint32_t COMMAND_STOP_MS = 300;
static const uint32_t COMMAND_SAFE_MS = 500;

struct MotorConfig {
  uint8_t physical;
  bool inverted;
  bool pidEnabled;
  float kp;
  float ki;
  float kd;
  float integralLimit;
  float feedForwardStaticPwmPositive;
  float feedForwardStaticPwmNegative;
  float feedForwardPwmPerRpmPositive;
  float feedForwardPwmPerRpmNegative;
  int16_t outputMin;
  int16_t outputMax;
  uint32_t countsPerWheelRev;
};

struct EncoderConfig {
  uint8_t physical;
  bool inverted;
  uint32_t countsPerWheelRev;
};

struct ServoConfig {
  uint8_t channel;
  uint16_t centerUs;
  uint16_t minUs;
  uint16_t maxUs;
  float minAngleDeg;
  float maxAngleDeg;
  float trimDeg;
  bool inverted;
  bool calibrated;
  float maxRateDegPerSec;
};

struct MotionConfig {
  float wheelbaseM;
  float trackWidthM;
  float wheelDiameterM;
  float maxWheelRpm;
  float maxLinearSpeedMps;
  float maxAngularSpeedRadps;
  float translationDeadzone;
  float candidateSwitchHysteresisDeg;
  float servoEndMarginDeg;
  float realignThresholdDeg;
  float alignmentServoRateDegPerSec;
  float alignmentToleranceDeg;
  uint16_t alignmentSettleTimeMs;
  uint16_t alignmentTimeoutMs;
  uint16_t decelTimeMs;
  uint16_t accelTimeMs;
};

struct VehicleConfig {
  uint16_t schemaVersion;
  uint32_t configRevision;
  bool pidEnabled;
  uint8_t pca9685Address;
  MotorConfig motors[WHEEL_COUNT];
  EncoderConfig encoders[WHEEL_COUNT];
  ServoConfig servos[WHEEL_COUNT];
  MotionConfig motion;
};

enum ControlMode : uint8_t {
  CONTROL_PWM = 0,
  CONTROL_RPM = 1
};

struct DriveCommand {
  uint32_t seq;
  bool armed;
  ControlMode control;
  float steerDeg[WHEEL_COUNT];
  float driveTarget[WHEEL_COUNT];
};

struct DebugCommand {
  char action[32];
  uint8_t wheel;
  float value;
  int16_t pwm;
  uint16_t pulseUs;
  bool direction;
  bool commit;
};
