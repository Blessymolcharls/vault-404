#include <Arduino.h>
#include <SPI.h>
#include <ArduinoJson.h>
#include <Keypad.h>
#include <ESP32Servo.h>

// ============================================================================
// Pin Assignments (ESP32 Hardware Circuit)
// ============================================================================

// Actuators & Indicators
#define SERVO_PIN      2
#define GREEN_LED      22
#define RED_LED        15
#define BUZZER_PIN     21

// Servo Positions
const int LOCKED_POSITION   = 0;
const int UNLOCKED_POSITION = 90;

// Keypad Configuration
const byte ROWS = 4;
const byte COLS = 4;

char keys[ROWS][COLS] = {
  {'D', 'C', 'B', 'A'},
  {'#', '9', '6', '3'},
  {'0', '8', '5', '2'},
  {'*', '7', '4', '1'}
};

// Row Pins 1-4
byte rowPins[ROWS] = {
  13,
  12,
  14,
  27
};

// Column Pins 5-8
byte colPins[COLS] = {
  26,
  25,
  33,
  32
};

// ============================================================================
// Global Peripherals
// ============================================================================

Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);
Servo lockServo;

// ============================================================================
// State & Timing Variables
// ============================================================================

String enteredPassword = "";

bool isLocked = true;
bool passwordVerified = false;
bool keypadEnabled = true;
bool lockdownActive = false;

unsigned long unlockTimestamp = 0;
const unsigned long UNLOCK_HOLD_MS = 5000;
bool autoRelockPending = false;

unsigned long redLedOffTimestamp = 0;
bool redLedTimerActive = false;

String serialRxBuffer = "";

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
// Audio Feedback Helpers
// ============================================================================

void soundBeep(int freq, int durationMs) {
    tone(BUZZER_PIN, freq, durationMs);
}

void soundErrorTone() {
    tone(BUZZER_PIN, 500, 200);
    delay(250);
    tone(BUZZER_PIN, 500, 200);
}

// ============================================================================
// Hardware Actuation Methods
// ============================================================================

void setLockState(bool locked) {
    if (lockdownActive && !locked) {
        Serial.println("[SECURITY] Unlock rejected: Lockdown active!");
        return;
    }

    isLocked = locked;
    if (isLocked) {
        lockServo.write(LOCKED_POSITION);
        digitalWrite(GREEN_LED, LOW);
        autoRelockPending = false;
        passwordVerified = false;
        Serial.println("Servo: LOCKED (0 deg)");
    } else {
        lockServo.write(UNLOCKED_POSITION);
        digitalWrite(GREEN_LED, HIGH);
        digitalWrite(RED_LED, LOW);
        unlockTimestamp = millis();
        autoRelockPending = true;
        passwordVerified = true;
        Serial.println("Servo: UNLOCKED (90 deg)");
    }

    JsonDocument payload;
    payload["locked"] = isLocked;
    payload["state"] = isLocked ? "LOCKED" : "UNLOCKED";
    payload["servo_angle"] = isLocked ? LOCKED_POSITION : UNLOCKED_POSITION;
    emitEvent("LOCK_STATUS_REPORT", payload);
}

// ============================================================================
// Keypad Processing Function (Delegates verification to Backend)
// ============================================================================

void checkPassword() {
    char key = keypad.getKey();
    if (key == NO_KEY) {
        return;
    }

    // =========================
    // CLEAR PASSWORD (*)
    // =========================
    if (key == '*') {
        enteredPassword = "";
        Serial.println();
        Serial.println("Password buffer cleared.");
        Serial.println();

        soundBeep(700, 100);

        JsonDocument payload;
        payload["status"] = "CLEARED";
        emitEvent("KEYPAD_CLEARED", payload);
        return;
    }

    // =========================
    // SUBMIT PASSWORD (#)
    // =========================
    if (key == '#') {
        Serial.println();

        if (enteredPassword.length() > 0) {
            Serial.println("[AUTH] Transmitting keypad password to backend for Argon2 verification...");

            // Send password to Python backend for central verification
            JsonDocument payload;
            payload["pin"] = enteredPassword;
            payload["length"] = enteredPassword.length();
            payload["status"] = "PIN_SUBMITTED";
            emitEvent("KEYPAD_PIN_SUBMITTED", payload);

            enteredPassword = "";
        } else {
            Serial.println("[AUTH] Empty password entry ignored.");
            soundBeep(500, 100);
        }
        return;
    }

    // =========================
    // ADD DIGIT / KEY
    // =========================
    if (enteredPassword.length() < 32) {
        enteredPassword += key;
        Serial.print("*");
        soundBeep(1000, 50);

        JsonDocument payload;
        payload["key"] = String(key);
        payload["length"] = enteredPassword.length();
        emitEvent("KEYPAD_KEY_PRESSED", payload);
    }
}

// ============================================================================
// Command Parser & Execution (Host Python Backend -> ESP32)
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

    // Unlock Command
    if (strcmp(cmd, "COMMAND_UNLOCK") == 0 || (strcmp(cmd, "SET_LOCK") == 0 && doc["state"] == "UNLOCKED")) {
        if (!lockdownActive) {
            Serial.println("================================");
            Serial.println("BACKEND: ACCESS GRANTED");
            Serial.println("UNLOCKING VAULT...");
            Serial.println("================================");

            soundBeep(2000, 300);
            setLockState(false);
        } else {
            JsonDocument rej;
            rej["reason"] = "LOCKDOWN_ACTIVE";
            emitEvent("UNLOCK_COMMAND_REJECTED", rej);
        }
    }
    // Lock Command
    else if (strcmp(cmd, "COMMAND_LOCK") == 0 || (strcmp(cmd, "SET_LOCK") == 0 && doc["state"] == "LOCKED")) {
        setLockState(true);
    }
    // Alarm Trigger (Failed authentication or tamper)
    else if (strcmp(cmd, "TRIGGER_ALARM") == 0) {
        Serial.println("================================");
        Serial.println("BACKEND: ACCESS DENIED / ALARM");
        Serial.println("================================");

        digitalWrite(RED_LED, HIGH);
        digitalWrite(GREEN_LED, LOW);
        soundErrorTone();
        redLedOffTimestamp = millis() + 1500;
        redLedTimerActive = true;
        setLockState(true);
    }
    // Security Lockdown
    else if (strcmp(cmd, "ENTER_LOCKDOWN") == 0) {
        lockdownActive = true;
        setLockState(true);
        digitalWrite(RED_LED, HIGH);
        soundErrorTone();
    }
    // Reset State
    else if (strcmp(cmd, "RESET_STATE") == 0) {
        lockdownActive = false;
        setLockState(true);
        enteredPassword = "";
        digitalWrite(RED_LED, LOW);
        digitalWrite(GREEN_LED, LOW);
    }
    // Heartbeat / Ping
    else if (strcmp(cmd, "PING") == 0) {
        JsonDocument pongPayload;
        pongPayload["uptime_ms"] = millis();
        pongPayload["locked"] = isLocked;
        pongPayload["password_verified"] = passwordVerified;
        pongPayload["lockdown"] = lockdownActive;
        pongPayload["status"] = "ONLINE";
        emitEvent("PONG", pongPayload);
    }
    else {
        JsonDocument errPayload;
        errPayload["error"] = "UNKNOWN_COMMAND";
        errPayload["cmd"] = cmd;
        emitEvent("HARDWARE_ERROR", errPayload);
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
                serialRxBuffer = ""; // Guard buffer overflow
            }
        }
    }
}

void updateTimers() {
    unsigned long now = millis();

    // Auto-relock after UNLOCK_HOLD_MS (5 seconds)
    if (autoRelockPending && (now - unlockTimestamp >= UNLOCK_HOLD_MS)) {
        Serial.println();
        Serial.println("Vault unlocked duration expired.");
        Serial.println("Locking again...");

        setLockState(true);

        Serial.println();
        Serial.println("Vault LOCKED.");
        Serial.println("Enter password on keypad:");
        Serial.println();
    }

    // Turn off Red LED after error timeout
    if (redLedTimerActive && (now >= redLedOffTimestamp)) {
        digitalWrite(RED_LED, LOW);
        redLedTimerActive = false;
    }
}

// ============================================================================
// Setup & Main Loop
// ============================================================================

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("================================");
    Serial.println("       BISCUIT VAULT (404)");
    Serial.println("================================");

    // Setup LEDs
    pinMode(GREEN_LED, OUTPUT);
    pinMode(RED_LED, OUTPUT);
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED, LOW);

    // Setup Buzzer
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);

    // Setup Servo
    lockServo.setPeriodHertz(50);
    lockServo.attach(SERVO_PIN, 500, 2400);
    lockServo.write(LOCKED_POSITION);
    isLocked = true;

    Serial.println("Servo: LOCKED (0 deg)");

    // Boot Telemetry
    JsonDocument bootPayload;
    bootPayload["firmware"] = "2.2.0-Vault404-SecureKeypad";
    bootPayload["status"] = "READY";
    bootPayload["servo_pin"] = SERVO_PIN;
    bootPayload["green_led_pin"] = GREEN_LED;
    bootPayload["red_led_pin"] = RED_LED;
    bootPayload["buzzer_pin"] = BUZZER_PIN;
    emitEvent("HARDWARE_BOOT", bootPayload);

    Serial.println();
    Serial.println("STEP 1: Enter password on keypad.");
    Serial.println("Press # to submit to backend.");
    Serial.println("Press * to clear.");
    Serial.println();
}

void loop() {
    pollSerialRx();
    checkPassword();
    updateTimers();
}
