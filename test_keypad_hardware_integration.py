"""Verification suite for Keypad Lock Hardware & Software Serial Integration."""

import asyncio
import json
import os
import pytest

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import HardwareEvent, HardwareEventType, LedColor, VaultState


@pytest.fixture(autouse=True)
def setup_password_env():
    """Configure test password in environment."""
    original = os.environ.get("VAULT_PASSWORD")
    os.environ["VAULT_PASSWORD"] = "MySecretVaultPassword#404"
    yield
    if original is not None:
        os.environ["VAULT_PASSWORD"] = original
    else:
        os.environ.pop("VAULT_PASSWORD", None)


@pytest.mark.asyncio
async def test_esp32_serial_telemetry_parser():
    """Verify ESP32SerialAdapter correctly parses keypad, fingerprint, and lock telemetry JSON lines."""
    adapter = ESP32SerialAdapter(port="COM_MOCK")
    events_received = []

    async def listener(event: HardwareEvent):
        events_received.append(event)

    adapter.register_event_listener(listener)

    # 1. Simulate incoming KEYPAD_KEY_PRESSED
    adapter._process_incoming_json(
        json.dumps({"event": "KEYPAD_KEY_PRESSED", "payload": {"key": "1", "length": 1}})
    )
    await asyncio.sleep(0.02)
    assert len(events_received) == 1
    assert events_received[0].event_type == HardwareEventType.KEYPAD_STATUS

    # 2. Simulate incoming KEYPAD_PIN_SUBMITTED
    adapter._process_incoming_json(
        json.dumps({"event": "KEYPAD_PIN_SUBMITTED", "payload": {"pin": "MySecretVaultPassword#404"}})
    )
    await asyncio.sleep(0.02)
    assert len(events_received) == 2
    assert events_received[1].event_type == HardwareEventType.KEYPAD_PIN_RESULT
    assert events_received[1].payload["pin"] == "MySecretVaultPassword#404"

    # 3. Simulate incoming LOCK_STATUS_REPORT
    adapter._process_incoming_json(
        json.dumps({"event": "LOCK_STATUS_REPORT", "payload": {"locked": False, "state": "UNLOCKED"}})
    )
    await asyncio.sleep(0.02)
    assert not adapter.is_locked
    assert len(events_received) == 3
    assert events_received[2].event_type == HardwareEventType.LOCK_STATUS_CHANGED


@pytest.mark.asyncio
async def test_engine_sequential_keypad_unlock():
    """Verify Engine validates password submitted via keypad in Stage 3 and advances to Stage 4."""
    adapter = ESP32SerialAdapter(port="COM_MOCK")
    engine = VaultAuthEngine(hardware=adapter)
    engine._state = VaultState.AWAITING_KEYPAD_PIN

    # Submit correct password via serial telemetry during Stage 3
    adapter._process_incoming_json(
        json.dumps({"event": "KEYPAD_PIN_SUBMITTED", "payload": {"pin": "MySecretVaultPassword#404"}})
    )
    await asyncio.sleep(0.05)
    assert engine.state == VaultState.AWAITING_VOICE
    await engine.shutdown()
