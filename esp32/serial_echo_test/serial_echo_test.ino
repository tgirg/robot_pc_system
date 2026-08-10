// Minimal serial echo test sketch.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "serial_echo_test";
static const char* VERSION = "0.1.0";

unsigned long lastOutputMs = 0;

void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("RX,");
      Serial.println(line);
      Serial.print("ECHO,");
      Serial.println(line);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("BOOT,SERIAL_ECHO_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastOutputMs >= 700) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
  }
}
