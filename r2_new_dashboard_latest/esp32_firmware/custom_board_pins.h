#pragma once

// Formal GPIO map for the custom ESP32 sensor connector board.
// Connector pin order: SIG, NC, VCC(3.3V), GND.

constexpr int PIN_FL = 13;
constexpr int PIN_FR = 14;
constexpr int PIN_RR = 27;
constexpr int PIN_BR = 26;
constexpr int PIN_BL = 25;
constexpr int PIN_LB = 33;
constexpr int PIN_LF = 32;

constexpr int PIN_US1 = 35;
constexpr int PIN_US2 = 23;

constexpr int CUSTOM_BOARD_DISTANCE_SENSOR_COUNT = 7;
constexpr int CUSTOM_BOARD_ULTRASONIC_SENSOR_COUNT = 2;
constexpr int CUSTOM_BOARD_SENSOR_CONNECTOR_COUNT = 9;

struct CustomBoardSensorPin {
  const char* name;
  int gpio;
  const char* purpose;
  bool inputOnly;
};

constexpr CustomBoardSensorPin CUSTOM_BOARD_SENSOR_PINS[] = {
  {"FL", PIN_FL, "front-left distance sensor", false},
  {"FR", PIN_FR, "front-right distance sensor", false},
  {"RR", PIN_RR, "rear-right-side distance sensor", false},
  {"BR", PIN_BR, "back-right distance sensor", false},
  {"BL", PIN_BL, "back-left distance sensor", false},
  {"LB", PIN_LB, "left-back distance sensor", false},
  {"LF", PIN_LF, "left-front distance sensor", false},
  {"US1", PIN_US1, "ultrasonic sensor 1", true},
  {"US2", PIN_US2, "ultrasonic sensor 2", false},
};

static_assert(
  sizeof(CUSTOM_BOARD_SENSOR_PINS) / sizeof(CUSTOM_BOARD_SENSOR_PINS[0]) ==
    CUSTOM_BOARD_SENSOR_CONNECTOR_COUNT,
  "custom board sensor pin map must define all 9 connectors"
);

