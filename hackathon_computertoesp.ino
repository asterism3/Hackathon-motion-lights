const int ledPin = 2; // Change to the pin wired to your LED

void setup() {
  pinMode(ledPin, OUTPUT);
  Serial.begin(115200);
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "LED=ON") {
      digitalWrite(ledPin, HIGH);
      Serial.println("OK LED=ON");
    } else if (command == "LED=OFF") {
      digitalWrite(ledPin, LOW);
      Serial.println("OK LED=OFF");
    } else {
      Serial.println("ERR unknown command");
    }
  }
}
