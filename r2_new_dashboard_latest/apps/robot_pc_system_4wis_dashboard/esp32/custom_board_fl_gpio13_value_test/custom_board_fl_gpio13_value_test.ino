// FL/GPIO13 value read test for the custom ESP32 sensor board.
// Motors, Wi-Fi, and Bluetooth are not used in this sketch.

#include "../custom_board_pins.h"

constexpr int FL_PIN = PIN_FL;
constexpr int ADC_SAMPLES = 16;
constexpr unsigned long OUTPUT_INTERVAL_MS = 200;
constexpr unsigned long ULTRASONIC_TIMEOUT_US = 30000;

unsigned long last_output_ms = 0;

int read_adc_average() {
  uint32_t sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(FL_PIN);
    delay(2);
  }
  return static_cast<int>(sum / ADC_SAMPLES);
}

long read_grove_ultrasonic_mm() {
  pinMode(FL_PIN, OUTPUT);
  digitalWrite(FL_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(FL_PIN, HIGH);
  delayMicroseconds(5);
  digitalWrite(FL_PIN, LOW);

  pinMode(FL_PIN, INPUT);
  const unsigned long duration_us = pulseIn(FL_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  if (duration_us == 0) {
    return -1;
  }
  return static_cast<long>((duration_us * 10UL) / 58UL);
}

const char* state_label(int raw, int mv, int digital_value, long ultrasonic_mm) {
  if (ultrasonic_mm >= 0) {
    return "ULTRASONIC_PULSE_OK";
  }
  if (raw <= 3 && mv <= 10 && digital_value == LOW) {
    return "HELD_LOW_OR_GND";
  }
  if (raw >= 4090 && digital_value == HIGH) {
    return "HELD_HIGH_OR_VCC";
  }
  return "ADC_SIGNAL_PRESENT";
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(FL_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(FL_PIN, ADC_11db);

  Serial.println("BOOT,FL_GPIO13_VALUE_TEST_READY");
  Serial.println("FW,custom_board_fl_gpio13_value_test,0.1.0");
  Serial.print("FL_PIN,");
  Serial.println(FL_PIN);
  Serial.println("ADC_RESOLUTION,12BIT");
  Serial.println("ADC_ATTENUATION,11DB");
  Serial.println("WIFI,OFF");
  Serial.println("BLUETOOTH,OFF");
  Serial.println("MOTOR,OFF");
}

void loop() {
  const unsigned long now = millis();
  if (now - last_output_ms < OUTPUT_INTERVAL_MS) {
    return;
  }
  last_output_ms = now;

  pinMode(FL_PIN, INPUT);
  const int raw = read_adc_average();
  const int mv = analogReadMilliVolts(FL_PIN);
  const int digital_value = digitalRead(FL_PIN);
  const long ultrasonic_mm = read_grove_ultrasonic_mm();
  const char* state = state_label(raw, mv, digital_value, ultrasonic_mm);

  Serial.print("SENSOR,FL,GPIO13,RAW,");
  Serial.println(raw);

  Serial.print("FL_RAW,");
  Serial.print(raw);
  Serial.print(",FL_MV,");
  Serial.println(mv);

  Serial.print("GPIO13_DIAG,RAW,");
  Serial.print(raw);
  Serial.print(",MV,");
  Serial.print(mv);
  Serial.print(",DIG,");
  Serial.print(digital_value);
  Serial.print(",STATE,");
  Serial.print(state);
  if (ultrasonic_mm >= 0) {
    Serial.print(",GROVE_ULTRASONIC_MM,");
    Serial.print(ultrasonic_mm);
  }
  Serial.println();
}
