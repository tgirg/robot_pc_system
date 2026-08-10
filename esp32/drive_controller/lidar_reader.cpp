#include "lidar_reader.h"

// LiDAR connection note:
// - UART LiDAR: connect TX/RX according to the sensor voltage and ESP32 serial pins.
// - I2C LiDAR: connect SDA/SCL according to the ESP32 board default pins or explicit Wire.begin(SDA, SCL).
// - Always confirm 3.3V / 5V requirements, GND common, baudrate, and protocol before enabling real LiDAR.

static bool lidarAvailable = false;
static const char* lidarStatus = "DUMMY";
static int frontDistanceMm = 1200;
static int leftDistanceMm = 1200;
static int rightDistanceMm = 1200;
static int rearDistanceMm = 1200;

void initLidar() {
#if USE_REAL_LIDAR
  // TODO: Initialize the actual LiDAR here after selecting the sensor model.
  // TODO: For UART LiDAR, configure a HardwareSerial port and baudrate.
  // TODO: For I2C LiDAR, configure SDA/SCL and sensor address.
  lidarAvailable = false;
  lidarStatus = "ERROR";
#else
  lidarAvailable = false;
  lidarStatus = "DUMMY";
#endif
}

void updateLidar() {
#if USE_REAL_LIDAR
  if (!lidarAvailable) {
    frontDistanceMm = 0;
    leftDistanceMm = 0;
    rightDistanceMm = 0;
    rearDistanceMm = 0;
    lidarStatus = "ERROR";
    return;
  }
  // TODO: Read real LiDAR distance values here.
#else
  frontDistanceMm = 1200;
  leftDistanceMm = 1200;
  rightDistanceMm = 1200;
  rearDistanceMm = 1200;
  lidarStatus = "DUMMY";
#endif
}

bool hasLidar() {
  return lidarAvailable;
}

int getFrontDistanceMm() {
  return frontDistanceMm;
}

int getLeftDistanceMm() {
  return leftDistanceMm;
}

int getRightDistanceMm() {
  return rightDistanceMm;
}

int getRearDistanceMm() {
  return rearDistanceMm;
}

const char* getLidarStatusText() {
  return lidarStatus;
}
