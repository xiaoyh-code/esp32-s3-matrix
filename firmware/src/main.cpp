#include <Arduino.h>
#include <FastLED.h>

#define MATRIX_W 8
#define MATRIX_H 8
#define NUM_LEDS (MATRIX_W * MATRIX_H)
#define LED_PIN 14
#define BRIGHTNESS 15

#define SYNC_MARKER 0xAA
#define CMD_FRAME   0x01

CRGB leds[NUM_LEDS];
unsigned long lastFrame = 0;

void startupTest() {
    for (int i = 0; i < NUM_LEDS; i++) leds[i] = CRGB(255, 0, 0);
    FastLED.show();
    delay(500);

    for (int i = 0; i < NUM_LEDS; i++) leds[i] = CRGB(0, 255, 0);
    FastLED.show();
    delay(500);

    for (int i = 0; i < NUM_LEDS; i++) leds[i] = CRGB(0, 0, 255);
    FastLED.show();
    delay(500);

    for (int i = 0; i < NUM_LEDS; i++) leds[i] = CRGB(0, 0, 0);
    FastLED.show();
}

void updateMatrix(uint8_t *data) {
    for (int row = 0; row < MATRIX_H; row++) {
        for (int col = 0; col < MATRIX_W; col++) {
            int idx = row * MATRIX_W + col;
            int offset = idx * 3;
            leds[idx] = CRGB(data[offset], data[offset + 1], data[offset + 2]);
        }
    }
    FastLED.show();
    lastFrame = millis();
}

void setup() {
    FastLED.addLeds<WS2812, LED_PIN, RGB>(leds, NUM_LEDS);
    FastLED.setBrightness(BRIGHTNESS);
    FastLED.clear();
    FastLED.show();

    startupTest();

    Serial.begin(115200);
}

void loop() {
    while (Serial.available() > 0) {
        int b = Serial.read();
        if (b != SYNC_MARKER) continue;

        unsigned long t = millis();
        while (Serial.available() < 1) {
            if (millis() - t > 100) return;
        }

        int cmd = Serial.read();
        if (cmd != CMD_FRAME) continue;

        t = millis();
        while (Serial.available() < 192) {
            if (millis() - t > 500) return;
        }

        uint8_t buf[192];
        Serial.readBytes(buf, 192);
        updateMatrix(buf);
        return;
    }
}
