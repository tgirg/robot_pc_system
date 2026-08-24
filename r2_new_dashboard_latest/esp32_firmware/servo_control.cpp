#include "servo_control.h"
#include <Wire.h>
#include <math.h>

static const float SERVO_FREQ_HZ = 50.0f;
static const uint8_t MODE1 = 0x00;
static const uint8_t MODE2 = 0x01;
static const uint8_t LED0_ON_L = 0x06;
static const uint8_t PRESCALE = 0xFE;

bool Pca9685ServoArray::begin(uint8_t address) {
  _address = address;
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(I2C_CLOCK_HZ);
  _connected = ping();
  if (!_connected) {
    return false;
  }
  write8(MODE1, 0x00);
  write8(MODE2, 0x04);
  delay(10);
  _connected = setPwmFrequency(SERVO_FREQ_HZ);
  _lastUpdateMs = millis();
  return _connected;
}

bool Pca9685ServoArray::connected() const {
  return _connected;
}

uint8_t Pca9685ServoArray::address() const {
  return _address;
}

uint32_t Pca9685ServoArray::failureCount() const {
  return _failureCount;
}

bool Pca9685ServoArray::ping() {
  Wire.beginTransmission(_address);
  return Wire.endTransmission() == 0;
}

bool Pca9685ServoArray::write8(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(_address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

uint8_t Pca9685ServoArray::read8(uint8_t reg) {
  Wire.beginTransmission(_address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return 0;
  }
  Wire.requestFrom((int)_address, 1);
  if (Wire.available() < 1) {
    return 0;
  }
  return Wire.read();
}

bool Pca9685ServoArray::setPwmFrequency(float hz) {
  float prescaleValue = 25000000.0f / 4096.0f / hz - 1.0f;
  uint8_t prescale = (uint8_t)floorf(prescaleValue + 0.5f);
  uint8_t oldMode = read8(MODE1);
  if (!write8(MODE1, (oldMode & 0x7F) | 0x10)) {
    return false;
  }
  if (!write8(PRESCALE, prescale)) {
    return false;
  }
  if (!write8(MODE1, oldMode)) {
    return false;
  }
  delay(5);
  return write8(MODE1, oldMode | 0xA0);
}

bool Pca9685ServoArray::setPwm(uint8_t channel, uint16_t onTick, uint16_t offTick) {
  if (channel >= PCA9685_SERVO_CHANNEL_COUNT) {
    return false;
  }
  Wire.beginTransmission(_address);
  Wire.write(LED0_ON_L + 4 * channel);
  Wire.write(onTick & 0xFF);
  Wire.write(onTick >> 8);
  Wire.write(offTick & 0xFF);
  Wire.write(offTick >> 8);
  return Wire.endTransmission() == 0;
}

bool Pca9685ServoArray::writePulse(uint8_t channel, uint16_t pulseUs) {
  if (!_connected) {
    _connected = ping();
    if (!_connected) {
      _failureCount++;
      return false;
    }
  }
  float periodUs = 1000000.0f / SERVO_FREQ_HZ;
  uint16_t ticks = (uint16_t)roundf(((float)pulseUs * 4096.0f) / periodUs);
  if (ticks > 4095) {
    ticks = 4095;
  }
  bool ok = setPwm(channel, 0, ticks);
  if (!ok) {
    _connected = false;
    _failureCount++;
  }
  return ok;
}

uint16_t Pca9685ServoArray::pulseForAngle(float angleDeg, const ServoConfig& servo) const {
  float physical = servo.inverted ? -angleDeg : angleDeg;
  physical += servo.trimDeg;
  physical = constrain(physical, servo.minAngleDeg, servo.maxAngleDeg);

  if (physical <= 0.0f) {
    float span = 0.0f - servo.minAngleDeg;
    float ratio = span > 0.0f ? (physical - servo.minAngleDeg) / span : 1.0f;
    float pulse = (float)servo.minUs + ((float)servo.centerUs - (float)servo.minUs) * ratio;
    return (uint16_t)roundf(pulse);
  }

  float span = servo.maxAngleDeg;
  float ratio = span > 0.0f ? physical / span : 0.0f;
  float pulse = (float)servo.centerUs + ((float)servo.maxUs - (float)servo.centerUs) * ratio;
  return (uint16_t)roundf(pulse);
}

bool Pca9685ServoArray::setLogicalTargetDeg(uint8_t logical, float angleDeg, const VehicleConfig& config, bool debugAllowed) {
  if (logical >= WHEEL_COUNT) {
    return false;
  }
  const ServoConfig& servo = config.servos[logical];
  if (!servo.calibrated && !debugAllowed) {
    return false;
  }
  _targetDeg[logical] = constrain(angleDeg, servo.minAngleDeg, servo.maxAngleDeg);
  return true;
}

bool Pca9685ServoArray::debugSetLogicalPulse(uint8_t logical, uint16_t pulseUs, const VehicleConfig& config) {
  if (logical >= WHEEL_COUNT) {
    return false;
  }
  const ServoConfig& servo = config.servos[logical];
  pulseUs = constrain(pulseUs, servo.minUs, servo.maxUs);
  return writePulse(servo.channel, pulseUs);
}

void Pca9685ServoArray::safeCenterCalibrated(const VehicleConfig& config) {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    if (config.servos[i].calibrated) {
      _targetDeg[i] = 0.0f;
    }
  }
}

bool Pca9685ServoArray::update(uint32_t nowMs, const VehicleConfig& config) {
  float dt = 0.02f;
  if (_lastUpdateMs != 0 && nowMs >= _lastUpdateMs) {
    dt = (float)(nowMs - _lastUpdateMs) / 1000.0f;
  }
  _lastUpdateMs = nowMs;

  bool allOk = true;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    const ServoConfig& servo = config.servos[i];
    if (!servo.calibrated) {
      continue;
    }
    float maxStep = servo.maxRateDegPerSec * dt;
    float delta = _targetDeg[i] - _currentDeg[i];
    if (delta > maxStep) {
      delta = maxStep;
    } else if (delta < -maxStep) {
      delta = -maxStep;
    }
    float nextDeg = _currentDeg[i] + delta;
    if (writePulse(servo.channel, pulseForAngle(nextDeg, servo))) {
      _currentDeg[i] = nextDeg;
    } else {
      allOk = false;
    }
  }
  return allOk;
}

float Pca9685ServoArray::logicalEstimatedDeg(uint8_t logical) const {
  if (logical >= WHEEL_COUNT) {
    return 0.0f;
  }
  return _currentDeg[logical];
}
