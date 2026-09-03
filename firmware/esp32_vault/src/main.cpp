#include <Arduino.h>
#include <SPI.h>
#include <ArduinoJson.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <ESP32Servo.h>
#include "mbedtls/md.h"

// ============================================================================
// Pin Assignments (ESP32)
// ============================================================================

// MFRC522 SPI Pins
#define PIN_RC522_SS       5
#define PIN_RC522_RST      22

// Actuators & Relays
#define PIN_SERVO          25
#define PIN_BUZZER         14

// Status LEDs
#define PIN_LED_GREEN      26
#define PIN_LED_RED        27

// Keypad Pins
#define ROWS 4
#define COLS 4
byte rowPins[ROWS] = {32, 33, 21, 13};
byte colPins[COLS] = {34, 35, 36, 39};

char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};

// ============================================================================
// Global Peripheral Instances
// ============================================================================

MFRC522 rfid(PIN_RC522_SS, PIN_RC522_RST);
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);
Servo lockServo;

// ============================================================================
// State & Timing Variables
// ============================================================================

bool isLocked = true;
bool keypadEnabled = false;
bool lockdownActive = false;
String expectedPinHash = "";
String currentPinEntry = "";

String serialRxBuffer = "";

enum AlarmMode {
    ALARM_OFF = 0,
    ALARM_SUCCESS = 1,
    ALARM_FAILURE = 2,
    ALARM_LOCKDOWN = 3
};
AlarmMode currentAlarmMode = ALARM_OFF;
unsigned long alarmStartTime = 0;
unsigned long lastAlarmToggle = 0;
bool alarmToggleState = false;

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

// ============================================================================
// Crypto Helpers
// ============================================================================

String computeSHA256(const String& input) {
    byte shaResult[32];
    mbedtls_md_context_t ctx;
    mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;
    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 0);
    mbedtls_md_starts(&ctx);
    mbedtls_md_update(&ctx, (const unsigned char*)input.c_str(), input.length());
    mbedtls_md_finish(&ctx, shaResult);
    mbedtls_md_free(&ctx);

    String hashStr = "";
    for (int i = 0; i < 32; i++) {
        char buf[3];
        sprintf(buf, "%02x", shaResult[i]);
        hashStr += buf;
    }
    return hashStr;
}

// ============================================================================
// Actuator Control
// ============================================================================

void setLockState(bool locked) {
    if (lockdownActive && !locked) {
        // Reject unlock if in lockdown
        return; 
    }
    isLocked = locked;
    if (isLocked) {
        lockServo.write(0); // 0 degrees = LOCKED
    } else {
        lockServo.write(90); // 90 degrees = UNLOCKED
    }

    JsonDocument payload;
    payload["locked"] = isLocked;
    payload["state"] = isLocked ? "LOCKED" : "UNLOCKED";
    emitEvent("LOCK_STATUS_REPORT", payload);
}

void triggerAlarm(AlarmMode mode) {
    currentAlarmMode = mode;
    alarmStartTime = millis();
    lastAlarmToggle = 0;
    alarmToggleState = false;

    // Reset LEDs/Buzzer
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_RED, LOW);
    digitalWrite(PIN_BUZZER, LOW);
}

void updateAlarm() {
    unsigned long now = millis();
    
    if (currentAlarmMode == ALARM_OFF) {
        digitalWrite(PIN_LED_GREEN, LOW);
        digitalWrite(PIN_LED_RED, LOW);
        digitalWrite(PIN_BUZZER, LOW);
        return;
    }
    
    if (currentAlarmMode == ALARM_SUCCESS) {
        // Brief green indication
        if (now - alarmStartTime < 1000) {
            digitalWrite(PIN_LED_GREEN, HIGH);
        } else {
            currentAlarmMode = ALARM_OFF;
        }
    }
    else if (currentAlarmMode == ALARM_FAILURE) {
        // Short red flashing and buzzer
        if (now - alarmStartTime < 2000) {
            if (now - lastAlarmToggle > 200) {
                alarmToggleState = !alarmToggleState;
                lastAlarmToggle = now;
                digitalWrite(PIN_LED_RED, alarmToggleState ? HIGH : LOW);
                digitalWrite(PIN_BUZZER, alarmToggleState ? HIGH : LOW);
            }
        } else {
            currentAlarmMode = ALARM_OFF;
        }
    }
    else if (currentAlarmMode == ALARM_LOCKDOWN) {
        // Persistent periodic red alarm pattern
        if (now - lastAlarmToggle > 500) {
            alarmToggleState = !alarmToggleState;
            lastAlarmToggle = now;
            digitalWrite(PIN_LED_RED, alarmToggleState ? HIGH : LOW);
            digitalWrite(PIN_BUZZER, alarmToggleState ? HIGH : LOW);
        }
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

    if (strcmp(cmd, "COMMAND_UNLOCK") == 0) {
        if (!lockdownActive) {
            setLockState(false);
            triggerAlarm(ALARM_SUCCESS);
        } else {
            JsonDocument rej;
            rej["reason"] = "LOCKDOWN_ACTIVE";
            emitEvent("UNLOCK_COMMAND_REJECTED", rej);
        }
    }
    else if (strcmp(cmd, "COMMAND_LOCK") == 0) {
        setLockState(true);
    }
    else if (strcmp(cmd, "TRIGGER_ALARM") == 0) {
        triggerAlarm(ALARM_FAILURE);
    }
    else if (strcmp(cmd, "ENTER_LOCKDOWN") == 0) {
        lockdownActive = true;
        setLockState(true);
        triggerAlarm(ALARM_LOCKDOWN);
    }
    else if (strcmp(cmd, "RESET_STATE") == 0) {
        lockdownActive = false;
        setLockState(true);
        keypadEnabled = false;
        currentPinEntry = "";
        triggerAlarm(ALARM_OFF);
    }
    else if (strcmp(cmd, "ENABLE_KEYPAD") == 0) {
        keypadEnabled = true;
        currentPinEntry = "";
        const char* hash = doc["expected_pin_hash"] | "";
        expectedPinHash = String(hash);
        
        JsonDocument payload;
        payload["status"] = "KEYPAD_ENABLED";
        emitEvent("KEYPAD_STATUS", payload);
    }
    else if (strcmp(cmd, "DISABLE_KEYPAD") == 0) {
        keypadEnabled = false;
        currentPinEntry = "";
    }
    else if (strcmp(cmd, "PING") == 0) {
        JsonDocument pongPayload;
        pongPayload["uptime_ms"] = millis();
        pongPayload["locked"] = isLocked;
        pongPayload["lockdown"] = lockdownActive;
        emitEvent("HEARTBEAT", pongPayload);
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
    static unsigned long lastRfidScanTime = 0;
    if (millis() - lastRfidScanTime < 350) return; // Debounce
    if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

    lastRfidScanTime = millis();

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

void pollKeypad() {
    char key = keypad.getKey();
    if (key) {
        if (!keypadEnabled) {
            return; // Ignore if not in Stage 4
        }
        
        if (key == '*') {
            // Clear entry
            currentPinEntry = "";
        } else if (key == '#') {
            // Submit entry
            String enteredHash = computeSHA256(currentPinEntry);
            JsonDocument payload;
            if (enteredHash.equalsIgnoreCase(expectedPinHash)) {
                payload["result"] = "KEYPAD_PIN_VERIFIED";
            } else {
                payload["result"] = "KEYPAD_PIN_REJECTED";
            }
            emitEvent("KEYPAD_PIN_RESULT", payload);
            
            // Clear memory
            currentPinEntry = "";
            keypadEnabled = false;
        } else {
            // Append
            currentPinEntry += key;
            // Cap length
            if (currentPinEntry.length() > 16) {
                currentPinEntry = "";
            }
        }
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

// ============================================================================
// Setup & Main Loop
// ============================================================================

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 2000);

    pinMode(PIN_BUZZER, OUTPUT);
    pinMode(PIN_LED_RED, OUTPUT);
    pinMode(PIN_LED_GREEN, OUTPUT);

    // Initialize Servo
    lockServo.attach(PIN_SERVO);
    setLockState(true);

    // Initialize SPI & RC522 RFID
    SPI.begin(18, 19, 23, PIN_RC522_SS);
    rfid.PCD_Init();

    JsonDocument bootPayload;
    bootPayload["firmware"] = "2.0.0-ESP32-Refactor";
    bootPayload["status"] = "READY";
    emitEvent("HARDWARE_BOOT", bootPayload);
}

void loop() {
    pollSerialRx();
    pollRfidScanner();
    pollKeypad();
    updateAlarm();
}
