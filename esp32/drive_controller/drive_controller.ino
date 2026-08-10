#include <Adafruit_NeoPixel.h>

#define RGB_PIN 15
#define LED_COUNT 1

Adafruit_NeoPixel rgb(LED_COUNT, RGB_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  rgb.begin();
  rgb.clear();
  rgb.show();
}

void loop() {
  rgb.setPixelColor(0, rgb.Color(255, 0, 0)); // 赤
  rgb.show();
  delay(500);

  rgb.setPixelColor(0, rgb.Color(0, 255, 0)); // 緑
  rgb.show();
  delay(500);

  rgb.setPixelColor(0, rgb.Color(0, 0, 255)); // 青
  rgb.show();
  delay(500);
}