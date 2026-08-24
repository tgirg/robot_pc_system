#include <Arduino.h>
#include <math.h>
#include "board_pins.h"
#include "vehicle_config.h"
#include "motor_control.h"
#include "encoder_control.h"
#include "servo_control.h"
#include "pid_controller.h"
#include "config_storage.h"
#include "serial_protocol.h"
#include "safety_manager.h"
#include "external_estop.h"

VehicleConfig activeConfig;
MotorControllerArray motors;
EncoderArray encoders;
Pca9685ServoArray servos;
PidController pid[WHEEL_COUNT];
SerialProtocol protocol;
SafetyManager safety;

uint32_t lastControlUs = 0;
uint32_t lastTelemetryMs = 0;
uint32_t lastDriveMs = 0;
uint32_t lastDriveSeq = 0;
uint32_t telemetrySeq = 0;
DriveCommand currentDrive;
bool haveDrive = false;

static void zeroDriveCommand() {
  currentDrive.seq = 0;
  currentDrive.armed = false;
  currentDrive.control = CONTROL_PWM;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    currentDrive.steerDeg[i] = 0.0f;
    currentDrive.driveTarget[i] = 0.0f;
  }
  haveDrive = false;
}

static bool driveTargetsAreZero(const DriveCommand& drive) {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    if (fabsf(drive.driveTarget[i]) >= 0.01f) {
      return false;
    }
  }
  return true;
}

static void forceZeroMotorOutput() {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    currentDrive.driveTarget[i] = 0.0f;
    pid[i].reset();
  }
  motors.brakeAll();
}

static void holdMotorsForServoAlignment() {
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    pid[i].reset();
  }
  motors.brakeAll();
}

static bool steeringAlignedForDrive() {
  if (!servos.connected()) {
    return false;
  }
  float tolerance = activeConfig.motion.alignmentToleranceDeg;
  if (tolerance <= 0.0f) {
    tolerance = 8.0f;
  }
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    const ServoConfig& servo = activeConfig.servos[i];
    if (!servo.calibrated) {
      return false;
    }
    float target = constrain(currentDrive.steerDeg[i], servo.minAngleDeg, servo.maxAngleDeg);
    float error = fabsf(target - servos.logicalEstimatedDeg(i));
    if (error > tolerance) {
      return false;
    }
  }
  return true;
}

static void enterSafe(uint32_t faultFlag) {
  safety.enterSafe(faultFlag);
  zeroDriveCommand();
  forceZeroMotorOutput();
  servos.safeCenterCalibrated(activeConfig);
}

static void applyDebugCommand(const DebugCommand& debug) {
  int16_t pwm[WHEEL_COUNT] = {0, 0, 0, 0};
  const int16_t debugLimit = 120;

  if (strcmp(debug.action, "motor_test") == 0) {
    int16_t command = constrain(debug.pwm, -debugLimit, debugLimit);
    if (!debug.direction) {
      command = -abs(command);
    }
    pwm[debug.wheel] = command;
    motors.setAllLogicalPwm(pwm, activeConfig);
  } else if (strcmp(debug.action, "motor_stop") == 0) {
    motors.brakeAll();
  } else if (strcmp(debug.action, "encoder_zero") == 0) {
    encoders.resetLogical(debug.wheel, activeConfig);
  } else if (strcmp(debug.action, "servo_us") == 0) {
    if (!servos.debugSetLogicalPulse(debug.wheel, debug.pulseUs, activeConfig)) {
      enterSafe(FAULT_PCA9685);
      protocol.sendFault(FAULT_PCA9685, "pca9685 write failed");
    }
  } else if (strcmp(debug.action, "servo_deg") == 0) {
    servos.setLogicalTargetDeg(debug.wheel, debug.value, activeConfig, true);
  } else if (strcmp(debug.action, "servo_calibrated") == 0 && debug.commit) {
    activeConfig.servos[debug.wheel].calibrated = true;
    activeConfig.configRevision++;
    if (!saveConfigToNvs(activeConfig)) {
      protocol.sendFault(FAULT_CONFIG, "nvs save failed");
    }
  } else if (strcmp(debug.action, "counts_commit") == 0 && debug.commit && debug.value > 0.0f) {
    uint32_t counts = (uint32_t)lroundf(debug.value);
    activeConfig.encoders[debug.wheel].countsPerWheelRev = counts;
    activeConfig.motors[debug.wheel].countsPerWheelRev = counts;
    activeConfig.configRevision++;
    if (!saveConfigToNvs(activeConfig)) {
      protocol.sendFault(FAULT_CONFIG, "nvs save failed");
    }
  }
}

static void handleIncoming(const IncomingMessage& msg) {
  char reason[96];
  switch (msg.type) {
    case IN_HELLO:
      protocol.sendHelloAck(servos.connected(), activeConfig.pca9685Address);
      break;

    case IN_WHO_ARE_YOU:
      protocol.sendNodeIdentity(servos.connected(), activeConfig.pca9685Address, activeConfig.configRevision);
      break;

    case IN_CONFIG:
    {
      VehicleConfig candidate = msg.config;
      candidate.configRevision++;
      bool addressChanged = candidate.pca9685Address != activeConfig.pca9685Address;
      bool pcaOk = servos.connected();
      uint8_t previousAddress = activeConfig.pca9685Address;
      if (addressChanged || !pcaOk) {
        pcaOk = servos.begin(candidate.pca9685Address);
      }
      if (!pcaOk) {
        if (addressChanged) {
          servos.begin(previousAddress);
        }
        protocol.sendConfigAck(false, "pca9685 init failed", activeConfig.configRevision);
        enterSafe(FAULT_PCA9685);
        break;
      }
      if (!saveConfigToNvs(candidate)) {
        if (addressChanged) {
          servos.begin(previousAddress);
        }
        protocol.sendConfigAck(false, "nvs save failed", activeConfig.configRevision);
        enterSafe(FAULT_CONFIG);
        break;
      }
      activeConfig = candidate;
      protocol.sendConfigAck(true, "stored", activeConfig.configRevision);
      lastDriveSeq = 0;
      enterSafe(FAULT_NONE);
      break;
    }

    case IN_ARM:
      if (strcmp(msg.mode, "debug") == 0 || strcmp(msg.mode, "DEBUG") == 0) {
        safety.armDebug(reason, sizeof(reason));
        lastDriveSeq = 0;
        haveDrive = false;
        lastDriveMs = millis();
        protocol.sendArmAck(true, safety.armed(), safety.stateName(), reason);
      } else if (safety.armNormal(activeConfig, servos.connected(), encoders.pcntReady(), reason, sizeof(reason))) {
        lastDriveSeq = 0;
        haveDrive = false;
        lastDriveMs = millis();
        protocol.sendArmAck(true, safety.armed(), safety.stateName(), reason);
      } else {
        protocol.sendArmAck(false, safety.armed(), safety.stateName(), reason);
      }
      break;

    case IN_DISARM:
      enterSafe(FAULT_NONE);
      protocol.sendArmAck(true, false, safety.stateName(), "disarmed");
      break;

    case IN_DRIVE:
      if (msg.drive.seq <= lastDriveSeq) {
        protocol.sendFault(FAULT_BAD_COMMAND, "stale drive seq");
        enterSafe(FAULT_BAD_COMMAND);
        break;
      }
      lastDriveSeq = msg.drive.seq;
      if (!msg.drive.armed) {
        enterSafe(FAULT_NONE);
        break;
      }
      if (safety.canApplyDrive()) {
        currentDrive = msg.drive;
        haveDrive = true;
        lastDriveMs = millis();
      }
      break;

    case IN_DEBUG:
      if (safety.armed() && safety.state() == STATE_DEBUG) {
        applyDebugCommand(msg.debug);
        lastDriveMs = millis();
      } else {
        protocol.sendFault(FAULT_BAD_COMMAND, "debug command requires DEBUG arm");
      }
      break;

    case IN_PING:
      protocol.sendPong(msg.seq);
      break;

    default:
      break;
  }
}

static void updateSafetyTimeouts(uint32_t nowMs) {
  if (!safety.armed()) {
    return;
  }
  uint32_t age = nowMs - lastDriveMs;
  if (age >= COMMAND_SAFE_MS) {
    enterSafe(FAULT_COMMAND_TIMEOUT);
  } else if (age >= COMMAND_STOP_MS) {
    forceZeroMotorOutput();
  }
}

static void updateControl(uint32_t nowUs) {
  float dt = (float)(nowUs - lastControlUs) / 1000000.0f;
  lastControlUs = nowUs;
  encoders.updateVelocity(dt);

  if (safety.armed() && safety.state() == STATE_DEBUG) {
    motors.update();
    if (!servos.update(millis(), activeConfig)) {
      enterSafe(FAULT_PCA9685);
      protocol.sendFault(FAULT_PCA9685, "pca9685 write failed");
    }
    return;
  }

  int16_t pwm[WHEEL_COUNT] = {0, 0, 0, 0};
  bool shouldForceZero = !safety.canApplyDrive() || !haveDrive;
  bool waitingForSteering = false;
  if (safety.canApplyDrive() && haveDrive) {
    for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
      servos.setLogicalTargetDeg(i, currentDrive.steerDeg[i], activeConfig, false);
    }

    shouldForceZero = driveTargetsAreZero(currentDrive);
    if (!shouldForceZero) {
      waitingForSteering = !steeringAlignedForDrive();
      if (!waitingForSteering) {
        for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
          if (currentDrive.control == CONTROL_PWM || !activeConfig.pidEnabled) {
            pwm[i] = constrain((int16_t)lroundf(currentDrive.driveTarget[i]), -MOTOR_PWM_MAX, MOTOR_PWM_MAX);
          } else {
            pwm[i] = pid[i].update(
              currentDrive.driveTarget[i],
              encoders.logicalRpm(i, activeConfig),
              activeConfig.motors[i],
              dt
            );
          }
        }
      }
    }
  }
  if (shouldForceZero) {
    forceZeroMotorOutput();
  } else if (waitingForSteering) {
    holdMotorsForServoAlignment();
  } else {
    motors.setAllLogicalPwm(pwm, activeConfig);
    motors.update();
  }
  if (!servos.update(millis(), activeConfig)) {
    enterSafe(FAULT_PCA9685);
    protocol.sendFault(FAULT_PCA9685, "pca9685 write failed");
  }
}

static void sendTelemetry(uint32_t nowMs) {
  TelemetrySnapshot snapshot;
  snapshot.seq = telemetrySeq++;
  snapshot.state = safety.stateName();
  snapshot.armed = safety.armed();
  snapshot.faultFlags = safety.faultFlags();
  snapshot.commandAgeMs = nowMs - lastDriveMs;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    snapshot.encoderCount[i] = encoders.logicalCount(i, activeConfig);
    snapshot.wheelRpm[i] = encoders.logicalRpm(i, activeConfig);
    snapshot.motorPwm[i] = motors.logicalOutput(i, activeConfig);
    snapshot.servoDeg[i] = servos.logicalEstimatedDeg(i);
  }
  protocol.sendTelemetry(snapshot);
}

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(200);

  setDefaultConfig(activeConfig);
  loadConfigFromNvs(activeConfig);
  zeroDriveCommand();

  safety.begin();
  motors.begin();
  encoders.begin();
  motors.brakeAll();
  servos.begin(activeConfig.pca9685Address);
  servos.safeCenterCalibrated(activeConfig);
  protocol.begin();

  lastControlUs = micros();
  lastDriveMs = millis();
  lastTelemetryMs = millis();
}

void loop() {
  IncomingMessage msg;
  while (protocol.poll(msg)) {
    handleIncoming(msg);
  }

  updateExternalEStop();
  if (externalEStopActive()) {
    enterSafe(FAULT_EXTERNAL_ESTOP);
  }

  uint32_t nowMs = millis();
  updateSafetyTimeouts(nowMs);

  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastControlUs) >= CONTROL_PERIOD_US) {
    updateControl(nowUs);
  }

  if (nowMs - lastTelemetryMs >= TELEMETRY_PERIOD_MS) {
    lastTelemetryMs = nowMs;
    sendTelemetry(nowMs);
  }
}
