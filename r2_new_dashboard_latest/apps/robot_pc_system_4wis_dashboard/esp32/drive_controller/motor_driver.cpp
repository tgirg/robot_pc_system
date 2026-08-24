#include "motor_driver.h"

// TODO: Set these pins for the actual motor driver after wiring is confirmed.
// Example placeholders:
// const int LEFT_PWM_PIN = 25;
// const int LEFT_DIR_PIN = 26;
// const int RIGHT_PWM_PIN = 27;
// const int RIGHT_DIR_PIN = 14;
// const int MOTOR_ENABLE_PIN = 13;

static int lastLeftSpeed = 0;
static int lastRightSpeed = 0;

void printDummyMotorOutput(int left, int right) {
  Serial.print("MOTOR_DUMMY,");
  Serial.print(left);
  Serial.print(",");
  Serial.println(right);
}

void initMotorDriver() {
#if MOTOR_OUTPUT_ENABLED
  // TODO: Configure motor driver pins with pinMode().
  // TODO: Configure PWM channels for the selected ESP32 board.
  // TODO: Keep the motor enable pin disabled until safety checks pass.
#else
  printDummyMotorOutput(0, 0);
#endif
}

void setMotorSpeed(int left, int right) {
  lastLeftSpeed = left;
  lastRightSpeed = right;
#if MOTOR_OUTPUT_ENABLED
  // TODO: Convert signed left/right speed to direction + PWM output.
  // TODO: Clamp PWM range and apply dead-zone handling if needed.
#else
  printDummyMotorOutput(lastLeftSpeed, lastRightSpeed);
#endif
}

void stopMotors() {
  lastLeftSpeed = 0;
  lastRightSpeed = 0;
#if MOTOR_OUTPUT_ENABLED
  // TODO: Write PWM 0 to both motors.
#else
  printDummyMotorOutput(0, 0);
#endif
}

void emergencyStopMotors() {
  lastLeftSpeed = 0;
  lastRightSpeed = 0;
#if MOTOR_OUTPUT_ENABLED
  // TODO: Immediately write PWM 0 and disable the motor driver if possible.
#else
  printDummyMotorOutput(0, 0);
#endif
}
