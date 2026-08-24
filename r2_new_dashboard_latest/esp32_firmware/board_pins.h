#pragma once

#include <Arduino.h>

static const uint8_t WHEEL_COUNT = 4;
static const uint8_t PCA9685_SERVO_CHANNEL_COUNT = 16;

enum WheelLogicalIndex : uint8_t {
  WHEEL_FL = 0,
  WHEEL_FR = 1,
  WHEEL_RL = 2,
  WHEEL_RR = 3
};

static const char* const WHEEL_NAMES[WHEEL_COUNT] = {
  "FL", "FR", "RL", "RR"
};

struct MotorHardwarePin {
  const char* name;
  uint8_t pwmPin;
  uint8_t dirPin;
  uint8_t ledcChannel;
};

struct EncoderHardwarePin {
  const char* name;
  uint8_t pinA;
  uint8_t pinB;
};

static const MotorHardwarePin MOTOR_PINS[WHEEL_COUNT] = {
  { "M1", 19, 14, 0 },
  { "M2", 27, 23, 1 },
  { "M3", 25, 26, 2 },
  { "M4", 18, 16, 3 }
};

static const EncoderHardwarePin ENCODER_PINS[WHEEL_COUNT] = {
  { "ENC1", 35, 34 },
  { "ENC2", 36, 39 },
  { "ENC3", 4, 13 },
  { "ENC4", 33, 32 }
};

static const uint8_t I2C_SDA_PIN = 21;
static const uint8_t I2C_SCL_PIN = 22;

static const uint32_t SERIAL_BAUDRATE = 115200;
static const uint32_t I2C_CLOCK_HZ = 400000;
static const uint8_t DEFAULT_PCA9685_ADDRESS = 0x40;

static const uint32_t MOTOR_PWM_FREQUENCY_HZ = 20000;
static const uint8_t MOTOR_PWM_RESOLUTION_BITS = 10;
static const int16_t MOTOR_PWM_MAX = (1 << MOTOR_PWM_RESOLUTION_BITS) - 1;
