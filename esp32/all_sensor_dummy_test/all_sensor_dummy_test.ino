// All sensor dummy test sketch for PC parser and UI checks.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "all_sensor_dummy_test";
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
  Serial.println("BOOT,ALL_SENSOR_DUMMY_TEST_READY");
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
    Serial.println("IMU_STATUS,DUMMY");
    Serial.println("IMU,0.00,0.00,0.00");
    Serial.println("GYRO,0.0000,0.0000,0.0000");
    Serial.println("LIDAR_STATUS,DUMMY");
    Serial.println("LIDAR,1200,1200,1200,1200");
    Serial.println("ENC_STATUS,DUMMY");
    Serial.println("ENC,0,0");
    Serial.println("ODOM_STATUS,DUMMY");
    Serial.println("ODOM,0,0,0");
    Serial.println("OPTICAL,0,0");
    Serial.println("DIST_STATUS,DUMMY");
    Serial.println("DIST,front,800");
    Serial.println("DIST,left,1200");
    Serial.println("DIST,right,900");
    Serial.println("DIST,rear,1500");
    Serial.println("LINE_STATUS,DUMMY");
    Serial.println("LINE,reflection,80");
    Serial.println("COLOR_STATUS,DUMMY");
    Serial.println("COLOR,unknown");
    Serial.println("MOTOR_DUMMY,0,0");
    Serial.println("DRIVE,0,0");
  }
}
