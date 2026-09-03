# 🔒 The Inconvenient Vault

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP32-orange.svg)](https://platformio.org/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/Tests-66%20Passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> An intentionally over-engineered, hardware-decoupled, 5-stage sequential authentication system backed by computer vision embeddings, acoustic speech feature analysis, Argon2id cryptography, and tamper-evident SHA-256 hash-chained audit trails.

---

## 📖 Executive Summary & Concept

**The Inconvenient Vault** explores extreme defense-in-depth and intentional security friction. Unlocking the physical solenoid requires an operator to execute five strictly ordered multi-modal authentication stages in a single continuous session:

$$\mathbf{IDLE} \xrightarrow{\text{Stage 1}} \mathbf{RFID} \xrightarrow{\text{Stage 2}} \mathbf{Fingerprint} \xrightarrow{\text{Stage 3}} \mathbf{Face\ Scan} \xrightarrow{\text{Stage 4}} \mathbf{Password} \xrightarrow{\text{Stage 5}} \mathbf{Voice\ Phrase} \xrightarrow{\text{Actuate}} \mathbf{UNLOCKED}$$

### Key Engineering Pillars
- **Strict Finite State Machine (FSM)**: Enforces exact sequence order. Out-of-order submissions are rejected instantly. Any three cumulative failures, chassis tamper sensor trips, or stage idle timeouts immediately force the system into a fail-secure `LOCKOUT` state accompanied by strobe alarms and siren actuation.
- **Hardware-Decoupled Architecture**: Abstract Base Classes (`HardwareInterface`, `CameraCaptureInterface`, `AudioCaptureInterface`, `VaultRepositoryInterface`) isolate core FSM security logic from physical microcontrollers, sound cards, and cameras.
- **Biometric Vector Pipelines**:
  - *Facial Biometrics*: Central ROI normalized spatial moments + Histogram of Oriented Gradients (HOG) combined into a 256-dimensional zero-mean unit vector with Laplacian variance focus anti-spoofing checks.
  - *Voice Biometrics*: Welch Power Spectral Density (PSD) sub-band energy moments + autocorrelation pitch-lag tracking combined into an $L_2$-normalized 256-dimensional speaker voiceprint vector.
- **Cryptographic Hash-Chained Audit Trail**: Every state transition, failure, and hardware event is appended to an immutable database log where each record stores the SHA-256 digest of the previous row's hash plus current event data ($\text{Hash}_n = \mathcal{H}(\text{Hash}_{n-1} \parallel \text{Payload}_n)$).
- **Dual-Target Orchestration**: The same Python backend runs 100% in simulation mode via software emulators or drives real physical microcontrollers via high-speed USB/UART framed JSON protocol.

---

## 🏛️ System Architecture

```
                                  ┌──────────────────────────────────────────────┐
                                  │   Cyberpunk Operator Web Dashboard (HUD)     │
                                  │   (Vanilla JS, HTML5, CSS3, WebRTC Stream)   │
                                  └──────────────────────┬───────────────────────┘
                                                         │ HTTP REST & Bidirectional WebSockets (/ws/vault)
                                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           FastAPI Application Server (:8000)                                           │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                               VaultAuthEngine (Core FSM)                                               │
│       IDLE ──► AWAITING_RFID ──► AWAITING_FINGERPRINT ──► AWAITING_FACE ──► AWAITING_PASSWORD ──► AWAITING_VOICE       │
├──────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────┤
│    Computer Vision Subsystem         │      Acoustic Voice Subsystem        │     Database & Audit Persistence         │
│    - FaceVerifier (256D Embeddings)  │      - VoiceVerifier (256D Vectors)  │     - SQLAlchemy 2.0 Async Session       │
│    - Laplacian Anti-Spoofing         │      - Welch PSD & Pitch Lag Profile │     - Multi-Modal User Credential Store  │
│    - MockCameraAdapter               │      - MockAudioAdapter              │     - SHA-256 Hash-Chained Audit Logs    │
├──────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────┤
│                                          Hardware Abstraction Layer (HAL)                                              │
│                                                HardwareInterface (ABC)                                                 │
│                             ┌─────────────────────────────┴─────────────────────────────┐                              │
│                             ▼                                                           ▼                              │
│                MockHardwareAdapter (Virtual)                               ESP32SerialAdapter (Physical)               │
│                - Thread/Async Safe State Tracking                          - Asynchronous Serial Transport             │
│                - Non-blocking Listener Dispatch                            - 115200 Baud JSON Frame RPC                │
└─────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────┘
                                                                                          │ UART Serial (USB / COM Port)
                                                                                          ▼
                                                              ┌──────────────────────────────────────────────────────────┐
                                                              │            ESP32 Embedded C++ Firmware                   │
                                                              │  - RC522 RFID SPI Reader (GPIO 5, 4, 18, 19, 23)         │
                                                              │  - AS608 / R503 Fingerprint UART (GPIO 16, 17)           │
                                                              │  - I2C LCD 16x2 / SSD1306 OLED Display (GPIO 21, 22)     │
                                                              │  - Solenoid Relay (GPIO 26) & Buzzer (GPIO 27)           │
                                                              │  - RGB LED Beacons (GPIO 12, 13, 14)                     │
                                                              │  - Hardware Tamper Interrupt (GPIO 34)                   │
                                                              └──────────────────────────────────────────────────────────┘
```

---

## 🔄 Sequential Authentication Pipeline

| Stage | Expected Input | Validation Mechanics | Threshold / Criteria | Fail-Secure Action |
| :--- | :--- | :--- | :--- | :--- |
| **0: IDLE** | Operator triggers `start_authentication()` | Checks that vault is in clean standby state. | None | Rejects input if locked out. |
| **1: RFID** | 13.56MHz Mifare Tag UID (Hex) | Evaluates UID against enrolled database profile (`E2806894`). | Exact String Match | Decrements retry count; unlocks user profile on match. |
| **2: Fingerprint** | Optical Scan ID (1..127) | Evaluates biometric slot ID and template matching confidence. | Confidence $\ge 0.85$ | Decrements retry count; advances to Stage 3. |
| **3: Face Scan** | Webcam / Stream Frame (H, W, 3) | Extracts 256D normalized vector; evaluates cosine similarity and Laplacian blur sharpness. | Cosine Sim $\ge 0.90$, Variance $\ge 15.0$ | Decrements retry count; rejects spoof / blur. |
| **4: Password** | Alphanumeric Passphrase | Verifies plaintext input against enrolled Argon2id cryptographic hash. | Argon2 Verification | Decrements retry count; advances to Stage 5. |
| **5: Voice** | Acoustic Waveform + Spoken Phrase | Computes 256D spectral voiceprint and verifies both speaker timbre and challenge text. | Cosine Sim $\ge 0.85$ & Exact Phrase Match | Disengages lock relay; sets state to `UNLOCKED`. |
| **UNLOCKED** | Standby | Holds solenoid open for 10 seconds. | Auto-relock timer | Auto-engages solenoid lock and resets to `IDLE`. |

---

## 💻 Software-First / Simulation Strategy

The vault is designed with zero physical hardware dependencies during software engineering and automated CI/CD:
1. **`MockHardwareAdapter`**: Emulates solenoid relay actuation, status LCD lines, RGB LEDs, and buzzer alarms completely in-memory.
2. **`MockCameraAdapter`**: Synthetically renders parameterized facial portraits with distinct skin tones, facial geometry, focus blurs, and sensor noise based on deterministic seeds (e.g. `Seed 777` for authorized operator, `Seed 999` for intruder).
3. **`MockAudioAdapter`**: Synthesizes vocal pitch fundamentals ($F_0$), vocal tract formant resonances ($F_1, F_2, F_3$), syllable amplitude envelopes, and acoustic noise based on speaker seeds (e.g. `Seed 1` for operator, `Seed 2` for intruder).

---

## 🚀 Getting Started (Local Development)

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13
- Git

### 2. Installation
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

### 3. Running the Interactive CLI Terminal Simulator
Experience the complete sequential vault simulator directly in your terminal with live ANSI LCD screen and color badges:
```bash
python cli_simulator.py
```
*(To run automated non-interactive smoke test: `python cli_simulator.py --smoke-test`)*

### 4. Running the Web Operator HUD & FastAPI Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser to access the Cyberpunk Operator Console.

---

## 🔌 Hardware Deployment Guide (ESP32 Integration)

To connect the Python backend to a physical ESP32 microcontroller with real sensors:

### 1. Wiring & Pinout Matrix

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
| | SCL | **GPIO 22** | I2C Clock (0x27) |
| | VCC / GND | 5V / GND | Power Pins |
| **Solenoid Relay Module** | IN / SIG | **GPIO 26** | Active HIGH triggers lock release |
| **Active Buzzer** | SIG | **GPIO 27** | Audible alarm & chirp alerts |
| **RGB LED Beacon** | Red / Green / Blue | **GPIO 12, 13, 14** | Common Cathode / Anode |
| **Chassis Tamper Switch** | Switch Pin | **GPIO 34** | Active LOW interrupt (`FALLING`) |

### 2. Compiling and Flashing Firmware (PlatformIO)
```bash
# Navigate to firmware directory
cd firmware/esp32_vault

# Build and upload firmware to connected ESP32
pio run --target upload

# Open serial monitor
pio device monitor --baud 115200
```

### 3. Running Backend in Real Hardware Mode
```bash
# Set environment variables
export VAULT_HARDWARE_MODE=REAL
export VAULT_SERIAL_PORT=COM3    # On Windows (e.g. COM3) or /dev/ttyUSB0 on Linux

# Launch backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 🔍 Forensic Audit Trails & Hash Chain Verification

Every security event is logged in SQLite with cryptographic SHA-256 chaining:

$$\text{EntryHash}_n = \text{SHA256}(\text{EntryHash}_{n-1} \parallel \text{Timestamp} \parallel \text{UserID} \parallel \text{Stage} \parallel \text{EventType} \parallel \text{Metadata})$$

### Verifying Chain Integrity Programmatically
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

---

## 🧪 Comprehensive Automated Test Suite

Run the full pytest suite (66 tests covering all 10 architectural steps):

```bash
pytest -v
```

```
============================= test session starts =============================
collected 66 items

test_step1.py (12 tests)  - Domain types, immutability, DisplayStatus, ABC contracts.
test_step2.py (11 tests)  - MockHardwareAdapter concurrency, event dispatch, actuators.
test_step3.py (10 tests)  - VaultAuthEngine FSM, strict sequence, lockout, timeouts.
test_step5.py (8 tests)   - Camera capture, 256D face embeddings, anti-spoofing blur.
test_step6.py (8 tests)   - Audio capture, 256D voiceprints, two-factor speech verification.
test_step7.py (4 tests)   - Multi-modal SQLite persistence, SHA-256 hash-chain verification.
test_step8.py (5 tests)   - FastAPI REST API endpoints, WebSocket event broadcast hub.
test_step9.py (4 tests)   - Web Dashboard static asset delivery & UI client flows.
test_step10.py (4 tests)  - Hardware factory, ESP32 serial JSON protocol, fault-tolerance.

============================= 66 passed in 8.34s ==============================
```

---

## 📂 Repository Structure

```
vault-404/
├── app/
│   ├── adapters/                  # Hardware & Simulation Adapters
│   │   ├── __init__.py
│   │   ├── esp32_hardware.py      # Production USB/UART Serial Adapter
│   │   ├── factory.py             # Hardware Mode Factory (REAL vs SIMULATED)
│   │   ├── mock_audio.py          # Synthetic Vocal Waveform Synthesizer
│   │   ├── mock_camera.py         # Synthetic Central ROI Face Frame Generator
│   │   └── mock_hardware.py       # Thread-safe In-Memory Virtual Peripheral Emulator
│   ├── api/                       # FastAPI REST & WebSocket Routing
│   │   ├── __init__.py
│   │   ├── routes.py              # REST endpoints & /ws/vault stream
│   │   ├── schemas.py             # Pydantic v2 Request/Response Data Envelopes
│   │   └── websocket_manager.py   # Connection Hub & Event Broadcaster
│   ├── audio/                     # Acoustic Signal Processing Subsystem
│   │   ├── __init__.py
│   │   └── voice_verifier.py      # 256D Welch PSD + Pitch-Lag Voiceprint Verifier
│   ├── core/                      # Core FSM & Domain Definitions
│   │   ├── __init__.py
│   │   ├── engine.py              # Central VaultAuthEngine State Machine
│   │   └── types.py               # VaultState, HardwareEvent, DisplayStatus
│   ├── database/                  # SQLite Persistence & Hash-Chained Audit Logs
│   │   ├── __init__.py
│   │   ├── models.py              # SQLAlchemy 2.0 User & AuditLog Declarations
│   │   ├── repository.py          # SqliteVaultRepository with SHA-256 Hash Chaining
│   │   └── session.py             # Async Database Engine & Schema Initializer
│   ├── interfaces/                # Abstract Hardware & Subsystem Contracts (ABCs)
│   │   ├── __init__.py
│   │   ├── audio.py               # AudioCaptureInterface, VoiceVerifierInterface
│   │   ├── hardware.py            # HardwareInterface
│   │   ├── repository.py          # VaultRepositoryInterface
│   │   └── vision.py              # CameraCaptureInterface, FaceRecognizerInterface
│   ├── static/                    # Cyberpunk Web Operator Console
│   │   ├── css/
│   │   │   └── dashboard.css      # Phosphor HUD, OLED box, Stepper, Lock Graphic
│   │   ├── js/
│   │   │   └── vault_client.js    # Auto-reconnecting WS, WebRTC Capture, REST client
│   │   └── index.html             # Semantic Single-Page Dashboard
│   └── vision/                    # Computer Vision Subsystem
│       ├── __init__.py
│       └── face_verifier.py       # 256D Facial Embedding Extractor & Liveness Checker
├── firmware/
│   └── esp32_vault/               # ESP32 Embedded Microcontroller Project
│       ├── platformio.ini         # PlatformIO Environment Configuration
│       └── src/
│           └── main.cpp           # Non-blocking Embedded C++ Peripheral Firmware
├── cli_simulator.py               # Terminal Interactive ANSI CLI Testing Harness
├── requirements.txt               # Locked Production Dependencies
├── test_step1.py ... test_step10.py # Comprehensive Automated Test Suites
└── README.md                      # Production Documentation
```

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
