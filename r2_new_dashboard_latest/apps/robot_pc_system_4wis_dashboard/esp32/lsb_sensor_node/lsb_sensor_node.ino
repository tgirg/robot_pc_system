// 2026F3F LSB RevA ver0 serial sensor node.
// This sketch is safe for the current universal-board prototype:
// it reads no actuators, drives no motor pins, and only emits telemetry.

#include <Wire.h>
#include <VL53L1X.h>

static const char* SKETCH_NAME = "lsb_sensor_node";
static const char* VERSION = "0.2.1";
static const char* BOARD_ID = "2026F3F_LSB_REVA_VER0";

static const int PIN_I2C_SDA = 21;
static const int PIN_I2C_SCL = 22;

static const int PIN_US_FRONT_L = 4;
static const int PIN_US_FRONT_R = 13;
static const int PIN_US_RIGHT_F = 14;
static const int PIN_US_RIGHT_R = 25;
static const int PIN_US_REAR_R = 26;
static const int PIN_US_REAR_L = 27;
static const int PIN_US_LEFT_R = 32;
static const int PIN_US_LEFT_F = 33;

static const int PIN_IMU_INT1 = 35;
static const int PIN_IMU_INT2 = 36;
static const int PIN_OPT_INT = 34;

unsigned long lastOutputMs = 0;
uint32_t sequenceNumber = 0;
bool streamEnabled = true;
uint16_t streamIntervalMs = 100;
VL53L1X tofFrontSensor;
bool tofFrontReady = false;
int lastTofFrontMm = 0;

static void printFirmware() {
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);
  Serial.print("LSB,ID,");
  Serial.print(BOARD_ID);
  Serial.print(",");
  Serial.println(VERSION);
}

static void printI2cScan() {
  Serial.print("LSB,I2C");
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
      Serial.print(",0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.print(address, HEX);
      Serial.print(":OK");
    }
  }
  Serial.println();
}

static uint16_t clampStreamInterval(long value) {
  if (value < 100) {
    return 100;
  }
  if (value > 2000) {
    return 2000;
  }
  return (uint16_t)value;
}

static void printRate() {
  Serial.print("LSB,RATE,");
  Serial.println(streamIntervalMs);
}

static bool readI2cRegister8(uint8_t address, uint16_t reg, uint8_t* value) {
  Wire.beginTransmission(address);
  Wire.write((uint8_t)(reg >> 8));
  Wire.write((uint8_t)(reg & 0xFF));
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom((int)address, 1) != 1) {
    return false;
  }
  *value = Wire.read();
  return true;
}

static bool i2cAddressPresent(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

static void printTofProbe() {
  const uint8_t address = 0x29;
  Serial.print("LSB,TOF,0x29");
  if (!i2cAddressPresent(address)) {
    Serial.println(",NG,NOT_FOUND");
    return;
  }

  uint8_t vl53l1xModel = 0;
  uint8_t vl53l0xModel = 0;
  bool hasL1xId = readI2cRegister8(address, 0x010F, &vl53l1xModel);
  bool hasL0xId = readI2cRegister8(address, 0x00C0, &vl53l0xModel);

  Serial.print(",OK");
  Serial.print(",VL53L1X_MODEL=0x");
  if (vl53l1xModel < 16) {
    Serial.print("0");
  }
  Serial.print(vl53l1xModel, HEX);
  Serial.print(",VL53L0X_MODEL=0x");
  if (vl53l0xModel < 16) {
    Serial.print("0");
  }
  Serial.print(vl53l0xModel, HEX);
  if (hasL1xId && vl53l1xModel == 0xEA) {
    Serial.print(",TYPE=VL53L1X");
  } else if (hasL0xId && vl53l0xModel == 0xEE) {
    Serial.print(",TYPE=VL53L0X");
  } else {
    Serial.print(",TYPE=UNKNOWN");
  }
  Serial.print(",READY=");
  Serial.print(tofFrontReady ? "1" : "0");
  Serial.print(",DIST_MM=");
  Serial.print(lastTofFrontMm);
  Serial.println();
}

static void initTofFront() {
  tofFrontReady = false;
  lastTofFrontMm = 0;
  if (!i2cAddressPresent(0x29)) {
    Serial.println("LSB,ERR,TOF_FRONT_NOT_FOUND,0x29");
    return;
  }

  tofFrontSensor.setBus(&Wire);
  tofFrontSensor.setTimeout(120);
  if (!tofFrontSensor.init()) {
    Serial.println("LSB,ERR,TOF_FRONT_INIT_FAILED,0x29");
    return;
  }
  tofFrontSensor.setDistanceMode(VL53L1X::Long);
  tofFrontSensor.setMeasurementTimingBudget(50000);
  tofFrontSensor.startContinuous(100);
  tofFrontReady = true;
  Serial.println("LSB,TOF_FRONT,OK,0x29");
}

static int readTofFrontMm() {
  if (!tofFrontReady) {
    return 0;
  }
  uint16_t distance = tofFrontSensor.read(false);
  if (tofFrontSensor.timeoutOccurred()) {
    Serial.println("LSB,ERR,TOF_FRONT_TIMEOUT,0x29");
    tofFrontReady = false;
    return 0;
  }
  if (distance > 0 && distance < 8190) {
    lastTofFrontMm = (int)distance;
  }
  return lastTofFrontMm;
}

static int readPrototypeDistanceMm(int pin, int fallbackMm) {
  // The current universal-board prototype may not have every LSB sensor mounted.
  // Keep this deterministic until each actual module is wired and its library is selected.
  (void)pin;
  return fallbackMm;
}

static void printSensorSnapshot() {
  const int tofFront = readTofFrontMm();
  const int tofRight = 0;
  const int tofRear = 0;
  const int tofLeft = 0;

  const int usFrontL = readPrototypeDistanceMm(PIN_US_FRONT_L, 800);
  const int usFrontR = readPrototypeDistanceMm(PIN_US_FRONT_R, 820);
  const int usRightF = readPrototypeDistanceMm(PIN_US_RIGHT_F, 900);
  const int usRightR = readPrototypeDistanceMm(PIN_US_RIGHT_R, 920);
  const int usRearR = readPrototypeDistanceMm(PIN_US_REAR_R, 1500);
  const int usRearL = readPrototypeDistanceMm(PIN_US_REAR_L, 1480);
  const int usLeftR = readPrototypeDistanceMm(PIN_US_LEFT_R, 1200);
  const int usLeftF = readPrototypeDistanceMm(PIN_US_LEFT_F, 1180);

  Serial.print("LSB,SENS,");
  Serial.print(sequenceNumber++);
  Serial.print(",tof=");
  Serial.print(tofFront);
  Serial.print("/");
  Serial.print(tofRight);
  Serial.print("/");
  Serial.print(tofRear);
  Serial.print("/");
  Serial.print(tofLeft);
  Serial.print(",us=");
  Serial.print(usFrontL);
  Serial.print("/");
  Serial.print(usFrontR);
  Serial.print("/");
  Serial.print(usRightF);
  Serial.print("/");
  Serial.print(usRightR);
  Serial.print("/");
  Serial.print(usRearR);
  Serial.print("/");
  Serial.print(usRearL);
  Serial.print("/");
  Serial.print(usLeftR);
  Serial.print("/");
  Serial.print(usLeftF);
  Serial.println(",imu=0.0/0.0/0.0");
}

static void handleCommand(const String& command) {
  if (command == "PING") {
    Serial.print("LSB,PONG,");
    Serial.println(millis());
  } else if (command == "ID?") {
    printFirmware();
  } else if (command == "I2C?") {
    printI2cScan();
  } else if (command == "TOF?") {
    printTofProbe();
  } else if (command == "SENS?") {
    printSensorSnapshot();
  } else if (command == "RATE?") {
    printRate();
  } else if (command.startsWith("RATE ")) {
    streamIntervalMs = clampStreamInterval(command.substring(5).toInt());
    printRate();
  } else if (command.startsWith("RATE,")) {
    streamIntervalMs = clampStreamInterval(command.substring(5).toInt());
    printRate();
  } else if (command == "STREAM ON") {
    streamEnabled = true;
    Serial.println("LSB,STATUS,STREAM,OK");
  } else if (command == "STREAM OFF") {
    streamEnabled = false;
    Serial.println("LSB,STATUS,STREAM,OK");
  } else if (command.length() > 0) {
    Serial.print("LSB,ERR,UNKNOWN_COMMAND,");
    Serial.println(command);
  }
}

static void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("RX,");
      Serial.println(line);
      handleCommand(line);
    }
  }
}

void setup() {
  pinMode(PIN_IMU_INT1, INPUT);
  pinMode(PIN_IMU_INT2, INPUT);
  pinMode(PIN_OPT_INT, INPUT);
  pinMode(PIN_US_FRONT_L, INPUT);
  pinMode(PIN_US_FRONT_R, INPUT);
  pinMode(PIN_US_RIGHT_F, INPUT);
  pinMode(PIN_US_RIGHT_R, INPUT);
  pinMode(PIN_US_REAR_R, INPUT);
  pinMode(PIN_US_REAR_L, INPUT);
  pinMode(PIN_US_LEFT_R, INPUT);
  pinMode(PIN_US_LEFT_F, INPUT);

  Serial.begin(115200);
  delay(500);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

  Serial.println("BOOT,LSB_SENSOR_NODE_READY");
  printFirmware();
  printRate();
  printI2cScan();
  initTofFront();
  printTofProbe();
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (streamEnabled && now - lastOutputMs >= streamIntervalMs) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
    printSensorSnapshot();
  }
}
