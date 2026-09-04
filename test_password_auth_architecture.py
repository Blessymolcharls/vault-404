"""Comprehensive Verification Suite for Centralized Password Authentication Architecture.

Validates:
1. Centralized verify_password logic with Argon2id cryptographic hashing.
2. Handling of correct, incorrect, empty, and missing VAULT_PASSWORD configurations.
3. Production ESP32SerialAdapter JSON telemetry parsing (KEYPAD_PIN_SUBMITTED, RFID_SCANNED, FINGERPRINT_CAPTURED, etc.).
4. VaultAuthEngine state transitions and direct hardware keypad PIN unlocking.
"""

import asyncio
import json
import os
import pytest
from argon2 import PasswordHasher

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.core.auth import (
    get_configured_password,
    get_configured_password_hash,
    verify_password,
)
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import DisplayStatus, HardwareEvent, HardwareEventType, LedColor, VaultState


@pytest.fixture(autouse=True)
def setup_test_env():
    """Ensure a consistent test environment for password verification."""
    original_pwd = os.environ.get("VAULT_PASSWORD")
    os.environ["VAULT_PASSWORD"] = "SecureTestPassword#2026!"
    yield
    if original_pwd is not None:
        os.environ["VAULT_PASSWORD"] = original_pwd
    else:
        os.environ.pop("VAULT_PASSWORD", None)


# ============================================================================
# 1. Centralized verify_password & Argon2 Hashing Unit Tests
# ============================================================================


def test_verify_password_correct():
    """Verify correct password authenticates successfully against Argon2 hash."""
    assert verify_password("SecureTestPassword#2026!") is True


def test_verify_password_incorrect():
    """Verify incorrect password is rejected."""
    assert verify_password("WrongPassword123") is False


def test_verify_password_empty_and_whitespace():
    """Verify empty and whitespace candidate passwords are safely rejected."""
    assert verify_password("") is False
    assert verify_password("   ") is False
    assert verify_password(None) is False  # type: ignore


def test_verify_password_missing_vault_password(monkeypatch):
    """Verify that when VAULT_PASSWORD is not set, verification safely rejects without crashing."""
    monkeypatch.delenv("VAULT_PASSWORD", raising=False)
    assert get_configured_password() is None
    assert get_configured_password_hash() is None
    assert verify_password("AnyPassword") is False


def test_verify_password_with_custom_hash():
    """Verify candidate password validates against a specific Argon2 hash."""
    ph = PasswordHasher()
    custom_hash = ph.hash("CustomSecretPass#777")

    assert verify_password("CustomSecretPass#777", expected_hash=custom_hash) is True
    assert verify_password("WrongCustomSecret", expected_hash=custom_hash) is False


# ============================================================================
# 2. ESP32 Serial Adapter Telemetry & Event Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_esp32_serial_telemetry_keypad_pin_submitted():
    """Verify ESP32SerialAdapter parses KEYPAD_PIN_SUBMITTED wire frames."""
    adapter = ESP32SerialAdapter(port="COM_TEST")
    received_events = []

    async def listener(event: HardwareEvent):
        received_events.append(event)

    adapter.register_event_listener(listener)

    raw_frame = json.dumps({
        "event": "KEYPAD_PIN_SUBMITTED",
        "payload": {"pin": "SecureTestPassword#2026!", "length": 25},
        "timestamp_ms": 12345
    })
    adapter._process_incoming_json(raw_frame)
    await asyncio.sleep(0.02)

    assert len(received_events) == 1
    ev = received_events[0]
    assert ev.event_type == HardwareEventType.KEYPAD_PIN_RESULT
    assert ev.payload["pin"] == "SecureTestPassword#2026!"


@pytest.mark.asyncio
async def test_esp32_serial_telemetry_rfid_and_fingerprint():
    """Verify ESP32SerialAdapter parses RFID_SCANNED and FINGERPRINT_CAPTURED frames."""
    adapter = ESP32SerialAdapter(port="COM_TEST")
    received_events = []

    async def listener(event: HardwareEvent):
        received_events.append(event)

    adapter.register_event_listener(listener)

    # 1. RFID
    adapter._process_incoming_json(json.dumps({
        "event": "RFID_SCANNED",
        "payload": {"card_uid": "E2806894", "sak": 8}
    }))

    # 2. Fingerprint
    adapter._process_incoming_json(json.dumps({
        "event": "FINGERPRINT_CAPTURED",
        "payload": {"finger_id": 1, "confidence": 120, "status": "MATCHED"}
    }))

    # 3. Tamper
    adapter._process_incoming_json(json.dumps({
        "event": "TAMPER_TRIGGERED",
        "payload": {"description": "Chassis Switch Open"}
    }))

    await asyncio.sleep(0.02)
    assert len(received_events) == 3
    assert received_events[0].event_type == HardwareEventType.RFID_SCANNED
    assert received_events[0].payload["card_uid"] == "E2806894"
    assert received_events[1].event_type == HardwareEventType.FINGERPRINT_SCANNED
    assert received_events[1].payload["finger_id"] == 1
    assert received_events[2].event_type == HardwareEventType.TAMPER_TRIGGERED


@pytest.mark.asyncio
async def test_stage_denial_terminates_entire_chain():
    """Verify that if access is denied at any stage, the entire authentication chain stops and resets to IDLE."""
    adapter = ESP32SerialAdapter(port="COM_TEST")
    engine = VaultAuthEngine(hardware=adapter)

    # 1. Start chain -> AWAITING_RFID
    await engine.start_authentication()
    assert engine.state == VaultState.AWAITING_RFID

    # 2. Provide invalid RFID -> entire chain must immediately stop and reset to IDLE
    res = await engine.submit_rfid("INVALID_TAG_DENIED")
    assert res is False
    assert engine.state == VaultState.IDLE

    # 3. Start chain again and pass RFID with the authorized physical card (39D74320)
    await engine.start_authentication()
    assert engine.state == VaultState.AWAITING_RFID
    await engine.submit_rfid("39D74320")
    assert engine.state == VaultState.AWAITING_FACE

    # 4. Fail Face recognition -> entire chain must stop and reset to IDLE
    res_face = await engine.submit_face(face_id="UNKNOWN_INTRUDER", confidence=0.2, is_live=False)
    assert res_face is False
    assert engine.state == VaultState.IDLE

    # 5. Start chain, pass RFID (39D74320) & Face, then fail Password -> entire chain must stop and reset to IDLE
    await engine.start_authentication()
    await engine.submit_rfid("39D74320")
    await engine.submit_face(face_id="SUBJECT_001_OPERATOR", confidence=0.99, is_live=True)
    assert engine.state == VaultState.AWAITING_KEYPAD_PIN

    res_pin = await engine.submit_keypad_pin("WRONG_PIN_123")
    assert res_pin is False
    assert engine.state == VaultState.IDLE

    await engine.shutdown()


@pytest.mark.asyncio
async def test_rfid_mifare_1kb_uid_authentication():
    """Verify physical MIFARE 1KB card UID (39 D7 43 20) in various formats is properly accepted."""
    adapter = ESP32SerialAdapter(port="COM_TEST")
    engine = VaultAuthEngine(hardware=adapter)

    # Test spaced format: "39 D7 43 20"
    await engine.start_authentication()
    assert engine.state == VaultState.AWAITING_RFID
    res = await engine.submit_rfid("39 D7 43 20")
    assert res is True
    assert engine.state == VaultState.AWAITING_FACE

    # Reset and test lowercase unspaced format: "39d74320"
    await engine.reset_to_idle()
    await engine.start_authentication()
    res = await engine.submit_rfid("39d74320")
    assert res is True
    assert engine.state == VaultState.AWAITING_FACE

    # Reset and test colon-separated format: "39:D7:43:20"
    await engine.reset_to_idle()
    await engine.start_authentication()
    res = await engine.submit_rfid("39:D7:43:20")
    assert res is True
    assert engine.state == VaultState.AWAITING_FACE

    # Verify keyfob / unauthorized keys are rejected and reset state to IDLE
    await engine.reset_to_idle()
    await engine.start_authentication()
    res_key = await engine.submit_rfid("89E3F31F")
    assert res_key is False
    assert engine.state == VaultState.IDLE

    await engine.shutdown()
