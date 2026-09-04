<img width="1280" height="640" alt="git (1)" src="https://github.com/user-attachments/assets/8920b256-2ba8-4988-b824-5351134eb4bd" />

# 🔒 The Inconvenient Vault (Vault-404) 🎯

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![ESP32 Arduino](https://img.shields.io/badge/ESP32-Arduino%20IDE-orange.svg)](https://www.arduino.cc/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Argon2id](https://img.shields.io/badge/Argon2-Argon2id%20Crypto-blueviolet.svg)](https://en.wikipedia.org/wiki/Argon2)
[![OpenCV](https://img.shields.io/badge/Vision-OpenCV%20Webcam-green.svg)](https://opencv.org/)
[![SoundDevice](https://img.shields.io/badge/Audio-SoundDevice%20Mic-yellow.svg)](https://python-sounddevice.readthedocs.io/)

> An intentionally over-engineered multi-modal physical security vault driven by an ESP32 microcontroller, OpenCV computer vision, acoustic microphone feature analysis, Argon2id cryptography, and a tamper-evident SHA-256 hash-chained audit ledger.

## Basic Details
### Team Name: Eclipse

### Team Members
- Team Lead: Blessy mol charls  - Muthoot Institute of Technology and Science
- Member 2: V M Samerath Kumar - Muthoot Institute of Technology and Science

### Project Description
An intentionally over-engineered, hardware-decoupled, 5-stage sequential authentication system backed by computer vision embeddings, acoustic speech feature analysis, Argon2id cryptography, and tamper-evident SHA-256 hash-chained audit trails.

### The Problem (that doesn't exist)
Opening physical boxes and vaults is simply too easy and convenient. People can just use a single key, or worse, just pull a handle. This lack of friction means anyone can access their own belongings without going through a grueling, multi-modal biometric and cryptographic gauntlet.

### The Solution (that nobody asked for)
We built a sequential 5-stage authentication system (RFID -> Fingerprint -> Face Scan -> Password -> Voice Phrase) that forces the user to prove their identity in five distinct ways before a simple solenoid relay is triggered. If they fail any step, they get locked out!

## Technical Details
### Technologies/Components Used
For Software:
- **Languages used**: Python 3.10+, JavaScript (Vanilla), HTML5, CSS3, C/C++
- **Frameworks used**: FastAPI
- **Libraries used**: OpenCV, SQLAlchemy 2.0, WebRTC
- **Tools used**: PlatformIO, pytest

For Hardware:
- **List main components**: ESP32 Microcontroller, MFRC522 RFID Reader, AS608/R503 Fingerprint Sensor, I2C LCD (16x2 / 20x4), Solenoid Relay Module, Active Buzzer, RGB LED Beacon, Chassis Tamper Switch
- **List specifications**: 13.56MHz RFID, Optical Fingerprint 1..127 IDs, I2C Display, 115200 Baud JSON Frame RPC
- **List tools required**: PlatformIO for firmware compilation

### Implementation
For Software:
# Installation
```bash
# Clone the repository
git clone https://github.com/bless/vault-404.git
cd vault-404

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

# Run
```bash
# Running the Interactive CLI Terminal Simulator
python cli_simulator.py

# Running the Web Operator HUD & FastAPI Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser to access the Cyberpunk Operator Console.

### Project Documentation
For Software:

# Screenshots (Add at least 3)
![Screenshot1](Add screenshot 1 here with proper name)
*Add caption explaining what this shows*

![Screenshot2](Add screenshot 2 here with proper name)
*Add caption explaining what this shows*

![Screenshot3](Add screenshot 3 here with proper name)
*Add caption explaining what this shows*

# Diagrams
**System Architecture**
```text
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

## 🏛️ Physical Hardware Architecture

**Sequential Authentication Pipeline**
| Stage | Expected Input | Validation Mechanics | Threshold / Criteria | Fail-Secure Action |
| :--- | :--- | :--- | :--- | :--- |
| **0: IDLE** | Operator triggers `start_authentication()` | Checks that vault is in clean standby state. | None | Rejects input if locked out. |
| **1: RFID** | 13.56MHz Mifare Tag UID (Hex) | Evaluates UID against enrolled database profile (`E2806894`). | Exact String Match | Decrements retry count; unlocks user profile on match. |
| **2: Fingerprint** | Optical Scan ID (1..127) | Evaluates biometric slot ID and template matching confidence. | Confidence $\ge 0.85$ | Decrements retry count; advances to Stage 3. |
| **3: Face Scan** | Webcam / Stream Frame (H, W, 3) | Extracts 256D normalized vector; evaluates cosine similarity and Laplacian blur sharpness. | Cosine Sim $\ge 0.90$, Variance $\ge 15.0$ | Decrements retry count; rejects spoof / blur. |
| **4: Password** | Alphanumeric Passphrase | Verifies plaintext input against enrolled Argon2id cryptographic hash. | Argon2 Verification | Decrements retry count; advances to Stage 5. |
| **5: Voice** | Acoustic Waveform + Spoken Phrase | Computes 256D spectral voiceprint and verifies both speaker timbre and challenge text. | Cosine Sim $\ge 0.85$ & Exact Phrase Match | Disengages lock relay; sets state to `UNLOCKED`. |
| **UNLOCKED** | Standby | Holds solenoid open for 10 seconds. | Auto-relock timer | Auto-engages solenoid lock and resets to `IDLE`. |

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
| **4-Motor Driver (Left)** | IN1 / IN2 (Left Motors Forward / Rev) | **GPIO 16, 17** | Dual H-Bridge (L298N / TB6612FNG) |
| **4-Motor Driver (Right)** | IN3 / IN4 (Right Motors Forward / Rev) | **GPIO 0, 1** | Dual H-Bridge (L298N / TB6612FNG) |
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

For Hardware:

# Schematic & Circuit
**Hardware Deployment Guide (ESP32 Integration)**
| Peripheral Component | Pin Name | ESP32 GPIO | Notes |
| :--- | :--- | :--- | :--- |
| **MFRC522 RFID Reader** | SDA / SS | **GPIO 5** | SPI Chip Select |
| | SCK | **GPIO 18** | SPI Clock |
| | MOSI | **GPIO 23** | SPI Master Out |
| | MISO | **GPIO 19** | SPI Master In |
| | RST | **GPIO 4** | Reset Pin |
| | 3.3V / GND | 3.3V / GND | **Do not power with 5V** |
| **Fingerprint Sensor (AS608/R503)** | TX | **GPIO 16 (RX2)** | HardwareSerial 2 |
| | RX | **GPIO 17 (TX2)** | HardwareSerial 2 |
| | VCC / GND | 5V / GND | Power Pins |
| **I2C LCD (16x2 / 20x4)** | SDA | **GPIO 21** | I2C Data (0x27) |
| **Solenoid Relay Module** | IN / SIG | **GPIO 26** | Active HIGH triggers lock release |
| **Active Buzzer** | SIG | **GPIO 27** | Audible alarm & chirp alerts |
| **RGB LED Beacon** | Red / Green / Blue | **GPIO 12, 13, 14** | Common Cathode / Anode |
| **Chassis Tamper Switch** | Switch Pin | **GPIO 34** | Active LOW interrupt (`FALLING`) |

# Build Photos
![Team](Add photo of your team here)

### Project Demo
# Video
[Add your demo video link here]
*Explain what the video demonstrates*

# Additional Demos
[Add any extra demo materials/links]

## Additional Project Details

### Software-First / Simulation Strategy
The vault is designed with zero physical hardware dependencies during software engineering and automated CI/CD:
1. **`MockHardwareAdapter`**: Emulates solenoid relay actuation, status LCD lines, RGB LEDs, and buzzer alarms completely in-memory.
2. **`MockCameraAdapter`**: Synthetically renders parameterized facial portraits with distinct skin tones, facial geometry, focus blurs, and sensor noise based on deterministic seeds (e.g. `Seed 777` for authorized operator, `Seed 999` for intruder).
3. **`MockAudioAdapter`**: Synthesizes vocal pitch fundamentals ($F_0$), vocal tract formant resonances ($F_1, F_2, F_3$), syllable amplitude envelopes, and acoustic noise based on speaker seeds (e.g. `Seed 1` for operator, `Seed 2` for intruder).

### Forensic Audit Trails & Hash Chain Verification
Every security event is logged in SQLite with cryptographic SHA-256 chaining:
$$\text{EntryHash}_n = \text{SHA256}(\text{EntryHash}_{n-1} \parallel \text{Timestamp} \parallel \text{UserID} \parallel \text{Stage} \parallel \text{EventType} \parallel \text{Metadata})$$

**Verifying Chain Integrity Programmatically:**
```python
import asyncio
from app.database.session import create_database_engine, create_session_factory
from app.database.repository import SqliteVaultRepository

async def verify():
    engine = create_database_engine("sqlite+aiosqlite:///vault.db")
    sf = create_session_factory(engine)
    repo = SqliteVaultRepository(sf)
    is_valid, error = await repo.verify_audit_trail_integrity()
    print(f"Audit Trail Integrity: {'VALID' if is_valid else 'CORRUPTED'}")
    if error:
        print(f"Tamper details: {error}")
    await engine.dispose()

asyncio.run(verify())
```

### Comprehensive Automated Test Suite
Run the full pytest suite (66 tests covering all 10 architectural steps):
```bash
pytest -v
```

### Repository Structure
```
vault-404/
├── app/
│   ├── adapters/                  # Hardware & Simulation Adapters
│   ├── api/                       # FastAPI REST & WebSocket Routing
│   ├── audio/                     # Acoustic Signal Processing Subsystem
│   ├── core/                      # Core FSM & Domain Definitions
│   ├── database/                  # SQLite Persistence & Hash-Chained Audit Logs
│   ├── interfaces/                # Abstract Hardware & Subsystem Contracts (ABCs)
│   ├── static/                    # Cyberpunk Web Operator Console
│   └── vision/                    # Computer Vision Subsystem
├── firmware/                      # ESP32 Embedded Microcontroller Project
├── cli_simulator.py               # Terminal Interactive ANSI CLI Testing Harness
├── requirements.txt               # Locked Production Dependencies
├── test_step1.py ... test_step10.py # Comprehensive Automated Test Suites
└── README.md                      # Production Documentation
```

## Team Contributions
- [Name 1]: [Specific contributions]
- [Name 2]: [Specific contributions]
- [Name 3]: [Specific contributions]

---
Made with ❤️ at TinkerHub Useless Projects
