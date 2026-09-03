/**
 * ============================================================================
 * THE INCONVENIENT VAULT — ESP32 EMBEDDED HARDWARE CONTROLLER FIRMWARE
 * Framework: Arduino Core for ESP32 (PlatformIO)
 *
 * Drives physical peripherals and interfaces with the Python backend over UART
 * using framed, newline-delimited JSON RPC commands and event telemetry.
 * ============================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <MFRC522.h>
#include <Adafruit_Fingerprint.h>
#include <LiquidCrystal_I2C.h>

// ============================================================================
// Pin Assignments (ESP32 NodeMCU / DevKit-V1)
// ============================================================================

// MFRC522 SPI Pins
#define PIN_RC522_SS       5
#define PIN_RC522_RST      4

// Fingerprint Sensor UART2 Pins (AS608 / Grow R503)
#define PIN_FINGER_RX      16
#define PIN_FINGER_TX      17

// Actuators & Relays
#define PIN_SOLENOID_RELAY 26
#define PIN_BUZZER         27

// RGB Status Beacon LEDs
#define PIN_LED_RED        12
#define PIN_LED_GREEN      13
#define PIN_LED_BLUE       14

// Chassis Tamper Detection
#define PIN_TAMPER_SWITCH  34

// I2C Display Configuration
#define LCD_I2C_ADDR       0x27
#define LCD_COLUMNS        16
#define LCD_ROWS           2

// ============================================================================
// Global Peripheral Instances
// ============================================================================

MFRC522 rfid(PIN_RC522_SS, PIN_RC522_RST);
HardwareSerial fingerSerial(2);
Adafruit_Fingerprint finger(&fingerSerial);
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, LCD_COLUMNS, LCD_ROWS);

// ============================================================================
// State & Timing Variables
// ============================================================================

bool isLocked = true;
unsigned long buzzerOffTime = 0;
unsigned long alarmOffTime = 0;
unsigned long lastRfidScanTime = 0;
unsigned long lastFpScanTime = 0;
String serialRxBuffer = "";
volatile bool tamperFlag = false;

// ============================================================================
// Interrupt Handlers
// ============================================================================

void IRAM_ATTR onTamperBreach() {
    tamperFlag = true;
}

// ============================================================================
// Telemetry & Serial JSON Emission
// ============================================================================

void emitEvent(const char* eventType, JsonDocument& payload) {
    JsonDocument doc;
    doc["event"] = eventType;
    doc["payload"] = payload;
    doc["timestamp_ms"] = millis();

    String jsonStr;
    serializeJson(doc, jsonStr);
    Serial.println(jsonStr);
    Serial.flush();
}

void emitSimpleEvent(const char* eventType) {
    JsonDocument payload;
    emitEvent(eventType, payload);
}

// ============================================================================
// Actuator & Display Control Functions
// ============================================================================

void setRgbLed(const char* color) {
    String c = String(color);
    c.toUpperCase();

    digitalWrite(PIN_LED_RED, LOW);
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_BLUE, LOW);

    if (c == "RED") {
        digitalWrite(PIN_LED_RED, HIGH);
    } else if (c == "GREEN") {
        digitalWrite(PIN_LED_GREEN, HIGH);
    } else if (c == "BLUE") {
        digitalWrite(PIN_LED_BLUE, HIGH);
    } else if (c == "CYAN") {
        digitalWrite(PIN_LED_GREEN, HIGH);
        digitalWrite(PIN_LED_BLUE, HIGH);
    } else if (c == "YELLOW") {
        digitalWrite(PIN_LED_RED, HIGH);
        digitalWrite(PIN_LED_GREEN, HIGH);
    } else if (c == "MAGENTA") {
        digitalWrite(PIN_LED_RED, HIGH);
        digitalWrite(PIN_LED_BLUE, HIGH);
    } else if (c == "WHITE") {
        digitalWrite(PIN_LED_RED, HIGH);
        digitalWrite(PIN_LED_GREEN, HIGH);
        digitalWrite(PIN_LED_BLUE, HIGH);
    }
}

void setLockState(bool locked) {
    isLocked = locked;
    // HIGH activates relay to disengage solenoid, LOW keeps it locked
    digitalWrite(PIN_SOLENOID_RELAY, isLocked ? LOW : HIGH);

    JsonDocument payload;
    payload["locked"] = isLocked;
    payload["state"] = isLocked ? "LOCKED" : "UNLOCKED";
    emitEvent("LOCK_CONFIRMED", payload);
}

void triggerBuzzer(unsigned long durationMs) {
    if (durationMs > 0) {
        digitalWrite(PIN_BUZZER, HIGH);
        buzzerOffTime = millis() + durationMs;
    } else {
        digitalWrite(PIN_BUZZER, LOW);
        buzzerOffTime = 0;
    }
}

void triggerAlarm(unsigned long durationMs) {
    if (durationMs > 0) {
        alarmOffTime = millis() + durationMs;
        triggerBuzzer(durationMs);
        setRgbLed("RED");
    } else {
        alarmOffTime = 0;
        triggerBuzzer(0);
    }
}

void updateDisplay(const char* line1, const char* line2, const char* ledColor, bool buzzer, unsigned long durationMs) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(line1 ? line1 : "");
    lcd.setCursor(0, 1);
    lcd.print(line2 ? line2 : "");

    if (ledColor) {
        setRgbLed(ledColor);
    }
    if (buzzer) {
        triggerBuzzer(durationMs > 0 ? durationMs : 500);
    }
}

// ============================================================================
// Command Parser & Execution
// ============================================================================

void processJsonCommand(const String& jsonLine) {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, jsonLine);

    if (error) {
        JsonDocument errPayload;
        errPayload["error"] = "JSON_PARSE_ERROR";
        errPayload["details"] = error.c_str();
        emitEvent("HARDWARE_ERROR", errPayload);
        return;
    }

    const char* cmd = doc["cmd"] | "";

    if (strcmp(cmd, "SET_DISPLAY") == 0) {
        const char* l1 = doc["line1"] | "";
        const char* l2 = doc["line2"] | "";
        const char* led = doc["led"] | "BLUE";
        bool buz = doc["buzzer"] | false;
        unsigned long dur = doc["duration_ms"] | 500;
        updateDisplay(l1, l2, led, buz, dur);
    }
    else if (strcmp(cmd, "SET_LOCK") == 0) {
        const char* state = doc["state"] | "LOCKED";
        setLockState(strcmp(state, "UNLOCKED") != 0);
    }
    else if (strcmp(cmd, "TRIGGER_ALARM") == 0) {
        unsigned long duration = doc["duration_ms"] | 3000;
        triggerAlarm(duration);
    }
    else if (strcmp(cmd, "PING") == 0) {
        JsonDocument pongPayload;
        pongPayload["uptime_ms"] = millis();
        pongPayload["locked"] = isLocked;
        emitEvent("PONG", pongPayload);
    }
    else {
        JsonDocument errPayload;
        errPayload["error"] = "UNKNOWN_COMMAND";
        errPayload["cmd"] = cmd;
        emitEvent("HARDWARE_ERROR", errPayload);
    }
}

// ============================================================================
// Peripheral Polling Loops (Non-Blocking)
// ============================================================================

void pollRfidScanner() {
    if (millis() - lastRfidScanTime < 350) return; // Debounce
    if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

    lastRfidScanTime = millis();

    // Format UID as Hex String
    String uidStr = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
        uidStr += String(rfid.uid.uidByte[i], HEX);
    }
    uidStr.toUpperCase();

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();

    JsonDocument payload;
    payload["card_uid"] = uidStr;
    emitEvent("RFID_SCANNED", payload);
}

void pollFingerprintScanner() {
    if (millis() - lastFpScanTime < 400) return; // Debounce

    uint8_t p = finger.getImage();
    if (p != FINGERPRINT_OK) return;

    lastFpScanTime = millis();
    p = finger.image2Tz();
    if (p != FINGERPRINT_OK) return;

    p = finger.fingerSearch();
    JsonDocument payload;

    if (p == FINGERPRINT_OK) {
        payload["finger_id"] = finger.fingerID;
        payload["confidence"] = (float)finger.confidence / 100.0f;
        payload["matched"] = true;
        emitEvent("FINGERPRINT_MATCHED", payload);
    } else if (p == FINGERPRINT_NOTFOUND) {
        payload["finger_id"] = 0;
        payload["confidence"] = 0.0f;
        payload["matched"] = false;
        emitEvent("FINGERPRINT_FAILED", payload);
    }
}

void pollSerialRx() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialRxBuffer.length() > 0) {
                processJsonCommand(serialRxBuffer);
                serialRxBuffer = "";
            }
        } else {
            serialRxBuffer += c;
            if (serialRxBuffer.length() > 512) {
                serialRxBuffer = ""; // Overflow guard
            }
        }
    }
}

void checkTimers() {
    unsigned long now = millis();
    if (buzzerOffTime > 0 && now >= buzzerOffTime) {
        digitalWrite(PIN_BUZZER, LOW);
        buzzerOffTime = 0;
    }
    if (alarmOffTime > 0 && now >= alarmOffTime) {
        alarmOffTime = 0;
    }
    if (tamperFlag) {
        tamperFlag = false;
        JsonDocument payload;
        payload["sensor"] = "chassis_switch";
        payload["description"] = "Chassis breach detected via hardware interrupt";
        emitEvent("TAMPER_TRIGGERED", payload);
    }
}

// ============================================================================
// Setup & Main Loop
// ============================================================================

void setup() {
    // 1. Initialize High-Speed Serial Communication
    Serial.begin(115200);
    while (!Serial && millis() < 2000);

    // 2. Configure GPIO Pins
    pinMode(PIN_SOLENOID_RELAY, OUTPUT);
    pinMode(PIN_BUZZER, OUTPUT);
    pinMode(PIN_LED_RED, OUTPUT);
    pinMode(PIN_LED_GREEN, OUTPUT);
    pinMode(PIN_LED_BLUE, OUTPUT);
    pinMode(PIN_TAMPER_SWITCH, INPUT_PULLUP);

    // Attach Tamper Interrupt
    attachInterrupt(digitalPinToInterrupt(PIN_TAMPER_SWITCH), onTamperBreach, FALLING);

    // Initial Actuator State: LOCKED
    setLockState(true);
    setRgbLed("BLUE");

    // 3. Initialize I2C Display
    Wire.begin(21, 22);
    lcd.init();
    lcd.backlight();
    updateDisplay("VAULT 404", "INITIALIZING...", "BLUE", true, 300);

    // 4. Initialize SPI & RC522 RFID
    SPI.begin(18, 19, 23, PIN_RC522_SS);
    rfid.PCD_Init();

    // 5. Initialize Fingerprint UART
    fingerSerial.begin(57600, SERIAL_8N1, PIN_FINGER_RX, PIN_FINGER_TX);
    finger.begin(57600);

    updateDisplay("VAULT 404 READY", "START AUTH...", "BLUE", false, 0);

    // Emit Ready Notification to Host
    JsonDocument bootPayload;
    bootPayload["firmware"] = "1.0.0-ESP32";
    bootPayload["status"] = "READY";
    emitEvent("HARDWARE_BOOT", bootPayload);
}

void loop() {
    pollSerialRx();
    pollRfidScanner();
    pollFingerprintScanner();
    checkTimers();
}
