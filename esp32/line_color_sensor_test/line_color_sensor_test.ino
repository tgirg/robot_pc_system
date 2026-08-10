// Line and color sensor test sketch.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "line_color_sensor_test";
static const char* VERSION = "0.1.0";

unsigned long lastOutputMs = 0;

void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("RX,");
      Serial.println(line);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("BOOT,LINE_COLOR_SENSOR_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);

  // Future notes:
  // Analog line sensor, I2C color sensor, floor line detection thresholds.
  // Confirm sensor voltage and analog range before connecting real parts.
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastOutputMs >= 700) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
    Serial.println("LINE_STATUS,DUMMY");
    Serial.println("LINE,reflection,80");
    Serial.println("COLOR_STATUS,DUMMY");
    Serial.println("COLOR,unknown");
  }
}
