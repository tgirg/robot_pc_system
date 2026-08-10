#include <Adafruit_NeoPixel.h>

#define RGB_PIN 15
#define LED_COUNT 1

Adafruit_NeoPixel rgb(LED_COUNT, RGB_PIN, NEO_GRB + NEO_KHZ800);

const char* FIRMWARE_NAME = "neopixel_test";
const char* FIRMWARE_VERSION = "0.2.0";
const unsigned long SERIAL_BAUDRATE = 115200;
const unsigned long COLOR_INTERVAL_MS = 500;

unsigned long lastChangeTime = 0;
int colorMode = 0;

void setColor(uint8_t r, uint8_t g, uint8_t b, const char* name) {
  rgb.setPixelColor(0, rgb.Color(r, g, b));
  rgb.show();

  Serial.print("RGB,");
  Serial.print(name);
  Serial.print(",");
  Serial.print(r);
  Serial.print(",");
  Serial.print(g);
  Serial.print(",");
  Serial.println(b);
}

void printStatus() {
  Serial.println("STATUS,OK");
  Serial.println("NEOPIXEL_STATUS,OK");
  Serial.print("RGB_PIN,");
  Serial.println(RGB_PIN);
  Serial.print("LED_COUNT,");
  Serial.println(LED_COUNT);
}

void handleSerialCommand() {
  if (!Serial.available()) return;

  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toUpperCase();

  if (command.length() == 0) return;

  Serial.print("RX,");
  Serial.println(command);

  if (command == "RED") {
    setColor(255, 0, 0, "RED");
  } else if (command == "GREEN") {
    setColor(0, 255, 0, "GREEN");
  } else if (command == "BLUE") {
    setColor(0, 0, 255, "BLUE");
  } else if (command == "OFF") {
    setColor(0, 0, 0, "OFF");
  } else if (command == "STATUS") {
    printStatus();
  } else {
    Serial.println("ERROR,UNKNOWN_COMMAND");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(500);

  rgb.begin();
  rgb.clear();
  rgb.show();

  Serial.println("BOOT,NEOPIXEL_TEST_READY");
  Serial.print("FW,");
  Serial.print(FIRMWARE_NAME);
  Serial.print(",");
  Serial.println(FIRMWARE_VERSION);
  printStatus();
}

void loop() {
  handleSerialCommand();

  unsigned long now = millis();
  if (now - lastChangeTime < COLOR_INTERVAL_MS) {
    return;
  }
  lastChangeTime = now;

  if (colorMode == 0) {
    setColor(255, 0, 0, "RED");
  } else if (colorMode == 1) {
    setColor(0, 255, 0, "GREEN");
  } else {
    setColor(0, 0, 255, "BLUE");
  }

  colorMode++;
  if (colorMode >= 3) {
    colorMode = 0;
  }
}
