/*
  DIY Spirometer Arduino Mega Controller

  Responsibilities:
  - display instructions on 16x2 LCD
  - run 4-second baseline calibration period
  - control 3 LED indicators
  - sample analog signal from A0 at 100 Hz
  - stream baseline and breath data to Python
  - receive computed FEV1/FVC from Python
  - display final spirometry results on LCD
*/


#include <LiquidCrystal.h>

const int signalPin = A0;
const unsigned long Ts_us = 10000;          // 100 Hz
const unsigned long baselineTime_ms = 4000; // 4 s calibration
const unsigned long recordTime_ms = 10000;  // 10 s recording

const int rs = 22;
const int en = 23;
const int d4 = 24;
const int d5 = 25;
const int d6 = 26;
const int d7 = 27;

const int led1 = 13;
const int led2 = 12;
const int led3 = 11;

LiquidCrystal lcd(rs, en, d4, d5, d6, d7);

void setup() {
  Serial.begin(115200);

  lcd.begin(16, 2);

  pinMode(led1, OUTPUT);
  pinMode(led2, OUTPUT);
  pinMode(led3, OUTPUT);
  allLedsOff();

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Spirometer");
  lcd.setCursor(0, 1);
  lcd.print("Waiting...");
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 's') {
      countdownAndRecord();
    }
  }
}

void allLedsOff() {
  digitalWrite(led1, LOW);
  digitalWrite(led2, LOW);
  digitalWrite(led3, LOW);
}

void setCountdownLeds(int n) {
  digitalWrite(led1, n >= 1 ? HIGH : LOW);
  digitalWrite(led2, n >= 2 ? HIGH : LOW);
  digitalWrite(led3, n >= 3 ? HIGH : LOW);
}

void flashLeds(int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(led1, HIGH);
    digitalWrite(led2, HIGH);
    digitalWrite(led3, HIGH);
    delay(onMs);
    allLedsOff();
    delay(offMs);
  }
}

void countdownAndRecord() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Spirometer");
  lcd.setCursor(0, 1);
  lcd.print("Waiting...");
  allLedsOff();

  unsigned long baseStart = millis();
  unsigned long nextSample = micros();

  while (millis() - baseStart < baselineTime_ms) {
    while ((long)(micros() - nextSample) < 0) {}
    nextSample += Ts_us;

    int adc = analogRead(signalPin);
    Serial.print("B,");
    Serial.println(adc);
  }

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Get Ready");
  lcd.setCursor(0, 1);
  lcd.print("Blow in 3");
  setCountdownLeds(1);
  delay(1000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Get Ready");
  lcd.setCursor(0, 1);
  lcd.print("Blow in 2");
  setCountdownLeds(2);
  delay(1000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Get Ready");
  lcd.setCursor(0, 1);
  lcd.print("Blow in 1");
  setCountdownLeds(3);
  delay(1000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Blow now!");
  lcd.setCursor(0, 1);
  lcd.print("Recording...");
  allLedsOff();

  Serial.println("START");

  unsigned long startMs = millis();
  nextSample = micros();
  int lastShown = -1;

  while (millis() - startMs < recordTime_ms) {
    while ((long)(micros() - nextSample) < 0) {}
    nextSample += Ts_us;

    int adc = analogRead(signalPin);
    Serial.println(adc);

    int secLeft = (recordTime_ms - (millis() - startMs)) / 1000;
    if (secLeft != lastShown) {
      lcd.setCursor(0, 1);
      lcd.print("Time left:     ");
      lcd.setCursor(11, 1);
      lcd.print(secLeft);
      lastShown = secLeft;
    }
  }

  Serial.println("END");

  flashLeds(3, 200, 200);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Calculating...");
  lcd.setCursor(0, 1);
  lcd.print("Please wait");

  String result = "";
  unsigned long waitStart = millis();

  while (millis() - waitStart < 20000) {
    while (Serial.available() > 0) {
      char c = Serial.read();
      if (c == '\r') continue;

      if (c == '\n') {
        if (result.length() > 0) goto display_results;
      } else {
        result += c;
      }
    }
  }

display_results:
  result.trim();

  if (result.startsWith("R,")) {
    int comma2 = result.indexOf(',', 2);

    if (comma2 > 0) {
      float fev1 = result.substring(2, comma2).toFloat();
      float fvc = result.substring(comma2 + 1).toFloat();

      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("FEV1:");
      lcd.print(fev1, 2);
      lcd.print(" L");

      lcd.setCursor(0, 1);
      lcd.print("FVC:");
      lcd.print(fvc, 2);
      lcd.print(" L");

      flashLeds(5, 120, 120);

      while (Serial.available() == 0) {
        // hold result until next trigger
      }
    } else {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Bad format");
      flashLeds(3, 300, 300);
      delay(3000);
    }
  } else {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("No result");
    flashLeds(3, 300, 300);
    delay(3000);
  }

  allLedsOff();
}
