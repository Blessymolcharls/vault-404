# 🔒 The Inconvenient Vault (Vault-404)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![ESP32 Arduino](https://img.shields.io/badge/ESP32-Arduino%20IDE-orange.svg)](https://www.arduino.cc/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Argon2id](https://img.shields.io/badge/Argon2-Argon2id%20Crypto-blueviolet.svg)](https://en.wikipedia.org/wiki/Argon2)
[![OpenCV](https://img.shields.io/badge/Vision-OpenCV%20Webcam-green.svg)](https://opencv.org/)
[![SoundDevice](https://img.shields.io/badge/Audio-SoundDevice%20Mic-yellow.svg)](https://python-sounddevice.readthedocs.io/)

> An intentionally over-engineered multi-modal physical security vault driven by an ESP32 microcontroller, OpenCV computer vision, acoustic microphone feature analysis, Argon2id cryptography, and a tamper-evident SHA-256 hash-chained audit ledger.

---

## 🏛️ Physical Hardware Architecture

```
                                  ┌──────────────────────────────────────────────┐
                                  │   Cyberpunk Operator Web Dashboard (HUD)     │
                                  │   (Vanilla JS, HTML5, CSS3, WebSockets)      │
                                  └──────────────────────┬───────────────────────┘
                                                         │ HTTP REST & WebSockets (/ws/vault)
                                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           FastAPI Application Server (:8000)                                           │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                               VaultAuthEngine (Core FSM)                                               │
│       IDLE ──► AWAITING_RFID ──► AWAITING_FACE ──► AWAITING_KEYPAD_PIN ──► AWAITING_VOICE ──► UNLOCKED                 │
├──────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────┤
│    Computer Vision Subsystem         │      Acoustic Voice Subsystem        │     Database & Audit Persistence         │
│    - OpenCVCameraAdapter (cv2)       │      - SoundDeviceAudioAdapter       │     - SQLAlchemy 2.0 Async Session       │
│    - FaceVerifier (256D Embeddings)  │      - VoiceVerifier (256D Vectors)  │     - Multi-Modal User Credential Store  │
│    - Laplacian Anti-Spoofing Filter  │      - Welch PSD & Pitch Lag Profile │     - SHA-256 Hash-Chained Audit Logs    │
├──────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────┤
│                                          Production Hardware Serial Adapter                                            │
│                                                ESP32SerialAdapter                                                      │
│                                    - High-speed UART (115200 Baud JSON RPC)                                            │
│                                    - Bidirectional Framed Telemetry & Actuation                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────┘
                                                                                          │ USB UART (COM Port / /dev/ttyUSB0)
                                                                                          ▼
                                                              ┌──────────────────────────────────────────────────────────┐
                                                              │            ESP32 Embedded C++ Firmware                   │
                                                              │  - 4x4 Matrix Keypad (Rows: 13,12,14,27 | Cols: 26,25,33,32)│
                                                              │  - MFRC522 RFID SPI Reader (GPIO 5, 4, 18, 19, 23)       │
                                                              │  - AS608 Optical Fingerprint UART2 (GPIO 16, 17)         │
                                                              │  - Micro Servo Lock Actuator (GPIO 2)                    │
                                                              │  - Green LED (GPIO 22) & Red LED (GPIO 15)               │
                                                              │  - Active Buzzer / Tone (GPIO 21)                        │
                                                              │  - Chassis Tamper Switch Interrupt (GPIO 34)             │
                                                              └──────────────────────────────────────────────────────────┘
```

---

## 🔌 ESP32 Pinout & Wiring Matrix

| Peripheral Component | Pin Name | ESP32 GPIO | Electrical / Protocol Notes |
| :--- | :--- | :--- | :--- |
| **4x4 Matrix Keypad** | Row 1 / Row 2 / Row 3 / Row 4 | **GPIO 13, 12, 14, 27** | Driven as outputs sequentially |
| | Col 1 / Col 2 / Col 3 / Col 4 | **GPIO 26, 25, 33, 32** | Read as inputs with internal pull-ups |
| **Lock Servo** | PWM Signal | **GPIO 2** | `0°` = Locked, `90°` = Unlocked (50Hz PWM) |
| **Status Green LED** | Granted Indicator | **GPIO 22** | Active-High with 220Ω current resistor |
| **Status Red LED** | Denied / Alarm | **GPIO 15** | Active-High with 220Ω current resistor |
| **Active Buzzer** | Audio Feedback | **GPIO 21** | PWM tone generator (1000Hz, 2000Hz, etc.) |
| **MFRC522 RFID** | SDA(SS) / SCK / MOSI / MISO / RST | **GPIO 5, 18, 23, 19, 4** | SPI Bus ($3.3\text{V}$) |
| **AS608 Fingerprint** | RX2 / TX2 | **GPIO 16, 17** | Hardware Serial 2 (57600 Baud) |
| **Tamper Switch** | Interrupt | **GPIO 34** | Active-Low interrupt (triggers lockout) |

---

## 🚀 Quickstart & Deployment Guide

### 1. Python Environment Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (.env)
cp .env.example .env
# Set your actual vault password in .env:
# VAULT_PASSWORD=YourSecretPassword123!
```

### 2. Flashing the ESP32 (Arduino IDE)
1. Open **Arduino IDE**.
2. Open the sketch: [`firmware/arduino_vault/arduino_vault.ino`](file:///c:/Users/bless/GIT/vault-404/firmware/arduino_vault/arduino_vault.ino).
3. Install required libraries from Library Manager (`Ctrl + Shift + I`):
   - `Keypad` by Mark Stanley, Alexander Brevig
   - `ESP32Servo` by Kevin Harrington
   - `MFRC522` by GithubCommunity / miguelbalboa
   - `Adafruit Fingerprint Sensor Library` by Adafruit
   - `ArduinoJson` by Benoit Blanchon (v7.x or v6.x)
4. Select Board: **ESP32 Dev Module**.
5. Select Port: (e.g. `COM3` on Windows or `/dev/ttyUSB0` on Linux).
6. Click **Upload**.

### 3. Run Physical Hardware Diagnostic Suite
Test all physical hardware peripherals interactively:
```powershell
python test_hardware_live.py
```
*(To test without waiting for physical inputs: `python test_hardware_live.py --dry-run`)*

### 4. Run the Vault-404 Backend Server & Web Terminal
```powershell
# Set your secure password:
$env:VAULT_PASSWORD="YourSecretPassword123!"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** to view the live security terminal.

### 5. Automated Tests
```powershell
python -m pytest test_password_auth_architecture.py test_keypad_hardware_integration.py
```
