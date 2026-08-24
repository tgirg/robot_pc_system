#include <Wire.h>

static const char* SKETCH_NAME = "optical_odometry_test";
static const char* VERSION = "0.3.0";

const int I2C_SDA_PIN = 21;
const int I2C_SCL_PIN = 22;
const uint8_t OPTICAL_ODOM_ADDRESS = 0x17;

const uint8_t REG_PRODUCT_ID = 0x00;
const uint8_t REG_HW_VERSION = 0x01;
const uint8_t REG_FW_VERSION = 0x02;
const uint8_t REG_RESET = 0x07;
const uint8_t REG_STATUS = 0x1F;
const uint8_t REG_POS_X_L = 0x20;
const uint8_t EXPECTED_PRODUCT_ID = 0x5F;

const unsigned long SERIAL_BAUD = 115200;
const unsigned long OUTPUT_INTERVAL_MS = 100;
const unsigned long CHECK_INTERVAL_MS = 1000;
const int32_t MAX_DELTA_COUNT = 2000;
const uint8_t ERROR_LIMIT = 3;

#define DEBUG_OPTICAL 0

bool debugEnabled = DEBUG_OPTICAL;
bool opticalPresent = false;
bool baselineReady = false;
uint8_t consecutiveErrors = 0;
uint8_t lastProductId = 0;
uint8_t lastHwVersion = 0;
uint8_t lastFwVersion = 0;
int16_t lastRawX = 0;
int16_t lastRawY = 0;
int16_t lastRawH = 0;
int32_t totalDxCount = 0;
int32_t totalDyCount = 0;
unsigned long lastOutputMs = 0;
unsigned long lastCheckMs = 0;

bool i2cDeviceExists(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint8_t& value) {
  Wire.beginTransmission(OPTICAL_ODOM_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(OPTICAL_ODOM_ADDRESS, (uint8_t)1) != 1) {
    return false;
  }
  value = Wire.read();
  return true;
}

bool readRegisters(uint8_t reg, uint8_t count, uint8_t* data) {
  Wire.beginTransmission(OPTICAL_ODOM_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(OPTICAL_ODOM_ADDRESS, count) != count) {
    return false;
  }
  for (uint8_t i = 0; i < count; i++) {
    data[i] = Wire.read();
  }
  return true;
}

bool writeRegisters(uint8_t reg, const uint8_t* data, uint8_t count) {
  Wire.beginTransmission(OPTICAL_ODOM_ADDRESS);
  Wire.write(reg);
  for (uint8_t i = 0; i < count; i++) {
    Wire.write(data[i]);
  }
  return Wire.endTransmission() == 0;
}

int16_t combineInt16(uint8_t lowByte, uint8_t highByte) {
  return (int16_t)((uint16_t)highByte << 8 | lowByte);
}

void printHex2(uint8_t value) {
  if (value < 16) Serial.print("0");
  Serial.print(value, HEX);
}

void printRawBytes(const uint8_t* data, uint8_t count) {
  Serial.print("OPTICAL_RAW");
  for (uint8_t i = 0; i < count; i++) {
    Serial.print(",");
    printHex2(data[i]);
  }
  Serial.println();
}

bool readOpticalPoseRaw(int16_t& x, int16_t& y, int16_t& h, bool printRaw) {
  uint8_t data[6] = {0, 0, 0, 0, 0, 0};
  if (!readRegisters(REG_POS_X_L, 6, data)) {
    return false;
  }
  if (printRaw) {
    printRawBytes(data, 6);
  }
  x = combineInt16(data[0], data[1]);
  y = combineInt16(data[2], data[3]);
  h = combineInt16(data[4], data[5]);
  return true;
}

bool writeOpticalPoseZero() {
  const uint8_t zeroPose[6] = {0, 0, 0, 0, 0, 0};
  return writeRegisters(REG_POS_X_L, zeroPose, 6);
}

bool checkOpticalSensor() {
  if (!i2cDeviceExists(OPTICAL_ODOM_ADDRESS)) {
    opticalPresent = false;
    baselineReady = false;
    lastProductId = 0;
    return false;
  }
  uint8_t productId = 0;
  if (!readRegister(REG_PRODUCT_ID, productId)) {
    opticalPresent = false;
    baselineReady = false;
    return false;
  }
  lastProductId = productId;
  readRegister(REG_HW_VERSION, lastHwVersion);
  readRegister(REG_FW_VERSION, lastFwVersion);
  opticalPresent = productId == EXPECTED_PRODUCT_ID;
  if (!opticalPresent) {
    baselineReady = false;
  }
  return opticalPresent;
}

void printOpticalStatus() {
  if (!opticalPresent) {
    Serial.println("OPTICAL_STATUS,UNCONNECTED");
    return;
  }
  uint8_t statusReg = 0;
  if (!readRegister(REG_STATUS, statusReg)) {
    Serial.println("OPTICAL_STATUS,ERROR");
    return;
  }
  bool paaFatal = (statusReg & 0x40) != 0;
  bool opticalWarn = (statusReg & 0x02) != 0;
  if (paaFatal || consecutiveErrors >= ERROR_LIMIT) {
    Serial.println("OPTICAL_STATUS,ERROR");
  } else {
    Serial.println("OPTICAL_STATUS,OK");
  }
  if (debugEnabled) {
    Serial.print("OPTICAL_REG_STATUS,0x");
    printHex2(statusReg);
    Serial.print(",WARN_OPTICAL,");
    Serial.print(opticalWarn ? 1 : 0);
    Serial.print(",ERROR_PAA,");
    Serial.println(paaFatal ? 1 : 0);
  }
}

bool initOpticalSensor() {
  bool ok = checkOpticalSensor();
  Serial.print("OPTICAL_ADDR,0x17,");
  Serial.println(ok ? "FOUND" : "NOT_FOUND");
  if (ok) {
    Serial.print("OPTICAL_PRODUCT,0x");
    printHex2(lastProductId);
    Serial.print(",HW,0x");
    printHex2(lastHwVersion);
    Serial.print(",FW,0x");
    printHex2(lastFwVersion);
    Serial.println();
    int16_t x = 0, y = 0, h = 0;
    if (readOpticalPoseRaw(x, y, h, false)) {
      lastRawX = x;
      lastRawY = y;
      lastRawH = h;
      baselineReady = true;
      consecutiveErrors = 0;
    }
  }
  printOpticalStatus();
  return ok;
}

bool readOpticalDelta(int16_t& dx, int16_t& dy) {
  dx = 0;
  dy = 0;
  if (!opticalPresent) {
    return false;
  }
  int16_t x = 0, y = 0, h = 0;
  if (!readOpticalPoseRaw(x, y, h, debugEnabled)) {
    consecutiveErrors++;
    baselineReady = false;
    return false;
  }
  if (!baselineReady) {
    lastRawX = x;
    lastRawY = y;
    lastRawH = h;
    baselineReady = true;
    consecutiveErrors = 0;
    return true;
  }
  int32_t rawDx = (int32_t)x - (int32_t)lastRawX;
  int32_t rawDy = (int32_t)y - (int32_t)lastRawY;
  lastRawX = x;
  lastRawY = y;
  lastRawH = h;
  if (abs(rawDx) > MAX_DELTA_COUNT || abs(rawDy) > MAX_DELTA_COUNT) {
    consecutiveErrors++;
    return false;
  }
  consecutiveErrors = 0;
  dx = (int16_t)rawDx;
  dy = (int16_t)rawDy;
  totalDxCount += dx;
  totalDyCount += dy;
  return true;
}

void scanI2C() {
  Serial.println("I2C scan start");
  int foundCount = 0;
  for (uint8_t address = 1; address < 127; address++) {
    if (i2cDeviceExists(address)) {
      Serial.print("I2C device found at 0x");
      printHex2(address);
      Serial.println();
      foundCount++;
    }
  }
  if (foundCount == 0) {
    Serial.println("I2C device not found");
  }
  Serial.println("I2C scan done");
}

void zeroOptical() {
  bool wroteZero = opticalPresent && writeOpticalPoseZero();
  int16_t x = 0, y = 0, h = 0;
  if (opticalPresent && readOpticalPoseRaw(x, y, h, false)) {
    lastRawX = x;
    lastRawY = y;
    lastRawH = h;
    baselineReady = true;
  } else {
    baselineReady = false;
  }
  totalDxCount = 0;
  totalDyCount = 0;
  consecutiveErrors = 0;
  Serial.println(wroteZero ? "ZERO,OK" : "ZERO,LOCAL_ONLY");
  Serial.println("OPTICAL,0,0");
}

void printStatusCommand() {
  Serial.println("STATUS,OK");
  printOpticalStatus();
  Serial.print("OPTICAL_TOTAL_COUNT,");
  Serial.print(totalDxCount);
  Serial.print(",");
  Serial.println(totalDyCount);
  Serial.print("OPTICAL_LAST_RAW,");
  Serial.print(lastRawX);
  Serial.print(",");
  Serial.print(lastRawY);
  Serial.print(",");
  Serial.println(lastRawH);
}

void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;
    Serial.print("RX,");
    Serial.println(line);
    if (line == "SCAN") {
      scanI2C();
      initOpticalSensor();
    } else if (line == "STATUS") {
      checkOpticalSensor();
      printStatusCommand();
    } else if (line == "ZERO") {
      zeroOptical();
    } else if (line == "DEBUG ON") {
      debugEnabled = true;
      Serial.println("DEBUG,ON");
    } else if (line == "DEBUG OFF") {
      debugEnabled = false;
      Serial.println("DEBUG,OFF");
    } else {
      Serial.println("ERROR,UNKNOWN_COMMAND");
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(500);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);
  Serial.println("BOOT,OPTICAL_ODOMETRY_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);
  Serial.println("OPTICAL_CONFIG,ADDR=0x17,SDA=21,SCL=22,REG_POS=0x20,FORMAT=INT16_LE_DELTA_COUNT");
  scanI2C();
  initOpticalSensor();
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();

  if (now - lastCheckMs >= CHECK_INTERVAL_MS) {
    lastCheckMs = now;
    checkOpticalSensor();
  }

  if (now - lastOutputMs < OUTPUT_INTERVAL_MS) {
    return;
  }
  lastOutputMs = now;
  Serial.println("STATUS,OK");

  if (!opticalPresent) {
    Serial.println("OPTICAL_STATUS,UNCONNECTED");
    Serial.println("OPTICAL,0,0");
    return;
  }

  int16_t dx = 0;
  int16_t dy = 0;
  if (readOpticalDelta(dx, dy) && consecutiveErrors < ERROR_LIMIT) {
    printOpticalStatus();
    Serial.print("OPTICAL,");
    Serial.print(dx);
    Serial.print(",");
    Serial.println(dy);
  } else {
    printOpticalStatus();
    Serial.println("OPTICAL,0,0");
  }
}
