// Encoder test sketch.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "encoder_test";
static const char* VERSION = "0.1.0";

const int LEFT_ENC_A_PIN = -1;
const int LEFT_ENC_B_PIN = -1;
const int RIGHT_ENC_A_PIN = -1;
const int RIGHT_ENC_B_PIN = -1;

long leftCount = 0;
long rightCount = 0;
unsigned long lastOutputMs = 0;

void handleSerialInput() {
  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("RX,");
      Serial.println(line);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("BOOT,ENCODER_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);

  // Future implementation notes:
  // Use A/B phase inputs with pullups as required by the encoder board.
  // attachInterrupt(digitalPinToInterrupt(LEFT_ENC_A_PIN), leftIsr, CHANGE);
  // Direction can be calculated from A phase and B phase state.
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastOutputMs >= 700) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
    Serial.println("ENC_STATUS,DUMMY");
    Serial.print("ENC,");
    Serial.print(leftCount);
    Serial.print(",");
    Serial.println(rightCount);
  }
}
