"""Verification suite for Step 1 of The Inconvenient Vault.

Validates:
1. State and hardware event enum integrity and completeness.
2. Pydantic models (HardwareEvent, DisplayStatus) validation rules, constraints, and immutability.
3. Strict enforcement of the HardwareInterface Abstract Base Class contract.
"""

import asyncio
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
    VaultState,
)
from app.interfaces.hardware import HardwareEventCallback, HardwareInterface


# ============================================================================
# 1. Enum Integrity Tests
# ============================================================================


def test_vault_state_enum_members():
    """Verify all sequential authentication stages and terminal states exist in VaultState."""
    expected_states = {
        "IDLE",
        "AWAITING_RFID",
        
        "AWAITING_FACE",
        "AWAITING_KEYPAD_PIN",
        "AWAITING_VOICE",
        "UNLOCKED",
        "LOCKOUT",
        "ERROR",
    }
    actual_states = {state.value for state in VaultState}
    assert expected_states.issubset(actual_states), f"Missing states: {expected_states - actual_states}"

    # Verify string serialization
    assert str(VaultState.AWAITING_RFID) == "VaultState.AWAITING_RFID"
    assert VaultState.AWAITING_RFID.value == "AWAITING_RFID"
    assert VaultState("AWAITING_VOICE") == VaultState.AWAITING_VOICE


def test_hardware_event_type_enum_members():
    """Verify essential hardware event types exist for RFID, fingerprint, locks, and alarms."""
    required_events = {
        "RFID_SCANNED",
        "KEYPAD_STATUS",
        "KEYPAD_PIN_RESULT",
        "LOCK_STATUS_CHANGED",
        "TAMPER_TRIGGERED",
        "ALARM_TRIGGERED",
        "HARDWARE_ERROR",
    }
    actual_events = {event.value for event in HardwareEventType}
    assert required_events.issubset(actual_events), f"Missing event types: {required_events - actual_events}"


def test_led_color_enum_members():
    """Verify common LED colors are defined."""
    assert LedColor.RED.value == "RED"
    assert LedColor.GREEN.value == "GREEN"
    assert LedColor.BLUE.value == "BLUE"
    assert LedColor.OFF.value == "OFF"


# ============================================================================
# 2. Pydantic Model Validation Tests
# ============================================================================


def test_hardware_event_creation_and_defaults():
    """Test HardwareEvent initialization with default timestamp and payload."""
    before_ts = datetime.now(timezone.utc)
    event = HardwareEvent(
        event_type=HardwareEventType.RFID_SCANNED,
        payload={"card_uid": "E2806894"},
    )
    after_ts = datetime.now(timezone.utc)

    assert event.event_type == HardwareEventType.RFID_SCANNED
    assert event.payload["card_uid"] == "E2806894"
    assert event.source_id is None
    assert before_ts <= event.timestamp <= after_ts
    assert event.timestamp.tzinfo == timezone.utc


def test_hardware_event_immutability():
    """Ensure HardwareEvent is frozen and immutable after creation."""
    event = HardwareEvent(
        event_type=HardwareEventType.BUTTON_PRESSED,
        payload={"button": "ENTER"},
    )
    with pytest.raises(ValidationError):
        event.event_type = HardwareEventType.HARDWARE_ERROR  # type: ignore


def test_hardware_event_extra_fields_forbidden():
    """Ensure unexpected fields are rejected."""
    with pytest.raises(ValidationError):
        HardwareEvent(
            event_type=HardwareEventType.ALARM_TRIGGERED,
            unauthorized_field="malicious_data",  # type: ignore
        )


def test_display_status_validation():
    """Test DisplayStatus construction, validation, and auto-parsing."""
    status = DisplayStatus(
        line1="SCAN RFID TAG",
        line2="READY",
        led_color=LedColor.BLUE,
        buzzer=False,
        duration_ms=2000,
    )
    assert status.line1 == "SCAN RFID TAG"
    assert status.line2 == "READY"
    assert status.led_color == LedColor.BLUE
    assert status.buzzer is False
    assert status.duration_ms == 2000


def test_display_status_led_color_parsing():
    """Verify string inputs to led_color are automatically parsed into LedColor enums."""
    status = DisplayStatus(line1="TEST", led_color="green")  # type: ignore
    assert status.led_color == LedColor.GREEN

    with pytest.raises(ValidationError):
        DisplayStatus(line1="TEST", led_color="ULTRAVIOLET")  # type: ignore


def test_display_status_constraints():
    """Verify field constraints such as max_length and non-negative duration."""
    # Negative duration must fail
    with pytest.raises(ValidationError):
        DisplayStatus(line1="OK", duration_ms=-100)

    # Line exceeding max length must fail
    with pytest.raises(ValidationError):
        DisplayStatus(line1="THIS LINE IS EXTREMELY LONG AND EXCEEDS THE TWENTY CHAR LIMIT")


# ============================================================================
# 3. HardwareInterface Abstract Base Class Tests
# ============================================================================


def test_hardware_interface_cannot_be_instantiated_directly():
    """Verify HardwareInterface is an abstract base class that cannot be instantiated."""
    with pytest.raises(TypeError) as exc_info:
        HardwareInterface()  # type: ignore
    assert "Can't instantiate abstract class" in str(exc_info.value)


def test_incomplete_hardware_interface_subclass_fails():
    """Verify a subclass missing any abstract method cannot be instantiated."""

    class IncompleteHardware(HardwareInterface):
        async def initialize(self) -> bool:
            return True

        # Missing shutdown, register_event_listener, set_display, set_lock, trigger_alarm

    with pytest.raises(TypeError) as exc_info:
        IncompleteHardware()  # type: ignore
    assert "Can't instantiate abstract class" in str(exc_info.value)


class MockHardware(HardwareInterface):
    """Complete, fully-compliant mock implementation of HardwareInterface for testing."""

    def __init__(self) -> None:
        self.is_initialized = False
        self.is_locked = True
        self.last_display: DisplayStatus | None = None
        self.alarm_duration_ms: int = 0
        self.listeners: list[HardwareEventCallback] = []
        self.dispatched_events: list[HardwareEvent] = []

    async def initialize(self) -> bool:
        self.is_initialized = True
        return True

    async def shutdown(self) -> None:
        self.is_initialized = False

    def register_event_listener(self, callback: HardwareEventCallback) -> None:
        self.listeners.append(callback)

    async def set_display(self, status: DisplayStatus) -> None:
        self.last_display = status

    async def set_lock(self, locked: bool) -> bool:
        self.is_locked = locked
        return True

    async def trigger_alarm(self, duration_ms: int) -> None:
        self.alarm_duration_ms = duration_ms

    async def simulate_incoming_event(self, event: HardwareEvent) -> None:
        """Helper to dispatch events to registered listeners."""
        self.dispatched_events.append(event)
        for listener in self.listeners:
            await listener(event)


@pytest.mark.asyncio
async def test_mock_hardware_interface_contract_fulfillment():
    """Verify complete implementation fulfills all async hardware interface contracts."""
    hw = MockHardware()

    # 1. Initialize
    init_success = await hw.initialize()
    assert init_success is True
    assert hw.is_initialized is True

    # 2. Event listener registration and asynchronous event propagation
    received_events: list[HardwareEvent] = []

    async def event_handler(event: HardwareEvent) -> None:
        received_events.append(event)

    hw.register_event_listener(event_handler)

    test_event = HardwareEvent(
        event_type=HardwareEventType.RFID_SCANNED,
        payload={"uid": "A1B2C3D4"},
        source_id="RC522_READER",
    )
    await hw.simulate_incoming_event(test_event)

    assert len(received_events) == 1
    assert received_events[0].event_type == HardwareEventType.RFID_SCANNED
    assert received_events[0].payload["uid"] == "A1B2C3D4"
    assert received_events[0].source_id == "RC522_READER"

    # 3. Set display
    disp = DisplayStatus(
        line1="RFID ACCEPTED",
        line2="PLACE FINGERPRINT",
        led_color=LedColor.GREEN,
        buzzer=True,
        duration_ms=1000,
    )
    await hw.set_display(disp)
    assert hw.last_display == disp

    # 4. Lock mechanism
    lock_result = await hw.set_lock(False)
    assert lock_result is True
    assert hw.is_locked is False

    # 5. Alarm trigger
    await hw.trigger_alarm(5000)
    assert hw.alarm_duration_ms == 5000

    # 6. Shutdown
    await hw.shutdown()
    assert hw.is_initialized is False


if __name__ == "__main__":
    import sys

    print("Running Step 1 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
