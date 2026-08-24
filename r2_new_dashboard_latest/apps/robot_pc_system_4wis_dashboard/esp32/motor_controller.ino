// R2 / NHK Robot Control Dashboard ESP32 command receiver.
// Ver.1 logs received commands and keeps motor-control hooks ready.

String currentCommand = "STOP";
int currentPower = 0;

struct MotorCommand {
  String name;
  int power;
  bool valid;
};

MotorCommand parseCommand(String line) {
  line.trim();
  line.toUpperCase();

  int spaceIndex = line.indexOf(' ');
  String name = spaceIndex >= 0 ? line.substring(0, spaceIndex) : line;
  int power = spaceIndex >= 0 ? line.substring(spaceIndex + 1).toInt() : 0;

  bool valid = name == "FWD" || name == "STOP" || name == "TURN_L" || name == "TURN_R" || name == "EMERGENCY_STOP";
  return {name, power, valid};
}

void applyMotorCommand(const MotorCommand& command) {
  currentCommand = command.name;
  currentPower = command.power;

  // TODO: Add motor driver PWM and direction control here.
  // FWD uses positive left/right PWM.
  // TURN_L and TURN_R use opposite wheel directions.
  // EMERGENCY_STOP should disable motor outputs immediately.
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  Serial.println("READY,R2_NHK_MOTOR_CONTROLLER");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    MotorCommand command = parseCommand(line);
    if (command.valid) {
      applyMotorCommand(command);
      Serial.print("ACK,");
      Serial.print(currentCommand);
      Serial.print(",");
      Serial.println(currentPower);
    } else {
      Serial.print("ERR,UNKNOWN_COMMAND,");
      Serial.println(line);
    }
  }

  static unsigned long lastReport = 0;
  unsigned long now = millis();
  if (now - lastReport >= 500) {
    lastReport = now;
    Serial.print("STATUS,");
    Serial.print(currentCommand);
    Serial.print(",");
    Serial.println(currentPower);
  }
}
