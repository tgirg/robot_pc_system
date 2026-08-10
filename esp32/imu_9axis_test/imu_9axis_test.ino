#include <Wire.h>
#include <math.h>

#define SDA_PIN 21
#define SCL_PIN 22

#define MPU_ADDR_1 0x68
#define MPU_ADDR_2 0x69

const char* FIRMWARE_NAME = "imu_9axis_test";
const char* FIRMWARE_VERSION = "0.1.0";

uint8_t imuAddress = 0x00;
unsigned long lastPrintTime = 0;
const unsigned long PRINT_INTERVAL_MS = 200;

bool writeRegister(uint8_t addr, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t addr, uint8_t reg, uint8_t count, uint8_t* data) {
  Wire.beginTransmission(addr);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received = Wire.requestFrom(addr, count);
  if (received != count) {
    return false;
  }

  for (uint8_t i = 0; i < count; i++) {
    data[i] = Wire.read();
  }

  return true;
}

int16_t combineBytes(uint8_t highByte, uint8_t lowByte) {
  return (int16_t)((highByte << 8) | lowByte);
}

void scanI2C() {
  Serial.println("I2C scan start");

  int foundCount = 0;

  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("I2C device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      foundCount++;
    }
  }

  if (foundCount == 0) {
    Serial.println("I2C device not found");
  }

  Serial.println("I2C scan done");
}

bool detectIMU() {
  Wire.beginTransmission(MPU_ADDR_1);
  if (Wire.endTransmission() == 0) {
    imuAddress = MPU_ADDR_1;
    return true;
  }

  Wire.beginTransmission(MPU_ADDR_2);
  if (Wire.endTransmission() == 0) {
    imuAddress = MPU_ADDR_2;
    return true;
  }

  imuAddress = 0x00;
  return false;
}

bool initMPU() {
  if (!detectIMU()) {
    return false;
  }

  // Wake up MPU
  if (!writeRegister(imuAddress, 0x6B, 0x00)) {
    return false;
  }

  delay(100);

  // Gyro ±250 deg/s
  writeRegister(imuAddress, 0x1B, 0x00);

  // Accel ±2g
  writeRegister(imuAddress, 0x1C, 0x00);

  return true;
}

bool readMPU(float& ax, float& ay, float& az, float& gx, float& gy, float& gz) {
  uint8_t data[14];

  // ACCEL_XOUT_H = 0x3B
  if (!readRegisters(imuAddress, 0x3B, 14, data)) {
    return false;
  }

  int16_t rawAx = combineBytes(data[0], data[1]);
  int16_t rawAy = combineBytes(data[2], data[3]);
  int16_t rawAz = combineBytes(data[4], data[5]);

  int16_t rawGx = combineBytes(data[8], data[9]);
  int16_t rawGy = combineBytes(data[10], data[11]);
  int16_t rawGz = combineBytes(data[12], data[13]);

  // ±2g: 16384 LSB/g
  ax = rawAx / 16384.0;
  ay = rawAy / 16384.0;
  az = rawAz / 16384.0;

  // ±250 deg/s: 131 LSB/(deg/s)
  gx = rawGx / 131.0;
  gy = rawGy / 131.0;
  gz = rawGz / 131.0;

  return true;
}

void handleSerialCommand() {
  if (!Serial.available()) return;

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (command.length() == 0) return;

  Serial.print("RX,");
  Serial.println(command);

  if (command == "STATUS") {
    Serial.println("STATUS,OK");
  } else if (command == "SCAN") {
    scanI2C();
  } else if (command == "RESET_IMU") {
    if (initMPU()) {
      Serial.println("IMU_STATUS,OK");
    } else {
      Serial.println("IMU_STATUS,ERROR");
    }
  } else {
    Serial.print("ECHO,");
    Serial.println(command);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println("BOOT,IMU_9AXIS_TEST_READY");

  Serial.print("FW,");
  Serial.print(FIRMWARE_NAME);
  Serial.print(",");
  Serial.println(FIRMWARE_VERSION);

  scanI2C();

  if (initMPU()) {
    Serial.print("IMU_ADDR,0x");
    if (imuAddress < 16) Serial.print("0");
    Serial.println(imuAddress, HEX);
    Serial.println("IMU_STATUS,OK");
  } else {
    Serial.println("IMU_ADDR,NONE");
    Serial.println("IMU_STATUS,ERROR");
  }
}

void loop() {
  handleSerialCommand();

  unsigned long now = millis();

  if (now - lastPrintTime >= PRINT_INTERVAL_MS) {
    lastPrintTime = now;

    if (imuAddress == 0x00) {
      Serial.println("STATUS,OK");
      Serial.println("IMU_STATUS,ERROR");
      Serial.println("IMU,0.00,0.00,0.00");
      Serial.println("GYRO,0.0000,0.0000,0.0000");
      return;
    }

    float ax, ay, az;
    float gx, gy, gz;

    if (readMPU(ax, ay, az, gx, gy, gz)) {
      float roll = atan2(ay, az) * 180.0 / PI;
      float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;

      // 磁気センサはまだ使っていないのでyawは0
      float yaw = 0.0;

      Serial.println("STATUS,OK");
      Serial.println("IMU_STATUS,OK");

      Serial.print("ACC,");
      Serial.print(ax, 4);
      Serial.print(",");
      Serial.print(ay, 4);
      Serial.print(",");
      Serial.println(az, 4);

      Serial.print("IMU,");
      Serial.print(yaw, 2);
      Serial.print(",");
      Serial.print(pitch, 2);
      Serial.print(",");
      Serial.println(roll, 2);

      Serial.print("GYRO,");
      Serial.print(gx, 4);
      Serial.print(",");
      Serial.print(gy, 4);
      Serial.print(",");
      Serial.println(gz, 4);
    } else {
      Serial.println("STATUS,OK");
      Serial.println("IMU_STATUS,ERROR");
      Serial.println("ACC,0.0000,0.0000,0.0000");
      Serial.println("IMU,0.00,0.00,0.00");
      Serial.println("GYRO,0.0000,0.0000,0.0000");
    }
  }
}