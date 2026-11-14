const int trigPin = 5;
const int echoPin = 18;
const uint8_t motion = 19;
const int IR = 34;
const int led1 = 16;
const int led2 = 17;
//define sound speed in cm/uS
#define SOUND_SPEED 0.034

long duration;
float dist;
int IRstate;
int warm_up;
int motionState;
int blinkrate;
int distmin;
int distmax;

void setup() {
  analogReadResolution(12);
  Serial.begin(115200); // Starts the serial communication
  pinMode(trigPin, OUTPUT); // Sets the trigPin as an Output
  pinMode(echoPin, INPUT); // Sets the echoPin as an Input
  pinMode(motion, INPUT );
  Serial.println("Waiting For Power On Warm Up");
  delay(20000); /* Power On Warm Up Delay */
  Serial.println("Ready!");
  distmin = 0; distmax = 0;
  blinkrate = 2000;

}

void loop() {
  IRstate  = analogRead(IR);
  motionState = digitalRead(motion);
  // Clears the trigPin
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  // Sets the trigPin on HIGH state for 10 micro seconds
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  // Reads the echoPin, returns the sound wave travel time in microseconds
  duration = pulseIn(echoPin, HIGH);
  
  // Calculate the distance
  dist = duration * SOUND_SPEED/2;
  /*
    if (IRstate == LOW)
    Serial.println("The obstacle is present");
  else
    Serial.println("The obstacle is NOT present");
  */

  if(dist < distmin)
  {
    distmin = dist;
  }
  if(dist > distmax)
  {
    distmax = dist;
  }
  blinkrate = (dist/distmax) * (1900) + 100;
  int led2state = LOW;
  if( motionState == LOW )
  {
    if( warm_up == 1 )
     {
      Serial.print("Warming Up\n\n");
      warm_up = 0;
      delay(1500);
    }
    Serial.print("No object in sight\n\n");
    led2state = LOW;
  }
  else
  {
    Serial.print("Object detected\n\n");   
    warm_up = 1;
    led2state = HIGH;
  } 
  digitalWrite(led1, HIGH);
  digitalWrite(led2, led2state);
  delay(blinkrate);
  digitalWrite(led1,LOW);
  if(led2state = HIGH);
  digitalWrite(led2, LOW);
  delay(blinkrate);

  
  delay(500);
}