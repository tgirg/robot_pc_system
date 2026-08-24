#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include "vehicle_config.h"

enum IncomingType : uint8_t {
  IN_NONE = 0,
  IN_HELLO,
  IN_CONFIG,
  IN_ARM,
  IN_DISARM,
  IN_DRIVE,
  IN_DEBUG,
  IN_PING,
  IN_WHO_ARE_YOU
};

struct IncomingMessage {
  IncomingType type = IN_NONE;
  VehicleConfig config;
  DriveCommand drive;
  DebugCommand debug;
  char mode[12] = {0};
  uint32_t seq = 0;
};

struct TelemetrySnapshot {
  uint32_t seq;
  const char* state;
  bool armed;
  int32_t encoderCount[WHEEL_COUNT];
  float wheelRpm[WHEEL_COUNT];
  int16_t motorPwm[WHEEL_COUNT];
  float servoDeg[WHEEL_COUNT];
  uint32_t faultFlags;
  uint32_t commandAgeMs;
};

class SerialProtocol {
public:
  void begin();
  bool poll(IncomingMessage& message);
  void sendNodeIdentity(bool pcaOk, uint8_t pcaAddress, uint32_t configRevision);
  void sendHelloAck(bool pcaOk, uint8_t pcaAddress);
  void sendConfigAck(bool ok, const char* reason, uint32_t revision);
  void sendArmAck(bool ok, bool armed, const char* state, const char* reason);
  void sendFault(uint32_t flags, const char* reason);
  void sendPong(uint32_t seq);
  void sendTelemetry(const TelemetrySnapshot& telemetry);

private:
  static const size_t RX_BUFFER_SIZE = 4096;
  char _buffer[RX_BUFFER_SIZE];
  size_t _length = 0;

  bool parseLine(char* line, IncomingMessage& message);
  bool parseDrive(JsonObjectConst root, IncomingMessage& message);
  bool parseDebug(JsonObjectConst root, IncomingMessage& message);
};
