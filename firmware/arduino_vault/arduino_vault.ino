// ============================================================================
// THE INCONVENIENT VAULT (VAULT-404) - ESP32 EMBEDDED FIRMWARE
// ============================================================================
// Environment: Arduino IDE
// Target Board: ESP32 Dev Module / NodeMCU-32S
//
// Required Arduino IDE Libraries (Install via Sketch -> Include Library -> Manage Libraries):
// 1. "Keypad" by Mark Stanley, Alexander Brevig (v3.1.1+)
// 2. "ESP32Servo" by Kevin Harrington, John K. Bennett (v3.0.0+)
// 3. "MFRC522" by GithubCommunity / miguelbalboa (v1.4.10+)
// 4. "ArduinoJson" by Benoit Blanchon (v7.x or v6.x)
// ============================================================================

#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ============================================================================
// 1. PIN DEFINITIONS & HARDWARE CONSTANTS
// ============================================================================

// Actuators & Indicators
#define SERVO_PIN        2      // Servo Lock Signal (PWM) - Powered by 5V
#define GREEN_LED        22     // Access Granted / Success Indicator (Active High)
#define RED_LED          15     // Access Denied / Warning Indicator (Active High)
#define BUZZER_PIN       21     // Active Buzzer / Audio Tone (PWM)

// 4-Motor Getaway Chassis (Dual H-Bridge / L298N Controller)
// Left Motor Pair (Front & Rear Left)
#define M_LEFT_IN1       16     // Left Motors Forward (IN1)
#define M_LEFT_IN2       17     // Left Motors Reverse (IN2)
// Right Motor Pair (Front & Rear Right)
#define M_RIGHT_IN3      0      // Right Motors Forward (IN3)
#define M_RIGHT_IN4      1      // Right Motors Reverse (IN4)

// MFRC522 RFID (SPI Bus)
#define RFID_SS_PIN      5      // SDA / SS
#define RFID_RST_PIN     4      // RST
#define RFID_SCK_PIN     18     // SCK
#define RFID_MISO_PIN    19     // MISO
#define RFID_MOSI_PIN    23     // MOSI

// Servo Positions
const int LOCKED_POSITION   = 0;    // 0 degrees = Locked
const int UNLOCKED_POSITION = 90;   // 90 degrees = Unlocked
const unsigned long AUTO_RELOCK_DEFAULT_MS = 5000; // 5 seconds non-blocking auto-relock

// 4x4 Matrix Keypad Configuration
const byte ROWS = 4;
const byte COLS = 4;

char keys[ROWS][COLS] = {
  {'D', 'C', 'B', 'A'},
  {'#', '9', '6', '3'},
  {'0', '8', '5', '2'},
  {'*', '7', '4', '1'}
};

byte rowPins[ROWS] = {13, 12, 14, 27};  // R1, R2, R3, R4
byte colPins[COLS] = {26, 25, 33, 32};  // C1, C2, C3, C4

// ============================================================================
// 2. HARDWARE DRIVER INSTANCES
// ============================================================================

Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);
Servo lockServo;
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

// ============================================================================
// 3. RUNTIME STATE & NON-BLOCKING TIMERS
// ============================================================================

String keypadBuffer = "";
bool isLocked = true;
bool keypadEnabled = true;
bool rfidAvailable = false;

// Non-blocking Auto-Relock Timer
unsigned long unlockTimestamp = 0;
unsigned long autoRelockDurationMs = AUTO_RELOCK_DEFAULT_MS;
bool autoRelockPending = false;

// Non-blocking Buzzer / Warning / Alarm Timers
unsigned long alarmUntilMs = 0;
bool alarmActive = false;
unsigned long lastAlarmToggleMs = 0;
bool alarmToneState = false;

// Non-blocking Denied Tone State Machine
unsigned long deniedStepTimestamp = 0;
int deniedStep = 0;

// Non-blocking Red LED Timer
unsigned long redLedOffTimestamp = 0;
bool redLedTimerActive = false;

// Non-blocking 4-Motor Getaway Timers & State
unsigned long motorStopTimestamp = 0;
bool motorsActive = false;
String currentMotorDirection = "STOPPED";

// Serial Line Receiver Buffer
String serialRxBuffer = "";

// ============================================================================
// 4. JSON TELEMETRY TRANSMISSION
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
// 5. ACOUSTIC TONE PROFILES (NON-BLOCKING)
// ============================================================================

void playKeyClickTone() {
    tone(BUZZER_PIN, 1000, 40);
}

void playClearTone() {
    tone(BUZZER_PIN, 700, 100);
}

void playSuccessTone() {
    tone(BUZZER_PIN, 2000, 400);
}

void startDeniedToneSequence() {
    tone(BUZZER_PIN, 500, 180);
    deniedStep = 1;
    deniedStepTimestamp = millis() + 220;
    
    // Light up Red LED
    digitalWrite(RED_LED, HIGH);
    redLedOffTimestamp = millis() + 1500;
    redLedTimerActive = true;
}

void setAlarm(unsigned long durationMs) {
    if (durationMs > 0) {
        alarmActive = true;
        alarmUntilMs = millis() + durationMs;
        digitalWrite(RED_LED, HIGH);
    } else {
        alarmActive = false;
        alarmUntilMs = 0;
        noTone(BUZZER_PIN);
        digitalWrite(RED_LED, LOW);
    }
}

// ============================================================================
// 6. 4-MOTOR GETAWAY CHASSIS CONTROLS
// ============================================================================

void stopMotors() {
    digitalWrite(M_LEFT_IN1, LOW);
    digitalWrite(M_LEFT_IN2, LOW);
    digitalWrite(M_RIGHT_IN3, LOW);
    digitalWrite(M_RIGHT_IN4, LOW);
    motorsActive = false;
    currentMotorDirection = "STOPPED";
    motorStopTimestamp = 0;

    JsonDocument payload;
    payload["status"] = "STOPPED";
    emitEvent("MOTOR_STOPPED", payload);
}

void driveMotors(String direction, unsigned long durationMs = 3000) {
    direction.toUpperCase();
    if (direction == "FORWARD") {
        digitalWrite(M_LEFT_IN1, HIGH);
        digitalWrite(M_LEFT_IN2, LOW);
        digitalWrite(M_RIGHT_IN3, HIGH);
        digitalWrite(M_RIGHT_IN4, LOW);
    } else if (direction == "BACKWARD" || direction == "REVERSE") {
        digitalWrite(M_LEFT_IN1, LOW);
        digitalWrite(M_LEFT_IN2, HIGH);
        digitalWrite(M_RIGHT_IN3, LOW);
        digitalWrite(M_RIGHT_IN4, HIGH);
    } else if (direction == "LEFT") {
        digitalWrite(M_LEFT_IN1, LOW);
        digitalWrite(M_LEFT_IN2, HIGH);
        digitalWrite(M_RIGHT_IN3, HIGH);
        digitalWrite(M_RIGHT_IN4, LOW);
    } else if (direction == "RIGHT") {
        digitalWrite(M_LEFT_IN1, HIGH);
        digitalWrite(M_LEFT_IN2, LOW);
        digitalWrite(M_RIGHT_IN3, LOW);
        digitalWrite(M_RIGHT_IN4, HIGH);
    } else {
        stopMotors();
        return;
    }

    motorsActive = true;
    currentMotorDirection = direction;
    if (durationMs > 0) {
        motorStopTimestamp = millis() + durationMs;
    } else {
        motorStopTimestamp = 0;
    }

    JsonDocument payload;
    payload["status"] = "RUNNING";
    payload["direction"] = direction;
    payload["duration_ms"] = durationMs;
    emitEvent("MOTOR_ACTIVATED", payload);
}

// ============================================================================
// 7. ACTUATOR & LOCK CONTROLS
// ============================================================================

void setLock(bool locked, unsigned long holdDurationMs = AUTO_RELOCK_DEFAULT_MS) {
    isLocked = locked;
    if (isLocked) {
        lockServo.write(LOCKED_POSITION);
        digitalWrite(GREEN_LED, LOW);
        stopMotors();
        autoRelockPending = false;
    } else {
        lockServo.write(UNLOCKED_POSITION);
        digitalWrite(GREEN_LED, HIGH);
        digitalWrite(RED_LED, LOW);
        playSuccessTone();
        unlockTimestamp = millis();
        autoRelockDurationMs = holdDurationMs > 0 ? holdDurationMs : AUTO_RELOCK_DEFAULT_MS;
        autoRelockPending = true;

        // 🚗 DRIVE THE VAULT AWAY ON AUTHENTICATION UNLOCK
        driveMotors("FORWARD", autoRelockDurationMs);
    }

    JsonDocument payload;
    payload["locked"] = isLocked;
    payload["state"] = isLocked ? "LOCKED" : "UNLOCKED";
    payload["servo_angle"] = isLocked ? LOCKED_POSITION : UNLOCKED_POSITION;
    emitEvent("LOCK_STATUS_REPORT", payload);
}

// ============================================================================
// 8. INBOUND SERIAL JSON COMMAND DISPATCHER
// ============================================================================

void processCommand(const String& jsonStr) {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, jsonStr);
    if (error) {
        return;
    }

    String cmd = doc["cmd"] | doc["command"] | "";
    cmd.toUpperCase();

    if (cmd == "COMMAND_UNLOCK" || (cmd == "SET_LOCK" && String(doc["state"] | "") == "UNLOCKED")) {
        unsigned long dur = doc["parameters"]["duration_ms"] | doc["duration_ms"] | AUTO_RELOCK_DEFAULT_MS;
        setLock(false, dur);
    }
    else if (cmd == "COMMAND_LOCK" || (cmd == "SET_LOCK" && String(doc["state"] | "") == "LOCKED")) {
        setLock(true);
    }
    else if (cmd == "DRIVE_MOTORS" || cmd == "MOTOR_DRIVE") {
        String dir = doc["direction"] | doc["parameters"]["direction"] | "FORWARD";
        unsigned long dur = doc["duration_ms"] | doc["parameters"]["duration_ms"] | 3000;
        driveMotors(dir, dur);
    }
    else if (cmd == "STOP_MOTORS" || cmd == "MOTOR_STOP") {
        stopMotors();
    }
    else if (cmd == "TRIGGER_ALARM") {
        unsigned long dur = doc["parameters"]["duration_ms"] | doc["duration_ms"] | 3000;
        setAlarm(dur);
    }
    else if (cmd == "SET_DISPLAY") {
        String led = doc["led"] | "";
        bool buzzer = doc["buzzer"] | false;

        if (led == "GREEN") {
            digitalWrite(GREEN_LED, HIGH);
            digitalWrite(RED_LED, LOW);
        } else if (led == "RED") {
            digitalWrite(RED_LED, HIGH);
            digitalWrite(GREEN_LED, LOW);
        } else if (led == "OFF") {
            digitalWrite(GREEN_LED, LOW);
            digitalWrite(RED_LED, LOW);
        }

        if (buzzer) {
            startDeniedToneSequence();
        }
    }
    else if (cmd == "ENABLE_KEYPAD") {
        keypadEnabled = true;
        keypadBuffer = "";
    }
    else if (cmd == "DISABLE_KEYPAD") {
        keypadEnabled = false;
        keypadBuffer = "";
    }
    else if (cmd == "PING") {
        JsonDocument payload;
        payload["pong"] = true;
        payload["locked"] = isLocked;
        payload["uptime_ms"] = millis();
        emitEvent("PONG", payload);
    }
}

// ============================================================================
// 8. PERIPHERAL POLLING ROUTINES
// ============================================================================

void pollKeypad() {
    char key = keypad.getKey();
    if (!key) return;

    playKeyClickTone();

    if (key == '#') {
        // Submit entered password / PIN to Python backend
        if (keypadBuffer.length() > 0) {
            JsonDocument payload;
            payload["pin"] = keypadBuffer;
            payload["length"] = keypadBuffer.length();
            emitEvent("KEYPAD_PIN_SUBMITTED", payload);
            keypadBuffer = "";
        }
    }
    else if (key == '*') {
        // Clear password buffer
        keypadBuffer = "";
        playClearTone();
        JsonDocument payload;
        payload["status"] = "CLEARED";
        emitEvent("KEYPAD_CLEARED", payload);
    }
    else {
        // Append key to buffer and stream keypress event
        keypadBuffer += key;
        JsonDocument payload;
        payload["key"] = String(key);
        payload["length"] = keypadBuffer.length();
        emitEvent("KEYPAD_KEY_PRESSED", payload);
    }
}

void pollRFID() {
    // Check if a card or tag is present in the RF field
    if (!rfid.PICC_IsNewCardPresent()) {
        return;
    }

    // Read card serial UID bytes
    if (!rfid.PICC_ReadCardSerial()) {
        return;
    }

    if (rfid.uid.size == 0) {
        return;
    }

    // Convert UID bytes to uppercase HEX string
    String cardUid = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) cardUid += "0";
        cardUid += String(rfid.uid.uidByte[i], HEX);
    }
    cardUid.toUpperCase();

    playKeyClickTone();

    JsonDocument payload;
    payload["card_uid"] = cardUid;
    payload["sak"] = rfid.uid.sak;
    payload["size"] = rfid.uid.size;
    emitEvent("RFID_SCANNED", payload);

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
}

void updateTimers() {
    unsigned long now = millis();

    // 1. Non-Blocking Auto-Relock
    if (autoRelockPending && (now - unlockTimestamp >= autoRelockDurationMs)) {
        setLock(true);
    }

    // 2. Non-Blocking 4-Motor Runaway Auto-Stop Timer
    if (motorsActive && motorStopTimestamp > 0 && now >= motorStopTimestamp) {
        stopMotors();
    }

    // 3. Denied Second Beep Tone Sequence
    if (deniedStep == 1 && now >= deniedStepTimestamp) {
        tone(BUZZER_PIN, 500, 180);
        deniedStep = 0;
    }

    // 4. Red LED Pulse Timer
    if (redLedTimerActive && now >= redLedOffTimestamp) {
        if (!alarmActive) {
            digitalWrite(RED_LED, LOW);
        }
        redLedTimerActive = false;
    }

    // 5. Warning / Alarm Siren Modulation
    if (alarmActive) {
        if (now < alarmUntilMs) {
            if (now - lastAlarmToggleMs >= 150) {
                lastAlarmToggleMs = now;
                alarmToneState = !alarmToneState;
                tone(BUZZER_PIN, alarmToneState ? 2400 : 1400);
                digitalWrite(RED_LED, alarmToneState ? HIGH : LOW);
            }
        } else {
            setAlarm(0);
        }
    }
}

// ============================================================================
// 10. SETUP & MAIN LOOP
// ============================================================================

void setup() {
    // 1. Initialize Serial UART at 115200 Baud
    Serial.begin(115200);
    while (!Serial && millis() < 1200);

    // 2. Initialize GPIO Output Pins (LEDs, Buzzer, 4-Motor Drivers)
    pinMode(GREEN_LED, OUTPUT);
    pinMode(RED_LED, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(RFID_RST_PIN, OUTPUT);
    digitalWrite(RFID_RST_PIN, HIGH);

    pinMode(M_LEFT_IN1, OUTPUT);
    pinMode(M_LEFT_IN2, OUTPUT);
    pinMode(M_RIGHT_IN3, OUTPUT);
    pinMode(M_RIGHT_IN4, OUTPUT);
    stopMotors();

    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED, LOW);

    // 3. Initialize Servo on GPIO 2 (50Hz PWM, 0 deg Locked)
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    lockServo.setPeriodHertz(50);
    lockServo.attach(SERVO_PIN, 500, 2400);
    lockServo.write(LOCKED_POSITION);

    // 4. Initialize MFRC522 RFID on SPI Bus with Max Antenna Gain
    SPI.begin(RFID_SCK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
    rfid.PCD_Init();
    delay(50);
    rfid.PCD_SetAntennaGain(rfid.RxGain_max);
    rfid.PCD_AntennaOn();
    rfidAvailable = true;

    // 5. Startup Chirp
    tone(BUZZER_PIN, 1800, 100);
    delay(120);
    tone(BUZZER_PIN, 2400, 150);

    // 6. Announce Hardware Boot Status to Python Backend
    JsonDocument bootDoc;
    bootDoc["firmware"] = "VAULT-404-ESP32";
    bootDoc["version"] = "2.1.0";
    bootDoc["rfid_available"] = rfidAvailable;
    bootDoc["servo_locked"] = isLocked;
    emitEvent("HARDWARE_BOOT", bootDoc);
}

void loop() {
    // 1. Process Inbound Serial JSON Commands from Host
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n') {
            serialRxBuffer.trim();
            if (serialRxBuffer.length() > 0) {
                processCommand(serialRxBuffer);
            }
            serialRxBuffer = "";
        } else if (c != '\r') {
            serialRxBuffer += c;
        }
    }

    // 2. Poll Physical Peripherals
    pollKeypad();
    pollRFID();

    // 3. Update Non-Blocking Timers & Relock Actuation
    updateTimers();

    delay(5); // Small power-efficient yield
}
