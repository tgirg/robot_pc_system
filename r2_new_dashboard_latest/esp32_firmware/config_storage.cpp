#include "config_storage.h"
#include <Preferences.h>
#include <math.h>

static const char* NVS_NAMESPACE = "mcb44ctrl";
static const char* NVS_CONFIG_KEY = "config_json";
static const uint8_t DEFAULT_MOTOR_PHYSICAL[WHEEL_COUNT] = {2, 1, 3, 0};
static const uint8_t DEFAULT_ENCODER_PHYSICAL[WHEEL_COUNT] = {0, 1, 2, 3};
static const uint8_t DEFAULT_SERVO_CHANNELS[WHEEL_COUNT] = {6, 5, 7, 4};
static const uint16_t DEFAULT_SERVO_CENTER_US[WHEEL_COUNT] = {1490, 1580, 1590, 1550};
static const bool DEFAULT_SERVO_INVERTED[WHEEL_COUNT] = {true, true, true, true};

static void setError(char* error, size_t errorSize, const char* message) {
  if (error != nullptr && errorSize > 0) {
    snprintf(error, errorSize, "%s", message);
  }
}

static bool finiteFloat(float value) {
  return !isnan(value) && !isinf(value);
}

void setDefaultConfig(VehicleConfig& config) {
  config.schemaVersion = CONFIG_SCHEMA_VERSION;
  config.configRevision = 1;
  config.pidEnabled = false;
  config.pca9685Address = DEFAULT_PCA9685_ADDRESS;

  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    config.motors[i].physical = DEFAULT_MOTOR_PHYSICAL[i];
    config.motors[i].inverted = true;
    config.motors[i].pidEnabled = false;
    config.motors[i].kp = 0.0f;
    config.motors[i].ki = 0.0f;
    config.motors[i].kd = 0.0f;
    config.motors[i].integralLimit = 500.0f;
    config.motors[i].feedForwardStaticPwmPositive = 0.0f;
    config.motors[i].feedForwardStaticPwmNegative = 0.0f;
    config.motors[i].feedForwardPwmPerRpmPositive = 0.0f;
    config.motors[i].feedForwardPwmPerRpmNegative = 0.0f;
    config.motors[i].outputMin = -MOTOR_PWM_MAX;
    config.motors[i].outputMax = MOTOR_PWM_MAX;
    config.motors[i].countsPerWheelRev = 0;

    config.encoders[i].physical = DEFAULT_ENCODER_PHYSICAL[i];
    config.encoders[i].inverted = false;
    config.encoders[i].countsPerWheelRev = 0;

    config.servos[i].channel = DEFAULT_SERVO_CHANNELS[i];
    config.servos[i].centerUs = DEFAULT_SERVO_CENTER_US[i];
    config.servos[i].minUs = 500;
    config.servos[i].maxUs = 2500;
    config.servos[i].minAngleDeg = -135.0f;
    config.servos[i].maxAngleDeg = 135.0f;
    config.servos[i].trimDeg = 0.0f;
    config.servos[i].inverted = DEFAULT_SERVO_INVERTED[i];
    config.servos[i].calibrated = false;
    config.servos[i].maxRateDegPerSec = 360.0f;
  }

  config.motion.wheelbaseM = 0.327f;
  config.motion.trackWidthM = 0.327f;
  config.motion.wheelDiameterM = 0.055f;
  config.motion.maxWheelRpm = 520.0f;
  config.motion.maxLinearSpeedMps = 1.5f;
  config.motion.maxAngularSpeedRadps = 4.0f;
  config.motion.translationDeadzone = 0.12f;
  config.motion.candidateSwitchHysteresisDeg = 20.0f;
  config.motion.servoEndMarginDeg = 10.0f;
  config.motion.realignThresholdDeg = 30.0f;
  config.motion.alignmentServoRateDegPerSec = 180.0f;
  config.motion.alignmentToleranceDeg = 5.0f;
  config.motion.alignmentSettleTimeMs = 100;
  config.motion.alignmentTimeoutMs = 2000;
  config.motion.decelTimeMs = 200;
  config.motion.accelTimeMs = 200;
}

static bool validatePermutation(uint8_t values[WHEEL_COUNT], uint8_t limit) {
  bool used[PCA9685_SERVO_CHANNEL_COUNT] = {false};
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    if (values[i] >= limit || used[values[i]]) {
      return false;
    }
    used[values[i]] = true;
  }
  return true;
}

bool configFromJson(JsonObjectConst root, VehicleConfig& config, char* error, size_t errorSize) {
  VehicleConfig candidate;
  setDefaultConfig(candidate);

  uint16_t schema = root["schema_version"] | CONFIG_SCHEMA_VERSION;
  if (schema != CONFIG_SCHEMA_VERSION) {
    setError(error, errorSize, "unsupported schema_version");
    return false;
  }

  candidate.schemaVersion = schema;
  candidate.configRevision = root["config_revision"] | candidate.configRevision;
  candidate.pidEnabled = root["pid_enabled"] | candidate.pidEnabled;
  candidate.pca9685Address = root["pca9685_address"] | candidate.pca9685Address;
  if (candidate.pca9685Address == 0 || candidate.pca9685Address > 0x7F) {
    setError(error, errorSize, "invalid pca9685_address");
    return false;
  }

  JsonObjectConst motion = root["motion"];
  if (!motion.isNull()) {
    candidate.motion.wheelbaseM = motion["wheelbase_m"] | candidate.motion.wheelbaseM;
    candidate.motion.trackWidthM = motion["track_width_m"] | candidate.motion.trackWidthM;
    candidate.motion.wheelDiameterM = motion["wheel_diameter_m"] | candidate.motion.wheelDiameterM;
    candidate.motion.maxWheelRpm = motion["max_wheel_rpm"] | candidate.motion.maxWheelRpm;
    candidate.motion.maxLinearSpeedMps = motion["max_linear_speed_mps"] | candidate.motion.maxLinearSpeedMps;
    candidate.motion.maxAngularSpeedRadps = motion["max_angular_speed_radps"] | candidate.motion.maxAngularSpeedRadps;
    candidate.motion.translationDeadzone = motion["translation_deadzone"] | candidate.motion.translationDeadzone;
    candidate.motion.candidateSwitchHysteresisDeg = motion["candidate_switch_hysteresis_deg"] | candidate.motion.candidateSwitchHysteresisDeg;
    candidate.motion.servoEndMarginDeg = motion["servo_end_margin_deg"] | candidate.motion.servoEndMarginDeg;
    candidate.motion.realignThresholdDeg = motion["realign_threshold_deg"] | candidate.motion.realignThresholdDeg;
    candidate.motion.alignmentServoRateDegPerSec = motion["alignment_servo_rate_deg_per_sec"] | candidate.motion.alignmentServoRateDegPerSec;
    candidate.motion.alignmentToleranceDeg = motion["alignment_tolerance_deg"] | candidate.motion.alignmentToleranceDeg;
    candidate.motion.alignmentSettleTimeMs = motion["alignment_settle_time_ms"] | candidate.motion.alignmentSettleTimeMs;
    candidate.motion.alignmentTimeoutMs = motion["alignment_timeout_ms"] | candidate.motion.alignmentTimeoutMs;
    candidate.motion.decelTimeMs = motion["decel_time_ms"] | candidate.motion.decelTimeMs;
    candidate.motion.accelTimeMs = motion["accel_time_ms"] | candidate.motion.accelTimeMs;
  }

  JsonArrayConst motors = root["motors"];
  if (!motors.isNull()) {
    if (motors.size() != WHEEL_COUNT) {
      setError(error, errorSize, "motors array must have 4 entries");
      return false;
    }
    uint8_t physical[WHEEL_COUNT];
    for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
      JsonObjectConst m = motors[i];
      candidate.motors[i].physical = m["physical"] | candidate.motors[i].physical;
      physical[i] = candidate.motors[i].physical;
      candidate.motors[i].inverted = m["inverted"] | candidate.motors[i].inverted;
      candidate.motors[i].pidEnabled = m["pid_enabled"] | candidate.motors[i].pidEnabled;
      candidate.motors[i].kp = m["kp"] | candidate.motors[i].kp;
      candidate.motors[i].ki = m["ki"] | candidate.motors[i].ki;
      candidate.motors[i].kd = m["kd"] | candidate.motors[i].kd;
      candidate.motors[i].integralLimit = m["integral_limit"] | candidate.motors[i].integralLimit;
      float commonStaticFf = m["ff_static_pwm"] | 0.0f;
      float commonSlopeFf = m["ff_pwm_per_rpm"] | 0.0f;
      candidate.motors[i].feedForwardStaticPwmPositive = m["ff_static_pwm_pos"] | commonStaticFf;
      candidate.motors[i].feedForwardStaticPwmNegative = m["ff_static_pwm_neg"] | commonStaticFf;
      candidate.motors[i].feedForwardPwmPerRpmPositive = m["ff_pwm_per_rpm_pos"] | commonSlopeFf;
      candidate.motors[i].feedForwardPwmPerRpmNegative = m["ff_pwm_per_rpm_neg"] | commonSlopeFf;
      candidate.motors[i].outputMin = m["output_min"] | candidate.motors[i].outputMin;
      candidate.motors[i].outputMax = m["output_max"] | candidate.motors[i].outputMax;
      candidate.motors[i].countsPerWheelRev = m["counts_per_wheel_rev"] | candidate.motors[i].countsPerWheelRev;
    }
    if (!validatePermutation(physical, WHEEL_COUNT)) {
      setError(error, errorSize, "duplicate or invalid motor physical mapping");
      return false;
    }
  }

  JsonArrayConst encoders = root["encoders"];
  if (!encoders.isNull()) {
    if (encoders.size() != WHEEL_COUNT) {
      setError(error, errorSize, "encoders array must have 4 entries");
      return false;
    }
    uint8_t physical[WHEEL_COUNT];
    for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
      JsonObjectConst e = encoders[i];
      candidate.encoders[i].physical = e["physical"] | candidate.encoders[i].physical;
      physical[i] = candidate.encoders[i].physical;
      candidate.encoders[i].inverted = e["inverted"] | candidate.encoders[i].inverted;
      candidate.encoders[i].countsPerWheelRev = e["counts_per_wheel_rev"] | candidate.encoders[i].countsPerWheelRev;
      if (candidate.encoders[i].countsPerWheelRev == 0) {
        candidate.encoders[i].countsPerWheelRev = candidate.motors[i].countsPerWheelRev;
      }
    }
    if (!validatePermutation(physical, WHEEL_COUNT)) {
      setError(error, errorSize, "duplicate or invalid encoder physical mapping");
      return false;
    }
  }

  JsonArrayConst servos = root["servos"];
  if (!servos.isNull()) {
    if (servos.size() != WHEEL_COUNT) {
      setError(error, errorSize, "servos array must have 4 entries");
      return false;
    }
    uint8_t channels[WHEEL_COUNT];
    for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
      JsonObjectConst s = servos[i];
      candidate.servos[i].channel = s["channel"] | candidate.servos[i].channel;
      channels[i] = candidate.servos[i].channel;
      candidate.servos[i].centerUs = s["center_us"] | candidate.servos[i].centerUs;
      candidate.servos[i].minUs = s["min_us"] | candidate.servos[i].minUs;
      candidate.servos[i].maxUs = s["max_us"] | candidate.servos[i].maxUs;
      candidate.servos[i].minAngleDeg = s["min_angle_deg"] | candidate.servos[i].minAngleDeg;
      candidate.servos[i].maxAngleDeg = s["max_angle_deg"] | candidate.servos[i].maxAngleDeg;
      candidate.servos[i].trimDeg = s["trim_deg"] | candidate.servos[i].trimDeg;
      candidate.servos[i].inverted = s["direction_inverted"] | candidate.servos[i].inverted;
      candidate.servos[i].calibrated = s["calibrated"] | candidate.servos[i].calibrated;
      candidate.servos[i].maxRateDegPerSec = s["max_rate_deg_per_sec"] | candidate.servos[i].maxRateDegPerSec;

      if (!(candidate.servos[i].minUs < candidate.servos[i].centerUs &&
            candidate.servos[i].centerUs < candidate.servos[i].maxUs &&
            candidate.servos[i].minAngleDeg < 0.0f &&
            candidate.servos[i].maxAngleDeg > 0.0f &&
            candidate.servos[i].maxRateDegPerSec > 0.0f)) {
        setError(error, errorSize, "invalid servo calibration range");
        return false;
      }
    }
    if (!validatePermutation(channels, PCA9685_SERVO_CHANNEL_COUNT)) {
      setError(error, errorSize, "duplicate or invalid servo channel mapping");
      return false;
    }
  }

  if (!finiteFloat(candidate.motion.wheelbaseM) ||
      !finiteFloat(candidate.motion.trackWidthM) ||
      !finiteFloat(candidate.motion.wheelDiameterM) ||
      !finiteFloat(candidate.motion.maxWheelRpm)) {
    setError(error, errorSize, "non-finite motion value");
    return false;
  }

  config = candidate;
  setError(error, errorSize, "ok");
  return true;
}

void configToJson(const VehicleConfig& config, JsonObject root) {
  root["schema_version"] = config.schemaVersion;
  root["config_revision"] = config.configRevision;
  root["pid_enabled"] = config.pidEnabled;
  root["pca9685_address"] = config.pca9685Address;

  JsonObject motion = root.createNestedObject("motion");
  motion["wheelbase_m"] = config.motion.wheelbaseM;
  motion["track_width_m"] = config.motion.trackWidthM;
  motion["wheel_diameter_m"] = config.motion.wheelDiameterM;
  motion["max_wheel_rpm"] = config.motion.maxWheelRpm;
  motion["max_linear_speed_mps"] = config.motion.maxLinearSpeedMps;
  motion["max_angular_speed_radps"] = config.motion.maxAngularSpeedRadps;
  motion["translation_deadzone"] = config.motion.translationDeadzone;
  motion["candidate_switch_hysteresis_deg"] = config.motion.candidateSwitchHysteresisDeg;
  motion["servo_end_margin_deg"] = config.motion.servoEndMarginDeg;
  motion["realign_threshold_deg"] = config.motion.realignThresholdDeg;
  motion["alignment_servo_rate_deg_per_sec"] = config.motion.alignmentServoRateDegPerSec;
  motion["alignment_tolerance_deg"] = config.motion.alignmentToleranceDeg;
  motion["alignment_settle_time_ms"] = config.motion.alignmentSettleTimeMs;
  motion["alignment_timeout_ms"] = config.motion.alignmentTimeoutMs;
  motion["decel_time_ms"] = config.motion.decelTimeMs;
  motion["accel_time_ms"] = config.motion.accelTimeMs;

  JsonArray motors = root.createNestedArray("motors");
  JsonArray encoders = root.createNestedArray("encoders");
  JsonArray servos = root.createNestedArray("servos");
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    JsonObject m = motors.createNestedObject();
    m["logical"] = i;
    m["physical"] = config.motors[i].physical;
    m["inverted"] = config.motors[i].inverted;
    m["pid_enabled"] = config.motors[i].pidEnabled;
    m["kp"] = config.motors[i].kp;
    m["ki"] = config.motors[i].ki;
    m["kd"] = config.motors[i].kd;
    m["integral_limit"] = config.motors[i].integralLimit;
    m["ff_static_pwm_pos"] = config.motors[i].feedForwardStaticPwmPositive;
    m["ff_static_pwm_neg"] = config.motors[i].feedForwardStaticPwmNegative;
    m["ff_pwm_per_rpm_pos"] = config.motors[i].feedForwardPwmPerRpmPositive;
    m["ff_pwm_per_rpm_neg"] = config.motors[i].feedForwardPwmPerRpmNegative;
    m["output_min"] = config.motors[i].outputMin;
    m["output_max"] = config.motors[i].outputMax;
    m["counts_per_wheel_rev"] = config.motors[i].countsPerWheelRev;

    JsonObject e = encoders.createNestedObject();
    e["logical"] = i;
    e["physical"] = config.encoders[i].physical;
    e["inverted"] = config.encoders[i].inverted;
    e["counts_per_wheel_rev"] = config.encoders[i].countsPerWheelRev;

    JsonObject s = servos.createNestedObject();
    s["logical"] = i;
    s["channel"] = config.servos[i].channel;
    s["center_us"] = config.servos[i].centerUs;
    s["min_us"] = config.servos[i].minUs;
    s["max_us"] = config.servos[i].maxUs;
    s["min_angle_deg"] = config.servos[i].minAngleDeg;
    s["max_angle_deg"] = config.servos[i].maxAngleDeg;
    s["trim_deg"] = config.servos[i].trimDeg;
    s["direction_inverted"] = config.servos[i].inverted;
    s["calibrated"] = config.servos[i].calibrated;
    s["max_rate_deg_per_sec"] = config.servos[i].maxRateDegPerSec;
  }
}

bool loadConfigFromNvs(VehicleConfig& config) {
  setDefaultConfig(config);
  Preferences prefs;
  if (!prefs.begin(NVS_NAMESPACE, true)) {
    return false;
  }
  String raw = prefs.getString(NVS_CONFIG_KEY, "");
  prefs.end();
  if (raw.length() == 0) {
    return false;
  }

  StaticJsonDocument<6144> doc;
  DeserializationError err = deserializeJson(doc, raw);
  if (err) {
    return false;
  }
  char message[64];
  return configFromJson(doc.as<JsonObjectConst>(), config, message, sizeof(message));
}

bool saveConfigToNvs(const VehicleConfig& config) {
  StaticJsonDocument<6144> doc;
  configToJson(config, doc.to<JsonObject>());
  String raw;
  serializeJson(doc, raw);

  Preferences prefs;
  if (!prefs.begin(NVS_NAMESPACE, false)) {
    return false;
  }
  bool ok = prefs.putString(NVS_CONFIG_KEY, raw) == raw.length();
  prefs.end();
  return ok;
}
