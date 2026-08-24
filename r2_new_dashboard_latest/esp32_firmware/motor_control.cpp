#include "motor_control.h"

#if __has_include(<esp_arduino_version.h>)
  #include <esp_arduino_version.h>
#endif

#ifndef ESP_ARDUINO_VERSION_MAJOR
  #define ESP_ARDUINO_VERSION_MAJOR 2
#endif

static const int16_t PWM_STEP_PER_UPDATE = 80;

void MotorControllerArray::begin() {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    pinMode(MOTOR_PINS[i].dirPin, OUTPUT);
    digitalWrite(MOTOR_PINS[i].dirPin, LOW);
    setupPwm(MOTOR_PINS[i].pwmPin, MOTOR_PINS[i].ledcChannel);
    writePwm(MOTOR_PINS[i].ledcChannel, 0);
  }
  brakeAll();
}

void MotorControllerArray::setupPwm(uint8_t pin, uint8_t channel) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttachChannel(pin, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS, channel);
#else
  ledcSetup(channel, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS);
  ledcAttachPin(pin, channel);
#endif
}

void MotorControllerArray::writePwm(uint8_t channel, uint16_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWriteChannel(channel, duty);
#else
  ledcWrite(channel, duty);
#endif
}

int8_t MotorControllerArray::signOf(int16_t value) const {
  if (value > 0) {
    return 1;
  }
  if (value < 0) {
    return -1;
  }
  return 0;
}

void MotorControllerArray::brakeAll() {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    _targetPhysical[i] = 0;
    _currentPhysical[i] = 0;
    _lastDir[i] = 0;
    writePhysical(i, 0);
  }
}

void MotorControllerArray::setLogicalPwm(uint8_t logical, int16_t pwm, const VehicleConfig& config) {
  if (logical >= WHEEL_COUNT) {
    return;
  }
  uint8_t physical = config.motors[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return;
  }
  pwm = constrain(pwm, -MOTOR_PWM_MAX, MOTOR_PWM_MAX);
  if (config.motors[logical].inverted) {
    pwm = -pwm;
  }
  _targetPhysical[physical] = pwm;
}

void MotorControllerArray::setAllLogicalPwm(const int16_t pwm[WHEEL_COUNT], const VehicleConfig& config) {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    setLogicalPwm(i, pwm[i], config);
  }
}

void MotorControllerArray::update() {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    int16_t target = _targetPhysical[i];
    int16_t current = _currentPhysical[i];
    int8_t targetSign = signOf(target);
    int8_t currentSign = signOf(current);

    if (currentSign != 0 && targetSign != 0 && currentSign != targetSign) {
      target = 0;
    }

    if (target > current + PWM_STEP_PER_UPDATE) {
      current += PWM_STEP_PER_UPDATE;
    } else if (target < current - PWM_STEP_PER_UPDATE) {
      current -= PWM_STEP_PER_UPDATE;
    } else {
      current = target;
    }

    _currentPhysical[i] = current;
    writePhysical(i, current);
  }
}

void MotorControllerArray::writePhysical(uint8_t physical, int16_t signedPwm) {
  if (physical >= WHEEL_COUNT) {
    return;
  }

  const MotorHardwarePin& pin = MOTOR_PINS[physical];
  signedPwm = constrain(signedPwm, -MOTOR_PWM_MAX, MOTOR_PWM_MAX);

  if (signedPwm == 0) {
    writePwm(pin.ledcChannel, 0);
    return;
  }

  int8_t direction = signedPwm > 0 ? 1 : -1;
  if (_lastDir[physical] != direction) {
    writePwm(pin.ledcChannel, 0);
    digitalWrite(pin.dirPin, direction > 0 ? HIGH : LOW);
    _lastDir[physical] = direction;
  }

  writePwm(pin.ledcChannel, (uint16_t)abs(signedPwm));
}

int16_t MotorControllerArray::logicalOutput(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0;
  }
  uint8_t physical = config.motors[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0;
  }
  int16_t value = _currentPhysical[physical];
  return config.motors[logical].inverted ? -value : value;
}

