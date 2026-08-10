#include "imu_reader.h"

#if USE_REAL_IMU
#include <Wire.h>
#if IMU_TYPE_MPU6050
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
Adafruit_MPU6050 mpu;
#endif
#endif

// MPU6050 wiring note:
// - VCC: 3.3V
// - GND: GND
// - SDA: ESP32 board default SDA, or edit Wire.begin(SDA, SCL)
// - SCL: ESP32 board default SCL, or edit Wire.begin(SDA, SCL)
// ESP32 default I2C pins depend on the board. Edit SDA/SCL if needed.

static bool imuAvailable = false;
static const char* imuStatus = "DUMMY";
static float yawDeg = 0.0;
static float pitchDeg = 0.0;
static float rollDeg = 0.0;
static float gyroX = 0.0;
static float gyroY = 0.0;
static float gyroZ = 0.0;

void initImu() {
#if USE_REAL_IMU
  Wire.begin();
#if IMU_TYPE_MPU6050
  if (mpu.begin()) {
    imuAvailable = true;
    imuStatus = "OK";
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  } else {
    imuAvailable = false;
    imuStatus = "ERROR";
  }
#else
  imuAvailable = false;
  imuStatus = "ERROR";
#endif
#else
  imuAvailable = false;
  imuStatus = "DUMMY";
#endif
}

void updateImu() {
#if USE_REAL_IMU
  if (!imuAvailable) {
    yawDeg = 0.0;
    pitchDeg = 0.0;
    rollDeg = 0.0;
    gyroX = 0.0;
    gyroY = 0.0;
    gyroZ = 0.0;
    return;
  }
#if IMU_TYPE_MPU6050
  sensors_event_t accel;
  sensors_event_t gyro;
  sensors_event_t temp;
  mpu.getEvent(&accel, &gyro, &temp);

  // Placeholder attitude estimate. Replace with calibration/filtering later.
  yawDeg = 0.0;
  pitchDeg = atan2(accel.acceleration.x, accel.acceleration.z) * 180.0 / PI;
  rollDeg = atan2(accel.acceleration.y, accel.acceleration.z) * 180.0 / PI;
  gyroX = gyro.gyro.x;
  gyroY = gyro.gyro.y;
  gyroZ = gyro.gyro.z;
#endif
#else
  yawDeg = 0.0;
  pitchDeg = 0.0;
  rollDeg = 0.0;
  gyroX = 0.0;
  gyroY = 0.0;
  gyroZ = 0.0;
#endif
}

bool hasImu() {
  return imuAvailable;
}

float getYaw() {
  return yawDeg;
}

float getPitch() {
  return pitchDeg;
}

float getRoll() {
  return rollDeg;
}

float getGyroX() {
  return gyroX;
}

float getGyroY() {
  return gyroY;
}

float getGyroZ() {
  return gyroZ;
}

const char* getImuStatus() {
  return imuStatus;
}
