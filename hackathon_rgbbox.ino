#include <Adafruit_Protomatter.h>


uint8_t rgbPins[]  = {16, 17, 18, 19, 27, 14};
uint8_t addrPins[] = {33, 26, 32, 25};
uint8_t clockPin   = 21;
uint8_t latchPin   = 15;
uint8_t oePin      = 5;
ProtomatterStatus status;
Adafruit_Protomatter matrix(32, 5, 1, rgbPins, 4, addrPins, clockPin, latchPin, oePin, true);
void setup() {
  Serial.begin(115200);
  status = matrix.begin();

  
}

void loop() {
  if(status == PROTOMATTER_OK)
  {
    matrix.drawCircle(12,10,9, matrix.color565(0,255,0));
    matrix.show();
  }
  else
  {
    Serial.println("FALIURE");
    if(status == PROTOMATTER_ERR_PINS)
    {
      Serial.println("Pins error");
    }
    else if(status == PROTOMATTER_ERR_MALLOC)
    {
      Serial.println("Malloc error :)");
    }
    else if(status == PROTOMATTER_ERR_ARG)
    {
      Serial.println("Rare error oh no panic");
    }
    else
    {
      Serial.println("More rare error oh no panic more");
    }
    return;
  }
}