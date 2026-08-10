// Field sensor demo sketch for dashboard field visualization.
// This sketch does not drive motors. It only prints sensor-format lines.

static const char* SKETCH_NAME = "field_sensor_demo_test";
static const char* VERSION = "0.1.0";

unsigned long lastOutputMs = 0;
float xMm = 0.0;
float yMm = 0.0;
float thetaDeg = 0.0;
long leftEncoder = 0;
long rightEncoder = 0;

void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;

    Serial.print("RX,");
    Serial.println(line);

    line.toUpperCase();
    if (line == "RESET_POSE") {
      xMm = 0.0;
      yMm = 0.0;
      thetaDeg = 0.0;
      leftEncoder = 0;
      rightEncoder = 0;
      Serial.println("POSE_RESET,OK");
    } else if (line == "STATUS") {
      printStatusOnly();
    }
  }
}

void printStatusOnly() {
  Serial.println("STATUS,OK");
  Serial.println("IMU_STATUS,OK");
  Serial.println("LIDAR_STATUS,OK");
  Serial.println("ENC_STATUS,OK");
  Serial.println("ODOM_STATUS,OK");
  Serial.println("DIST_STATUS,OK");
  Serial.println("LINE_STATUS,OK");
  Serial.println("COLOR_STATUS,OK");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("BOOT,FIELD_SENSOR_DEMO_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);
  printStatusOnly();
  Serial.println("COMMANDS,RESET_POSE,STATUS");
}

void loop() {
  handleSerialInput();

  unsigned long now = millis();
  if (now - lastOutputMs < 200) {
    return;
  }
  lastOutputMs = now;

  thetaDeg += 1.5;
  if (thetaDeg >= 360.0) thetaDeg -= 360.0;

  float rad = thetaDeg * 3.14159265 / 180.0;
  float dx = 8.0 * cos(rad);
  float dy = 8.0 * sin(rad);
  xMm += dx;
  yMm += dy;
  leftEncoder += 4;
  rightEncoder += 5;

  printStatusOnly();

  Serial.print("IMU,");
  Serial.print(thetaDeg, 2);
  Serial.println(",0.00,0.00");

  Serial.println("GYRO,0.0000,0.0000,1.5000");

  Serial.print("ODOM,");
  Serial.print(xMm, 2);
  Serial.print(",");
  Serial.print(yMm, 2);
  Serial.print(",");
  Serial.println(thetaDeg, 2);

  Serial.print("OPTICAL,");
  Serial.print(dx, 2);
  Serial.print(",");
  Serial.println(dy, 2);

  Serial.print("ENC,");
  Serial.print(leftEncoder);
  Serial.print(",");
  Serial.println(rightEncoder);

  Serial.println("LIDAR,850,1200,900,1500");
  Serial.println("DIST,front,800");
  Serial.println("LINE,reflection,80");
  Serial.println("COLOR,green");
}
