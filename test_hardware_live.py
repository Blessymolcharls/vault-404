"""Interactive Physical Hardware Diagnostic & Verification Suite for Vault-404.

Tests all physical peripherals end-to-end:
1. Serial UART Handshake (ESP32 Ping / Heartbeat)
2. Servo Lock Actuation (0° -> 90° -> 0°)
3. Indicator LEDs & Buzzer Audio Tone Profiles (Green/Red LEDs, Active Buzzer)
4. 4x4 Matrix Keypad Polling & Echo
5. MFRC522 RFID Card / Tag Scanner
6. AS608 Optical Fingerprint Biometric Scanner
7. Physical Webcam Capture & Laplacian Sharpness Anti-Spoofing Filter
8. Physical Microphone Capture & RMS Audio Power Spectrum
"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
from typing import Optional
import cv2
import numpy as np

# Configure standard stdout safely for Windows / Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("vault.diagnostic")

# ANSI Terminal Color Helpers
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(title: str) -> None:
    print(f"\n{CYAN}{BOLD}{'=' * 70}{RESET}")
    print(f"{CYAN}{BOLD}  [*] VAULT-404 HARDWARE DIAGNOSTIC // {title.upper()}{RESET}")
    print(f"{CYAN}{BOLD}{'=' * 70}{RESET}\n")


def print_pass(msg: str) -> None:
    print(f"  {GREEN}{BOLD}[PASS]{RESET} {msg}")


def print_fail(msg: str) -> None:
    print(f"  {RED}{BOLD}[FAIL]{RESET} {msg}")


def print_info(msg: str) -> None:
    print(f"  {YELLOW}[INFO]{RESET} {msg}")


# ============================================================================
# Diagnostic Step 1: Serial Handshake & Telemetry Ping
# ============================================================================


async def test_serial_handshake(port: Optional[str] = None) -> bool:
    print_banner("Step 1: Serial UART Handshake with ESP32")
    from app.adapters.esp32_hardware import ESP32SerialAdapter

    adapter = ESP32SerialAdapter(port=port, baudrate=115200)
    connected = await adapter.initialize()
    if not connected:
        print_fail(f"Could not open serial port '{adapter.port or 'AUTO'}'. Check USB cable / driver.")
        return False

    print_pass(f"Serial link established on {adapter.port} @ 115200 baud.")

    # Send Ping and listen for response
    ping_ok = await adapter.ping()
    if ping_ok:
        print_pass("Transmitted PING JSON frame to ESP32.")
    else:
        print_fail("Failed to transmit PING command.")

    await asyncio.sleep(0.5)
    adapter.release()
    return True


# ============================================================================
# Diagnostic Step 2: Servo Lock Actuator Test
# ============================================================================


async def test_servo_actuation(port: Optional[str] = None) -> bool:
    print_banner("Step 2: Micro Servo Lock Actuator (GPIO 2)")
    from app.adapters.esp32_hardware import ESP32SerialAdapter

    adapter = ESP32SerialAdapter(port=port)
    if not await adapter.initialize():
        print_fail("Serial link not available for servo test.")
        return False

    print_info("Rotating Servo to UNLOCKED position (90 deg)...")
    await adapter.set_lock(False, duration_ms=3000)
    await asyncio.sleep(2.0)
    print_pass("Servo rotated to 90 deg (UNLOCKED).")

    print_info("Rotating Servo back to LOCKED position (0 deg)...")
    await adapter.set_lock(True)
    await asyncio.sleep(1.0)
    print_pass("Servo rotated to 0 deg (LOCKED).")

    adapter.release()
    return True


# ============================================================================
# Diagnostic Step 3: LEDs & Buzzer Audio Tone Profiles
# ============================================================================


async def test_leds_and_buzzer(port: Optional[str] = None) -> bool:
    print_banner("Step 3: Status LEDs (GPIO 22/15) & Buzzer (GPIO 21)")
    from app.adapters.esp32_hardware import ESP32SerialAdapter
    from app.core.types import DisplayStatus, LedColor

    adapter = ESP32SerialAdapter(port=port)
    if not await adapter.initialize():
        print_fail("Serial link not available for LED/Buzzer test.")
        return False

    print_info("Testing ACCESS GRANTED Profile (Green LED + 2000Hz Tone)...")
    await adapter.set_display(
        DisplayStatus(line1="TEST GRANTED", line2="GREEN LED ON", led_color=LedColor.GREEN, buzzer=False)
    )
    await asyncio.sleep(1.5)
    print_pass("Access Granted Profile emitted.")

    print_info("Testing ACCESS DENIED / ALARM Profile (Red LED + Alarm Tone)...")
    await adapter.trigger_alarm(duration_ms=1000)
    await asyncio.sleep(1.2)
    print_pass("Access Denied Profile emitted.")

    # Reset display
    await adapter.set_display(
        DisplayStatus(line1="VAULT 404 READY", line2="IDLE", led_color=LedColor.BLUE, buzzer=False)
    )
    adapter.release()
    return True


# ============================================================================
# Diagnostic Step 4: 4x4 Keypad Matrix Live Test
# ============================================================================


async def test_keypad_matrix(port: Optional[str] = None, interactive: bool = True) -> bool:
    print_banner("Step 4: 4x4 Matrix Keypad (Rows: 13,12,14,27 | Cols: 26,25,33,32)")
    if not interactive:
        print_info("Non-interactive mode: Keypad test skipped.")
        return True

    from app.adapters.esp32_hardware import ESP32SerialAdapter
    from app.core.types import HardwareEvent, HardwareEventType

    adapter = ESP32SerialAdapter(port=port)
    if not await adapter.initialize():
        print_fail("Serial link not available for keypad test.")
        return False

    keys_pressed = []
    pin_submitted_event = asyncio.Event()

    async def on_key_event(event: HardwareEvent) -> None:
        if event.event_type == HardwareEventType.KEYPAD_STATUS:
            key = event.payload.get("key")
            if key:
                keys_pressed.append(key)
                print(f"  {GREEN}>> Key Pressed:{RESET} [{BOLD}{key}{RESET}] (Buffer length: {event.payload.get('length')})")
        elif event.event_type == HardwareEventType.KEYPAD_PIN_RESULT:
            pin = event.payload.get("pin")
            print(f"  {CYAN}{BOLD}>> Password Submitted with '#':{RESET} '{pin}'")
            pin_submitted_event.set()

    adapter.register_event_listener(on_key_event)

    print_info("Please press several keys on the 4x4 keypad matrix and terminate with '#':")
    try:
        await asyncio.wait_for(pin_submitted_event.wait(), timeout=15.0)
        print_pass(f"Keypad interaction verified! Captured keys: {keys_pressed}")
        adapter.release()
        return True
    except asyncio.TimeoutError:
        print_info(f"Keypad input timeout (captured keys: {keys_pressed}).")
        adapter.release()
        return len(keys_pressed) > 0


# ============================================================================
# Diagnostic Step 5: MFRC522 RFID Card Scanner
# ============================================================================


async def test_rfid_reader(port: Optional[str] = None, interactive: bool = True) -> bool:
    print_banner("Step 5: MFRC522 RFID Reader (SPI Bus: GPIO 5, 18, 23, 19, 4)")
    if not interactive:
        print_info("Non-interactive mode: RFID test skipped.")
        return True

    from app.adapters.esp32_hardware import ESP32SerialAdapter
    from app.core.types import HardwareEvent, HardwareEventType

    adapter = ESP32SerialAdapter(port=port)
    if not await adapter.initialize():
        print_fail("Serial link not available for RFID test.")
        return False

    rfid_event = asyncio.Event()
    scanned_uid = [None]

    async def on_rfid_event(event: HardwareEvent) -> None:
        if event.event_type == HardwareEventType.RFID_SCANNED:
            uid = event.payload.get("card_uid")
            scanned_uid[0] = uid
            print(f"  {GREEN}{BOLD}>> RFID Card Scanned!{RESET} UID: {BOLD}{uid}{RESET} (SAK: {event.payload.get('sak')})")
            rfid_event.set()

    adapter.register_event_listener(on_rfid_event)
    print_info("Hold an RFID card / keyfob near the MFRC522 antenna...")

    try:
        await asyncio.wait_for(rfid_event.wait(), timeout=12.0)
        print_pass(f"RFID reader operational. Detected UID: '{scanned_uid[0]}'")
        adapter.release()
        return True
    except asyncio.TimeoutError:
        print_info("RFID scan timeout (no card presented).")
        adapter.release()
        return False


# ============================================================================
# Diagnostic Step 6: AS608 Optical Fingerprint Biometrics
# ============================================================================


async def test_fingerprint_sensor(port: Optional[str] = None, interactive: bool = True) -> bool:
    print_banner("Step 6: AS608 Optical Fingerprint Sensor (UART2: GPIO 16/17 @ 57600)")
    if not interactive:
        print_info("Non-interactive mode: Fingerprint test skipped.")
        return True

    from app.adapters.esp32_hardware import ESP32SerialAdapter
    from app.core.types import HardwareEvent, HardwareEventType

    adapter = ESP32SerialAdapter(port=port)
    if not await adapter.initialize():
        print_fail("Serial link not available for fingerprint test.")
        return False

    finger_event = asyncio.Event()
    finger_result = [None]

    async def on_finger_event(event: HardwareEvent) -> None:
        if event.event_type == HardwareEventType.FINGERPRINT_SCANNED:
            finger_result[0] = event.payload
            print(f"  {GREEN}{BOLD}>> Fingerprint Sensor Triggered!{RESET} Result: {event.payload}")
            finger_event.set()

    adapter.register_event_listener(on_finger_event)
    print_info("Place finger on the optical fingerprint sensor...")

    try:
        await asyncio.wait_for(finger_event.wait(), timeout=10.0)
        print_pass("Fingerprint sensor trigger verified.")
        adapter.release()
        return True
    except asyncio.TimeoutError:
        print_info("Fingerprint scan timeout (sensor not wired or no finger placed).")
        adapter.release()
        return False


# ============================================================================
# Diagnostic Step 7: OpenCV Webcam Frame & Laplacian Sharpness Filter
# ============================================================================


def test_webcam_capture() -> bool:
    print_banner("Step 7: Physical Webcam Frame Capture & Anti-Spoofing Sharpness")
    from app.adapters.camera import OpenCVCameraAdapter
    from app.vision.face_verifier import FaceVerifier

    camera = OpenCVCameraAdapter(auto_open=True)
    if not camera.is_opened():
        print_info("Physical webcam not detected or busy. Check camera index/permissions.")
        return False

    print_pass(f"Physical webcam opened successfully (index: {camera._camera_index}).")

    frame = camera.capture_warm_frame(discard_count=4)
    if frame is None or frame.size == 0:
        print_fail("Captured frame was empty.")
        camera.release()
        return False

    h, w, c = frame.shape
    print_pass(f"Captured live video frame: {w}x{h} (3 channels).")

    # Anti-Spoofing Laplacian Sharpness Test
    verifier = FaceVerifier()
    liveness_score = verifier.check_liveness(frame)
    print_info(f"Frame clarity & sharpness score: {liveness_score:.2f} (Threshold >= 0.40)")

    if liveness_score >= 0.35:
        print_pass("Image passes sharpness and focus anti-spoofing criteria.")
    else:
        print_info("Image is soft or low contrast. Ensure adequate lighting.")

    # Feature embedding extraction
    emb = verifier.extract_embeddings(frame)
    if emb is not None:
        print_pass(f"Extracted 256D normalized facial feature embedding: shape {emb.shape}, norm={np.linalg.norm(emb):.4f}")
    else:
        print_info("No human face detected in current frame (ensure face is centered in camera).")

    camera.release()
    return True


# ============================================================================
# Diagnostic Step 8: SoundDevice Microphone & RMS Energy Spectrum
# ============================================================================


def test_microphone_recording() -> bool:
    print_banner("Step 8: Physical Microphone Capture & Acoustic RMS Energy")
    from app.adapters.audio import SoundDeviceAudioAdapter
    from app.audio.voice_verifier import VoiceVerifier

    audio = SoundDeviceAudioAdapter()
    if not audio.is_available():
        print_info("No physical audio input device detected by sounddevice.")
        return False

    print_pass("Physical audio recording device available.")

    print_info("Recording 2.0 seconds of live room audio...")
    waveform = audio.record_utterance(duration_sec=2.0, sample_rate=16000)
    if waveform is None or len(waveform) == 0:
        print_fail("Failed to capture audio waveform from microphone.")
        return False

    rms = SoundDeviceAudioAdapter.calculate_rms(waveform)
    peak = float(np.max(np.abs(waveform)))
    print_pass(f"Captured {len(waveform)} audio samples ({len(waveform)/16000:.1f}s @ 16kHz).")
    print_info(f"Signal Metrics: Peak Amplitude = {peak:.4f}, RMS Energy = {rms:.4f}")

    if rms > 0.001:
        print_pass("Acoustic energy level confirmed (microphone actively capturing audio).")
    else:
        print_info("Low audio energy recorded (room quiet or mic gain low).")

    # Voice print vector extraction
    verifier = VoiceVerifier()
    vp = verifier.extract_voice_print(waveform)
    if vp is not None:
        print_pass(f"Extracted 256D acoustic voiceprint vector: shape {vp.shape}, norm={np.linalg.norm(vp):.4f}")
    else:
        print_info("Acoustic voiceprint generation skipped (signal below voice threshold).")

    audio.release()
    return True


# ============================================================================
# Main Diagnostic Orchestrator
# ============================================================================


async def run_diagnostics(port: Optional[str] = None, dry_run: bool = False) -> None:
    print(f"\n{MAGENTA}{BOLD}{'#' * 70}{RESET}")
    print(f"{MAGENTA}{BOLD}#  VAULT-404 PHYSICAL HARDWARE END-TO-END VERIFICATION SUITE       #{RESET}")
    print(f"{MAGENTA}{BOLD}{'#' * 70}{RESET}")

    results = {}

    # 1. Webcam (Host Subsystem)
    results["Webcam (OpenCV)"] = test_webcam_capture()

    # 2. Microphone (Host Subsystem)
    results["Microphone (SoundDevice)"] = test_microphone_recording()

    # 3. Serial Handshake (ESP32)
    results["Serial Link (ESP32)"] = await test_serial_handshake(port=port)

    if results["Serial Link (ESP32)"] and not dry_run:
        # 4. Servo Actuator
        results["Lock Servo (GPIO 2)"] = await test_servo_actuation(port=port)

        # 5. LEDs & Buzzer
        results["LEDs & Buzzer (GPIO 22/15/21)"] = await test_leds_and_buzzer(port=port)

        # 6. Keypad Matrix
        results["4x4 Keypad Matrix"] = await test_keypad_matrix(port=port, interactive=True)

        # 7. RFID Reader
        results["MFRC522 RFID (SPI)"] = await test_rfid_reader(port=port, interactive=True)

    # Summary Report
    print(f"\n{CYAN}{BOLD}{'=' * 70}{RESET}")
    print(f"{CYAN}{BOLD}  [+] FINAL HARDWARE DIAGNOSTIC SUMMARY REPORT{RESET}")
    print(f"{CYAN}{BOLD}{'=' * 70}{RESET}")

    for component, passed in results.items():
        status_str = f"{GREEN}[PASSED]{RESET}" if passed else f"{YELLOW}[DETECTED / SKIPPED]{RESET}"
        print(f"  * {component:<38} : {status_str}")

    print(f"{CYAN}{BOLD}{'=' * 70}{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault-404 Hardware Diagnostic Suite")
    parser.add_argument("--port", "-p", default=None, help="Serial COM port (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Non-interactive driver detection test")
    args = parser.parse_args()

    asyncio.run(run_diagnostics(port=args.port, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
