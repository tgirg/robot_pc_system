// Distance sensor test sketch.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "distance_sensor_test";
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
  Serial.println("BOOT,DISTANCE_SENSOR_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);

  // Future candidates: VL53L0X, VL53L1X, ultrasonic sensors, analog distance sensors.
  // Keep voltage and I2C/UART pin compatibility checked before real sensor testing.
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastOutputMs >= 700) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
    Serial.println("DIST_STATUS,DUMMY");
    Serial.println("DIST,front,800");
    Serial.println("DIST,left,1200");
    Serial.println("DIST,right,900");
    Serial.println("DIST,rear,1500");
  }
}
