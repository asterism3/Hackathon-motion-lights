// draw_led.ino - everything gesture_led.ino does, plus drawing mode.
//
//   python main.py              -> gesture mode: a shape follows your hand (as before)
//   python main.py --mode draw  -> drawing mode: the panel shows what you draw in the air
//
// The laptop says which mode it is in; this sketch follows. Wiring is identical to
// gesture_led.ino: same panel pins, ultrasonic on TRIG=22, ECHO=23 (ECHO through a
// 5 V -> 3.3 V divider).
//
// Libraries: "Adafruit Protomatter" (+ Adafruit GFX) from the Library Manager.
// laptop_link.h and gesture_frames.h in this folder are exact copies of the ones in
// firmware/gesture_led (Arduino needs them next to the sketch). draw_link.h is new.
#include <Adafruit_Protomatter.h>
#include "laptop_link.h"
#include "gesture_frames.h"
#include "draw_link.h"

uint8_t rgbPins[]  = {16, 17, 18, 19, 27, 14};
uint8_t addrPins[] = {33, 26, 32, 25};
uint8_t clockPin   = 21;
uint8_t latchPin   = 15;
uint8_t oePin      = 5;
Adafruit_Protomatter matrix(32, 5, 1, rgbPins, 4, addrPins, clockPin, latchPin, oePin, true);

const int TRIG_PIN = 22;
const int ECHO_PIN = 23;
const unsigned long SONAR_EVERY_MS = 100;
const unsigned long ECHO_TIMEOUT_US = 25000;   // ~4 m; stops pulseIn blocking for 1 s

LaptopLink laptop;
DrawLink art;
float distCm = -1;
unsigned long lastSonarMs = 0;
bool redraw = true;

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (us == 0) return -1;                        // nothing in range
  return us * 0.034f / 2.0f;
}

void setup() {
  Serial.setRxBufferSize(4096);                  // room for a burst of pixels; must be before begin()
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  ProtomatterStatus status = matrix.begin();
  if (status != PROTOMATTER_OK) {
    while (true) {                               // panel failed: say why, forever
      Serial.print("Panel error, Protomatter status ");
      Serial.println((int)status);
      delay(1000);
    }
  }
}

void loop() {
  art.poll(laptop);                              // reads drawing AND gesture messages
  if (laptop.changed()) redraw = true;
  if (art.modeChanged()) redraw = true;

  if (millis() - lastSonarMs >= SONAR_EVERY_MS) {
    lastSonarMs = millis();
    float d = readDistanceCm();
    if (distanceRadius(d) != distanceRadius(distCm)) redraw = true;
    distCm = d;
    laptop.sendDistance(distCm);
  }

  if (art.drawMode) {
    if (art.needsRedraw() || redraw) {
      redraw = false;
      art.draw(matrix);
      matrix.show();
    }
  } else if (redraw) {
    redraw = false;
    matrix.fillScreen(0);
    drawGestureFrame(matrix, laptop.gesture, laptop.x, laptop.y, distCm);
    matrix.show();
  }
}
