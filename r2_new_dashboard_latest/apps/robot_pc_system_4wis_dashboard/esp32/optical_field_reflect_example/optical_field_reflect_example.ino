#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22

#define OPTICAL_ADDR 0x17
#define REG_PRODUCT_ID 0x00
#define REG_POS_X_L 0x20
#define EXPECTED_PRODUCT_ID 0x5F

unsigned long lastPrintMs = 0;

bool sensorOk = false;
bool baselineReady = false;

int16_t lastX = 0;
int16_t lastY = 0;

bool readRegister(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(OPTICAL_ADDR);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(OPTICAL_ADDR, (uint8_t)1) != 1) {
    return false;
  }

  value = Wire.read();
  return true;
}

bool readPosition(int16_t &x, int16_t &y) {
  uint8_t data[6];

  Wire.beginTransmission(OPTICAL_ADDR);
  Wire.write(REG_POS_X_L);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(OPTICAL_ADDR, (uint8_t)6) != 6) {
    return false;
  }

  for (int i = 0; i < 6; i++) {
    data[i] = Wire.read();
  }

  x = (int16_t)((data[1] << 8) | data[0]);
  y = (int16_t)((data[3] << 8) | data[2]);

  return true;
}

bool checkOpticalSensor() {
  uint8_t productId = 0;

  if (!readRegister(REG_PRODUCT_ID, productId)) {
    return false;
  }

  return productId == EXPECTED_PRODUCT_ID;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  Serial.println("BOOT,OPTICAL_REFLECT_READY");
  Serial.println("FW,optical_reflect_minimal,0.1.0");

  sensorOk = checkOpticalSensor();

  if (sensorOk) {
    Serial.println("OPTICAL_STATUS,OK");

    int16_t x = 0;
    int16_t y = 0;

    if (readPosition(x, y)) {
      lastX = x;
      lastY = y;
      baselineReady = true;
    }
  } else {
    Serial.println("OPTICAL_STATUS,UNCONNECTED");
    Serial.println("OPTICAL,0,0");
  }
}

void loop() {
  if (millis() - lastPrintMs < 100) {
    return;
  }

  lastPrintMs = millis();

  sensorOk = checkOpticalSensor();

  if (!sensorOk) {
    baselineReady = false;
    Serial.println("STATUS,OK");
    Serial.println("OPTICAL_STATUS,UNCONNECTED");
    Serial.println("OPTICAL,0,0");
    return;
  }

  int16_t x = 0;
  int16_t y = 0;

  if (!readPosition(x, y)) {
    baselineReady = false;
    Serial.println("STATUS,OK");
    Serial.println("OPTICAL_STATUS,ERROR");
    Serial.println("OPTICAL,0,0");
    return;
  }

  int16_t dx = 0;
  int16_t dy = 0;

  if (baselineReady) {
    dx = x - lastX;
    dy = y - lastY;
  } else {
    baselineReady = true;
  }

  lastX = x;
  lastY = y;

  Serial.println("STATUS,OK");
  Serial.println("OPTICAL_STATUS,OK");

  Serial.print("OPTICAL,");
  Serial.print(dx);
  Serial.print(",");
  Serial.println(dy);
}