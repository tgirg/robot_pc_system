// UART LiDAR test sketch.
// Motor output is not used in this sketch.

static const char* SKETCH_NAME = "lidar_uart_test";
static const char* VERSION = "0.1.0";

const int LIDAR_RX_PIN = 16;
const int LIDAR_TX_PIN = 17;
const long LIDAR_BAUDRATE = 115200;

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
  Serial.println("BOOT,LIDAR_UART_TEST_READY");
  Serial.print("FW,");
  Serial.print(SKETCH_NAME);
  Serial.print(",");
  Serial.println(VERSION);

  // Future wiring notes:
  // LiDAR TX -> ESP32 RX, LiDAR RX -> ESP32 TX, common GND.
  // Check LiDAR voltage before connecting.
  // HardwareSerial candidate:
  // Serial2.begin(LIDAR_BAUDRATE, SERIAL_8N1, LIDAR_RX_PIN, LIDAR_TX_PIN);
}

void loop() {
  handleSerialInput();
  unsigned long now = millis();
  if (now - lastOutputMs >= 700) {
    lastOutputMs = now;
    Serial.println("STATUS,OK");
    Serial.println("LIDAR_STATUS,DUMMY");
    Serial.println("LIDAR,1200,1200,1200,1200");
  }
}
