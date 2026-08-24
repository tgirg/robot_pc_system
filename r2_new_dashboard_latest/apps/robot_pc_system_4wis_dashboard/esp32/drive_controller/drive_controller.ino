#include <Arduino.h>

#include "imu_reader.h"
#include "lidar_reader.h"
#include "motor_driver.h"

static const char* SKETCH_NAME = "drive_controller";
static const char* VERSION = "0.1.0";
static const unsigned long TELEMETRY_PERIOD_MS = 700;

static String inputLine;
static unsigned long lastTelemetryMs = 0;
static int currentLeftSpeed = 0;
static int currentRightSpeed = 0;

static void printFirmware() {
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);
}

static void printTelemetry() {
  updateImu();
  updateLidar();

  Serial.println("STATUS,OK");

  Serial.print("IMU_STATUS,");
  Serial.println(getImuStatus());
  Serial.print("IMU,");
  Serial.print(getYaw(), 2);
  Serial.print(",");
  Serial.print(getPitch(), 2);
  Serial.print(",");
  Serial.println(getRoll(), 2);
  Serial.print("GYRO,");
  Serial.print(getGyroX(), 4);
  Serial.print(",");
  Serial.print(getGyroY(), 4);
  Serial.print(",");
  Serial.println(getGyroZ(), 4);

  Serial.println("ENC_STATUS,DUMMY");
  Serial.println("ENC,0,0");

  Serial.print("LIDAR_STATUS,");
  Serial.println(getLidarStatusText());
  Serial.print("LIDAR,");
  Serial.print(getFrontDistanceMm());
  Serial.print(",");
  Serial.print(getLeftDistanceMm());
  Serial.print(",");
  Serial.print(getRightDistanceMm());
  Serial.print(",");
  Serial.println(getRearDistanceMm());
}

static bool parseDriveVelocity(const String& line, int* left, int* right) {
  const String prefix = "DRIVE VEL ";
  if (!line.startsWith(prefix)) {
    return false;
  }

  String rest = line.substring(prefix.length());
  rest.trim();
  int spaceIndex = rest.indexOf(' ');
  if (spaceIndex <= 0) {
    return false;
  }

  String leftText = rest.substring(0, spaceIndex);
  String rightText = rest.substring(spaceIndex + 1);
  leftText.trim();
  rightText.trim();
  if (leftText.length() == 0 || rightText.length() == 0) {
    return false;
  }

  *left = leftText.toInt();
  *right = rightText.toInt();
  return true;
}

static void applyStop() {
  currentLeftSpeed = 0;
  currentRightSpeed = 0;
  Serial.println("DRIVE,0,0");
  stopMotors();
}

static void handleCommand(const String& line) {
  if (line == "STATUS") {
    printTelemetry();
    return;
  }

  if (line == "DRIVE STOP" || line == "STOP") {
    applyStop();
    return;
  }

  if (line == "EMERGENCY_STOP") {
    currentLeftSpeed = 0;
    currentRightSpeed = 0;
    Serial.println("EMERGENCY_STOP,OK");
    Serial.println("DRIVE,0,0");
    emergencyStopMotors();
    return;
  }

  int left = 0;
  int right = 0;
  if (parseDriveVelocity(line, &left, &right)) {
    currentLeftSpeed = left;
    currentRightSpeed = right;
    Serial.print("DRIVE,");
    Serial.print(currentLeftSpeed);
    Serial.print(",");
    Serial.println(currentRightSpeed);
    setMotorSpeed(currentLeftSpeed, currentRightSpeed);
    return;
  }

  Serial.print("ERR,UNKNOWN_COMMAND,");
  Serial.println(line);
}

static void handleSerialInput() {
  while (Serial.available()) {
    char ch = static_cast<char>(Serial.read());
    if (ch == '\r') {
      continue;
    }
    if (ch == '\n') {
      inputLine.trim();
      if (inputLine.length() > 0) {
        Serial.print("RX,");
        Serial.println(inputLine);
        handleCommand(inputLine);
      }
      inputLine = "";
      continue;
    }
    inputLine += ch;
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  initMotorDriver();
  initImu();
  initLidar();

  Serial.println("BOOT,DRIVE_CONTROLLER_READY");
  printFirmware();
  printTelemetry();
}

void loop() {
  handleSerialInput();

  unsigned long now = millis();
  if (now - lastTelemetryMs >= TELEMETRY_PERIOD_MS) {
    lastTelemetryMs = now;
    printTelemetry();
  }
}
