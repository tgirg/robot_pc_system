#include "serial_protocol.h"
#include "config_storage.h"
#include "safety_manager.h"
#include <math.h>

static const char* NODE_ID = "mcb44_drive_main";
static const char* NODE_BOARD = "MCB44";
static const char* NODE_ROLE = "drive";
static const char* NODE_FIRMWARE = "mcb44_4wis";
static const char* NODE_FIRMWARE_VERSION = "v29";
static const char* NODE_PROTOCOL = "mcb44-json-serial";

void SerialProtocol::begin() {
  _length = 0;
  _buffer[0] = '\0';
}

bool SerialProtocol::poll(IncomingMessage& message) {
  message.type = IN_NONE;
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      if (_length > 0) {
        _buffer[_length] = '\0';
        bool ok = parseLine(_buffer, message);
        _length = 0;
        _buffer[0] = '\0';
        if (ok) {
          return true;
        }
      }
    } else if (_length < RX_BUFFER_SIZE - 1) {
      _buffer[_length++] = c;
    } else {
      _length = 0;
      _buffer[0] = '\0';
      sendFault(FAULT_BAD_COMMAND, "line too long");
    }
  }
  return false;
}

bool SerialProtocol::parseLine(char* line, IncomingMessage& message) {
  StaticJsonDocument<6144> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    sendFault(FAULT_BAD_COMMAND, "bad json");
    return false;
  }

  JsonObjectConst root = doc.as<JsonObjectConst>();
  int version = root["v"] | 0;
  const char* type = root["type"] | "";
  if (version != 1 || type[0] == '\0') {
    sendFault(FAULT_BAD_COMMAND, "missing protocol version or type");
    return false;
  }

  if (strcmp(type, "hello") == 0) {
    message.type = IN_HELLO;
  } else if (strcmp(type, "who_are_you") == 0) {
    message.type = IN_WHO_ARE_YOU;
  } else if (strcmp(type, "config") == 0) {
    char reason[96];
    if (!configFromJson(root, message.config, reason, sizeof(reason))) {
      sendConfigAck(false, reason, 0);
      return false;
    }
    message.type = IN_CONFIG;
  } else if (strcmp(type, "arm") == 0) {
    message.type = IN_ARM;
    const char* mode = root["mode"] | "normal";
    snprintf(message.mode, sizeof(message.mode), "%s", mode);
  } else if (strcmp(type, "disarm") == 0) {
    message.type = IN_DISARM;
  } else if (strcmp(type, "drive") == 0) {
    return parseDrive(root, message);
  } else if (strcmp(type, "debug") == 0) {
    return parseDebug(root, message);
  } else if (strcmp(type, "ping") == 0) {
    message.type = IN_PING;
    message.seq = root["seq"] | 0;
  } else {
    sendFault(FAULT_BAD_COMMAND, "unknown type");
    return false;
  }
  return true;
}

bool SerialProtocol::parseDrive(JsonObjectConst root, IncomingMessage& message) {
  JsonArrayConst steer = root["steer_deg"];
  JsonArrayConst target = root["drive_target"];
  if (steer.size() != WHEEL_COUNT || target.size() != WHEEL_COUNT) {
    sendFault(FAULT_BAD_COMMAND, "drive arrays must have 4 entries");
    return false;
  }

  message.type = IN_DRIVE;
  message.drive.seq = root["seq"] | 0;
  message.drive.armed = root["armed"] | false;
  const char* control = root["control"] | "pwm";
  if (strcmp(control, "rpm") == 0) {
    message.drive.control = CONTROL_RPM;
  } else if (strcmp(control, "pwm") == 0) {
    message.drive.control = CONTROL_PWM;
  } else {
    sendFault(FAULT_BAD_COMMAND, "unknown drive control");
    return false;
  }
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    float angle = steer[i] | 0.0f;
    float value = target[i] | 0.0f;
    if (isnan(angle) || isinf(angle) || isnan(value) || isinf(value)) {
      sendFault(FAULT_BAD_COMMAND, "non-finite drive value");
      return false;
    }
    message.drive.steerDeg[i] = angle;
    message.drive.driveTarget[i] = value;
  }
  return true;
}

bool SerialProtocol::parseDebug(JsonObjectConst root, IncomingMessage& message) {
  message.type = IN_DEBUG;
  const char* action = root["action"] | "";
  if (action[0] == '\0') {
    sendFault(FAULT_BAD_COMMAND, "debug action required");
    return false;
  }
  snprintf(message.debug.action, sizeof(message.debug.action), "%s", action);
  message.debug.wheel = root["wheel"] | 0;
  message.debug.value = root["value"] | 0.0f;
  message.debug.pwm = root["pwm"] | 0;
  message.debug.pulseUs = root["pulse_us"] | 1500;
  message.debug.direction = root["direction"] | true;
  message.debug.commit = root["commit"] | false;
  if (message.debug.wheel >= WHEEL_COUNT) {
    sendFault(FAULT_BAD_COMMAND, "debug wheel must be 0..3");
    return false;
  }
  return true;
}

void SerialProtocol::sendNodeIdentity(bool pcaOk, uint8_t pcaAddress, uint32_t configRevision) {
  StaticJsonDocument<768> doc;
  char efuseMac[17];
  uint64_t mac = ESP.getEfuseMac();
  snprintf(efuseMac, sizeof(efuseMac), "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);

  doc["v"] = 1;
  doc["type"] = "node_identity";
  doc["node_id"] = NODE_ID;
  doc["board"] = NODE_BOARD;
  doc["role"] = NODE_ROLE;
  doc["firmware"] = NODE_FIRMWARE;
  doc["fw_version"] = NODE_FIRMWARE_VERSION;
  doc["protocol"] = NODE_PROTOCOL;
  doc["esp32_efuse_mac"] = efuseMac;
  doc["pca9685_ok"] = pcaOk;
  doc["pca9685_address"] = pcaAddress;
  doc["config_revision"] = configRevision;
  JsonArray capabilities = doc.createNestedArray("capabilities");
  capabilities.add("drive_4wis");
  capabilities.add("encoder");
  capabilities.add("pca9685");
  capabilities.add("debug");
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendHelloAck(bool pcaOk, uint8_t pcaAddress) {
  StaticJsonDocument<384> doc;
  doc["v"] = 1;
  doc["type"] = "hello_ack";
  doc["node_id"] = NODE_ID;
  doc["board"] = NODE_BOARD;
  doc["role"] = NODE_ROLE;
  doc["firmware"] = NODE_FIRMWARE;
  doc["protocol"] = NODE_PROTOCOL;
  doc["pca9685_ok"] = pcaOk;
  doc["pca9685_address"] = pcaAddress;
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendConfigAck(bool ok, const char* reason, uint32_t revision) {
  StaticJsonDocument<256> doc;
  doc["v"] = 1;
  doc["type"] = "config_ack";
  doc["ok"] = ok;
  doc["reason"] = reason;
  doc["config_revision"] = revision;
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendArmAck(bool ok, bool armed, const char* state, const char* reason) {
  StaticJsonDocument<256> doc;
  doc["v"] = 1;
  doc["type"] = "arm_ack";
  doc["ok"] = ok;
  doc["armed"] = armed;
  doc["state"] = state;
  doc["reason"] = reason;
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendFault(uint32_t flags, const char* reason) {
  StaticJsonDocument<256> doc;
  doc["v"] = 1;
  doc["type"] = "fault";
  doc["fault_flags"] = flags;
  doc["reason"] = reason;
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendPong(uint32_t seq) {
  StaticJsonDocument<128> doc;
  doc["v"] = 1;
  doc["type"] = "pong";
  doc["seq"] = seq;
  serializeJson(doc, Serial);
  Serial.println();
}

void SerialProtocol::sendTelemetry(const TelemetrySnapshot& telemetry) {
  StaticJsonDocument<768> doc;
  doc["v"] = 1;
  doc["type"] = "telemetry";
  doc["seq"] = telemetry.seq;
  doc["state"] = telemetry.state;
  doc["armed"] = telemetry.armed;
  JsonArray enc = doc.createNestedArray("encoder_count");
  JsonArray rpm = doc.createNestedArray("wheel_rpm");
  JsonArray pwm = doc.createNestedArray("motor_pwm");
  JsonArray servo = doc.createNestedArray("servo_deg");
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    enc.add(telemetry.encoderCount[i]);
    rpm.add(telemetry.wheelRpm[i]);
    pwm.add(telemetry.motorPwm[i]);
    servo.add(telemetry.servoDeg[i]);
  }
  doc["fault_flags"] = telemetry.faultFlags;
  doc["command_age_ms"] = telemetry.commandAgeMs;
  serializeJson(doc, Serial);
  Serial.println();
}
