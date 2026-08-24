#include "encoder_control.h"

#if __has_include(<driver/pcnt.h>)
  #include <driver/pcnt.h>
  #define ENCODER_USE_PCNT 1
#else
  #define ENCODER_USE_PCNT 0
#endif

static volatile int32_t g_counts[WHEEL_COUNT] = {0, 0, 0, 0};
static volatile uint8_t g_lastAb[WHEEL_COUNT] = {0, 0, 0, 0};
static volatile uint32_t g_invalid[WHEEL_COUNT] = {0, 0, 0, 0};
static int32_t g_lastSample[WHEEL_COUNT] = {0, 0, 0, 0};
static float g_cps[WHEEL_COUNT] = {0, 0, 0, 0};
static bool g_pcntReady = false;

#if ENCODER_USE_PCNT

static const pcnt_unit_t PCNT_UNITS[WHEEL_COUNT] = {
  PCNT_UNIT_0,
  PCNT_UNIT_1,
  PCNT_UNIT_2,
  PCNT_UNIT_3
};

static int16_t readPcntRaw(uint8_t physical) {
  int16_t raw = 0;
  if (physical < WHEEL_COUNT) {
    pcnt_get_counter_value(PCNT_UNITS[physical], &raw);
  }
  return raw;
}

static void clearPcnt(uint8_t physical) {
  if (physical >= WHEEL_COUNT) {
    return;
  }
  pcnt_counter_pause(PCNT_UNITS[physical]);
  pcnt_counter_clear(PCNT_UNITS[physical]);
  pcnt_counter_resume(PCNT_UNITS[physical]);
}

static bool configurePcntChannel(
  pcnt_unit_t unit,
  pcnt_channel_t channel,
  uint8_t pulsePin,
  uint8_t ctrlPin,
  pcnt_count_mode_t posMode,
  pcnt_count_mode_t negMode,
  pcnt_ctrl_mode_t lowCtrlMode,
  pcnt_ctrl_mode_t highCtrlMode
) {
  pcnt_config_t config = {};
  config.pulse_gpio_num = pulsePin;
  config.ctrl_gpio_num = ctrlPin;
  config.channel = channel;
  config.unit = unit;
  config.pos_mode = posMode;
  config.neg_mode = negMode;
  config.lctrl_mode = lowCtrlMode;
  config.hctrl_mode = highCtrlMode;
  config.counter_h_lim = 32767;
  config.counter_l_lim = -32768;
  return pcnt_unit_config(&config) == ESP_OK;
}

void EncoderArray::begin() {
  g_pcntReady = true;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    pinMode(ENCODER_PINS[i].pinA, INPUT);
    pinMode(ENCODER_PINS[i].pinB, INPUT);

    bool ok = configurePcntChannel(
      PCNT_UNITS[i],
      PCNT_CHANNEL_0,
      ENCODER_PINS[i].pinA,
      ENCODER_PINS[i].pinB,
      PCNT_COUNT_INC,
      PCNT_COUNT_DEC,
      PCNT_MODE_KEEP,
      PCNT_MODE_REVERSE
    );
    ok = configurePcntChannel(
      PCNT_UNITS[i],
      PCNT_CHANNEL_1,
      ENCODER_PINS[i].pinB,
      ENCODER_PINS[i].pinA,
      PCNT_COUNT_DEC,
      PCNT_COUNT_INC,
      PCNT_MODE_KEEP,
      PCNT_MODE_REVERSE
    ) && ok;

    ok = (pcnt_counter_pause(PCNT_UNITS[i]) == ESP_OK) && ok;
    ok = (pcnt_counter_clear(PCNT_UNITS[i]) == ESP_OK) && ok;
    ok = (pcnt_set_filter_value(PCNT_UNITS[i], 100) == ESP_OK) && ok;
    ok = (pcnt_filter_enable(PCNT_UNITS[i]) == ESP_OK) && ok;
    ok = (pcnt_counter_resume(PCNT_UNITS[i]) == ESP_OK) && ok;
    g_pcntReady = g_pcntReady && ok;

    g_counts[i] = 0;
    g_lastSample[i] = 0;
    g_cps[i] = 0.0f;
    g_invalid[i] = 0;
  }
}

bool EncoderArray::pcntReady() const {
  return g_pcntReady;
}

void EncoderArray::updateVelocity(float dtSeconds) {
  if (dtSeconds <= 0.0f) {
    return;
  }
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    pcnt_counter_pause(PCNT_UNITS[i]);
    int16_t raw = readPcntRaw(i);
    pcnt_counter_clear(PCNT_UNITS[i]);
    pcnt_counter_resume(PCNT_UNITS[i]);

    g_counts[i] += raw;
    g_lastSample[i] = g_counts[i];
    g_cps[i] = (float)raw / dtSeconds;
  }
}

void EncoderArray::resetLogical(uint8_t logical, const VehicleConfig& config) {
  if (logical >= WHEEL_COUNT) {
    return;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return;
  }
  g_counts[physical] = 0;
  g_lastSample[physical] = 0;
  g_cps[physical] = 0.0f;
  g_invalid[physical] = 0;
  clearPcnt(physical);
}

int32_t EncoderArray::logicalCount(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0;
  }
  int32_t count = g_counts[physical] + readPcntRaw(physical);
  return config.encoders[logical].inverted ? -count : count;
}

float EncoderArray::logicalRpm(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0.0f;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0.0f;
  }
  uint32_t countsPerRev = config.encoders[logical].countsPerWheelRev;
  if (countsPerRev == 0) {
    countsPerRev = config.motors[logical].countsPerWheelRev;
  }
  if (countsPerRev == 0) {
    return 0.0f;
  }
  float cps = g_cps[physical];
  if (config.encoders[logical].inverted) {
    cps = -cps;
  }
  return (cps * 60.0f) / (float)countsPerRev;
}

uint32_t EncoderArray::invalidTransitions(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0;
  }
  return g_invalid[physical];
}

#else

static portMUX_TYPE g_mux[WHEEL_COUNT] = {
  portMUX_INITIALIZER_UNLOCKED,
  portMUX_INITIALIZER_UNLOCKED,
  portMUX_INITIALIZER_UNLOCKED,
  portMUX_INITIALIZER_UNLOCKED
};

static const int8_t QUADRATURE_TABLE[16] = {
   0, -1,  1,  0,
   1,  0,  0, -1,
  -1,  0,  0,  1,
   0,  1, -1,  0
};

static uint8_t readAb(uint8_t physical) {
  uint8_t a = digitalRead(ENCODER_PINS[physical].pinA);
  uint8_t b = digitalRead(ENCODER_PINS[physical].pinB);
  return (a << 1) | b;
}

void EncoderArray::begin() {
  g_pcntReady = false;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    pinMode(ENCODER_PINS[i].pinA, INPUT);
    pinMode(ENCODER_PINS[i].pinB, INPUT);
    portENTER_CRITICAL(&g_mux[i]);
    g_counts[i] = 0;
    g_lastAb[i] = readAb(i);
    g_invalid[i] = 0;
    portEXIT_CRITICAL(&g_mux[i]);
  }

  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[0].pinA), EncoderArray::handleInterrupt0, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[0].pinB), EncoderArray::handleInterrupt0, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[1].pinA), EncoderArray::handleInterrupt1, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[1].pinB), EncoderArray::handleInterrupt1, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[2].pinA), EncoderArray::handleInterrupt2, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[2].pinB), EncoderArray::handleInterrupt2, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[3].pinA), EncoderArray::handleInterrupt3, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_PINS[3].pinB), EncoderArray::handleInterrupt3, CHANGE);
}

bool EncoderArray::pcntReady() const {
  return false;
}

void IRAM_ATTR EncoderArray::handleInterrupt0() { handleEdge(0); }
void IRAM_ATTR EncoderArray::handleInterrupt1() { handleEdge(1); }
void IRAM_ATTR EncoderArray::handleInterrupt2() { handleEdge(2); }
void IRAM_ATTR EncoderArray::handleInterrupt3() { handleEdge(3); }

void IRAM_ATTR EncoderArray::handleEdge(uint8_t physical) {
  uint8_t currentAb = readAb(physical);
  portENTER_CRITICAL_ISR(&g_mux[physical]);
  uint8_t previous = g_lastAb[physical];
  int8_t delta = QUADRATURE_TABLE[(previous << 2) | currentAb];
  if (delta != 0) {
    g_counts[physical] += delta;
  } else if (currentAb != previous) {
    g_invalid[physical]++;
  }
  g_lastAb[physical] = currentAb;
  portEXIT_CRITICAL_ISR(&g_mux[physical]);
}

void EncoderArray::updateVelocity(float dtSeconds) {
  if (dtSeconds <= 0.0f) {
    return;
  }
  for (uint8_t i = 0; i < WHEEL_COUNT; i++) {
    int32_t count;
    portENTER_CRITICAL(&g_mux[i]);
    count = g_counts[i];
    portEXIT_CRITICAL(&g_mux[i]);
    int32_t delta = count - g_lastSample[i];
    g_lastSample[i] = count;
    g_cps[i] = (float)delta / dtSeconds;
  }
}

void EncoderArray::resetLogical(uint8_t logical, const VehicleConfig& config) {
  if (logical >= WHEEL_COUNT) {
    return;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return;
  }
  portENTER_CRITICAL(&g_mux[physical]);
  g_counts[physical] = 0;
  g_lastAb[physical] = readAb(physical);
  g_invalid[physical] = 0;
  portEXIT_CRITICAL(&g_mux[physical]);
  g_lastSample[physical] = 0;
  g_cps[physical] = 0.0f;
}

int32_t EncoderArray::logicalCount(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0;
  }
  int32_t count;
  portENTER_CRITICAL(&g_mux[physical]);
  count = g_counts[physical];
  portEXIT_CRITICAL(&g_mux[physical]);
  return config.encoders[logical].inverted ? -count : count;
}

float EncoderArray::logicalRpm(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0.0f;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0.0f;
  }
  uint32_t countsPerRev = config.encoders[logical].countsPerWheelRev;
  if (countsPerRev == 0) {
    countsPerRev = config.motors[logical].countsPerWheelRev;
  }
  if (countsPerRev == 0) {
    return 0.0f;
  }
  float cps = g_cps[physical];
  if (config.encoders[logical].inverted) {
    cps = -cps;
  }
  return (cps * 60.0f) / (float)countsPerRev;
}

uint32_t EncoderArray::invalidTransitions(uint8_t logical, const VehicleConfig& config) const {
  if (logical >= WHEEL_COUNT) {
    return 0;
  }
  uint8_t physical = config.encoders[logical].physical;
  if (physical >= WHEEL_COUNT) {
    return 0;
  }
  uint32_t value;
  portENTER_CRITICAL(&g_mux[physical]);
  value = g_invalid[physical];
  portEXIT_CRITICAL(&g_mux[physical]);
  return value;
}

#endif
