"""Automated integration test suite for Step 10 of The Inconvenient Vault.

Validates:
1. Hardware Factory configuration and seamless switching (REAL vs SIMULATED modes).
2. ESP32 Serial protocol command serialization and newline-delimited JSON wire framing.
3. ESP32 Telemetry event parsing, error recovery on corrupted frames, and event dispatching.
4. End-to-end integration between simulated ESP32 serial events and VaultAuthEngine FSM.
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import List
import pytest

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.adapters.factory import get_hardware_adapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.core.engine import VaultAuthEngine
from app.core.types import DisplayStatus, HardwareEvent, HardwareEventType, LedColor, VaultState


# ============================================================================
# 1. Hardware Factory & Configuration Tests
# ============================================================================


def test_hardware_factory_switching():
    """Verify hardware adapter factory returns appropriate implementation based on mode."""
    # Simulated Mode
    mock_hw = get_hardware_adapter(mode="SIMULATED")
    assert isinstance(mock_hw, MockHardwareAdapter)
    assert mock_hw.is_initialized is True

    # Real Physical ESP32 Serial Mode
    real_hw = get_hardware_adapter(mode="REAL", port="COM42", baudrate=115200)
    assert isinstance(real_hw, ESP32SerialAdapter)
    assert real_hw.port == "COM42"
    assert real_hw.is_initialized is False


# ============================================================================
# 2. ESP32 Serial Protocol Framing & Command Serialization Tests
# ============================================================================


@pytest.mark.asyncio
async def test_esp32_serial_command_serialization():
    """Verify ESP32SerialAdapter correctly formats and transmits Host-to-ESP32 commands."""
    adapter = ESP32SerialAdapter(port="VIRTUAL_TEST_PORT")

    # Mock writer stream to capture transmitted bytes
    sent_bytes_list: List[bytes] = []

    class MockStreamWriter:
        def write(self, data: bytes):
            sent_bytes_list.append(data)

        async def drain(self):
            pass

        def close(self):
            pass

    adapter._is_initialized = True
    adapter._writer = MockStreamWriter()

    # 1. SET_DISPLAY
    display = DisplayStatus(
        line1="VAULT 404", line2="SCAN CARD", led_color=LedColor.CYAN, buzzer=True, duration_ms=500
    )
    assert await adapter.set_display(display) is True
    assert len(sent_bytes_list) == 1

    cmd1 = json.loads(sent_bytes_list[0].decode("utf-8").strip())
    assert cmd1["cmd"] == "SET_DISPLAY"
    assert cmd1["line1"] == "VAULT 404"
    assert cmd1["line2"] == "SCAN CARD"
    assert cmd1["led"] == "CYAN"
    assert cmd1["buzzer"] is True

    # 2. SET_LOCK (UNLOCKED)
    assert await adapter.set_lock(False) is True
    assert len(sent_bytes_list) == 2

    cmd2 = json.loads(sent_bytes_list[1].decode("utf-8").strip())
    assert cmd2["cmd"] == "SET_LOCK"
    assert cmd2["state"] == "UNLOCKED"

    # 3. TRIGGER_ALARM
    await adapter.trigger_alarm(3000)
    assert len(sent_bytes_list) == 3

    cmd3 = json.loads(sent_bytes_list[2].decode("utf-8").strip())
    assert cmd3["cmd"] == "TRIGGER_ALARM"
    assert cmd3["duration_ms"] == 3000


# ============================================================================
# 3. Telemetry Event Decoding & Error Recovery Tests
# ============================================================================


@pytest.mark.asyncio
async def test_esp32_telemetry_event_decoding_and_fault_tolerance():
    """Verify incoming serial JSON telemetry lines are decoded and dispatched, with corrupt frame tolerance."""
    adapter = ESP32SerialAdapter(port="VIRTUAL_TEST_PORT")
    dispatched_events: List[HardwareEvent] = []

    async def event_handler(event: HardwareEvent):
        dispatched_events.append(event)

    adapter.register_event_listener(event_handler)

    # 1. Valid RFID Event Line
    adapter._process_incoming_json(
        json.dumps({"event": "RFID_SCANNED", "payload": {"card_uid": "E2806894"}})
    )
    await asyncio.sleep(0.05)

    assert len(dispatched_events) == 1
    assert dispatched_events[0].event_type == HardwareEventType.RFID_SCANNED
    assert dispatched_events[0].payload["card_uid"] == "E2806894"

    # 2. Valid Fingerprint Matched Event
    adapter._process_incoming_json(
        json.dumps(
            {
                "event": "FINGERPRINT_MATCHED",
                "payload": {"finger_id": 1, "matched": True, "confidence": 0.98},
            }
        )
    )
    await asyncio.sleep(0.05)

    assert len(dispatched_events) == 2
    assert dispatched_events[1].event_type == HardwareEventType.FINGERPRINT_MATCHED
    assert dispatched_events[1].payload["finger_id"] == 1

    # 3. Valid Tamper Triggered Event
    adapter._process_incoming_json(
        json.dumps(
            {
                "event": "TAMPER_TRIGGERED",
                "payload": {"sensor": "chassis_switch", "description": "Breach detected"},
            }
        )
    )
    await asyncio.sleep(0.05)

    assert len(dispatched_events) == 3
    assert dispatched_events[2].event_type == HardwareEventType.TAMPER_TRIGGERED

    # 4. Corrupted / Malformed Framing Lines (Ensure No Crashing)
    adapter._process_incoming_json("MALFORMED_GARBAGE_LINE_WITHOUT_JSON")
    adapter._process_incoming_json("{invalid_json_fragment: 123,")
    adapter._process_incoming_json("")
    await asyncio.sleep(0.05)

    # Count of valid events should still be 3
    assert len(dispatched_events) == 3


# ============================================================================
# 4. Virtual Serial Loopback End-to-End Test with VaultAuthEngine
# ============================================================================


@pytest.mark.asyncio
async def test_virtual_serial_loopback_with_engine():
    """Verify virtual serial events drive the complete VaultAuthEngine FSM through physical abstractions."""
    adapter = ESP32SerialAdapter(port="VIRTUAL_TEST_PORT")
    engine = VaultAuthEngine(hardware=adapter)

    # Initialize Engine (Registers event listener with adapter)
    adapter._is_initialized = True
    await engine.initialize()
    assert engine.state == VaultState.IDLE

    # 1. ESP32 emits RFID_SCANNED -> Engine initiates and verifies Stage 1
    adapter._process_incoming_json(
        json.dumps({"event": "RFID_SCANNED", "payload": {"card_uid": "E2806894"}})
    )
    await asyncio.sleep(0.05)
    assert engine.state == VaultState.AWAITING_FINGERPRINT

    # 2. ESP32 emits FINGERPRINT_MATCHED -> Engine verifies Stage 2
    adapter._process_incoming_json(
        json.dumps(
            {
                "event": "FINGERPRINT_MATCHED",
                "payload": {"finger_id": 1, "matched": True, "confidence": 0.98},
            }
        )
    )
    await asyncio.sleep(0.05)
    assert engine.state == VaultState.AWAITING_FACE

    # 3. ESP32 emits TAMPER_TRIGGERED -> Engine immediately locks down to LOCKOUT
    adapter._process_incoming_json(
        json.dumps(
            {
                "event": "TAMPER_TRIGGERED",
                "payload": {"sensor": "chassis_switch", "description": "Drill detected"},
            }
        )
    )
    await asyncio.sleep(0.05)
    assert engine.state == VaultState.LOCKOUT
    assert engine.is_locked is True if hasattr(engine, "is_locked") else adapter.is_locked is True


if __name__ == "__main__":
    import sys

    print("Running Step 10 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
