"""Automated test suite for Step 2 of The Inconvenient Vault.

Validates:
1. MockHardwareAdapter initialization, lifecycle, and safety guards.
2. Event listener registration, unregistration, and exception isolation.
3. Peripheral simulation methods (RFID, Fingerprint, Tamper, Door, Error).
4. Solenoid lock state transitions and event broadcasting.
5. Display updates and alarm actuation.
6. High-concurrency event dispatching under load.
"""

import asyncio
from typing import List
import pytest

from app.adapters.mock_hardware import MockHardwareAdapter
from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
)
from app.interfaces.hardware import HardwareInterface


def test_mock_hardware_implements_interface():
    """Verify MockHardwareAdapter implements HardwareInterface ABC."""
    adapter = MockHardwareAdapter()
    assert isinstance(adapter, HardwareInterface)


@pytest.mark.asyncio
async def test_mock_hardware_lifecycle_and_uninitialized_guards():
    """Verify operations prior to initialize() raise RuntimeError and shutdown resets state."""
    adapter = MockHardwareAdapter(auto_initialize=False)
    assert adapter.is_initialized is False

    # Attempting operations when offline must raise RuntimeError
    with pytest.raises(RuntimeError, match="not initialized"):
        await adapter.set_display(DisplayStatus(line1="FAIL"))

    with pytest.raises(RuntimeError, match="not initialized"):
        await adapter.set_lock(False)

    with pytest.raises(RuntimeError, match="not initialized"):
        await adapter.trigger_alarm(1000)

    # Initialize
    success = await adapter.initialize()
    assert success is True
    assert adapter.is_initialized is True
    assert adapter.is_locked is True
    assert adapter.current_display.line1 == "VAULT 404 READY"
    assert adapter.current_display.led_color == LedColor.BLUE

    # Shutdown
    await adapter.shutdown()
    assert adapter.is_initialized is False
    assert adapter.current_display.led_color == LedColor.OFF


@pytest.mark.asyncio
async def test_event_listener_registration_and_unregistration():
    """Verify event listeners can be registered, invoked, and unregistered."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    events: List[HardwareEvent] = []

    async def listener(event: HardwareEvent) -> None:
        events.append(event)

    adapter.register_event_listener(listener)
    assert adapter.listener_count == 1

    # Emit an event
    await adapter.simulate_rfid_scan("A1B2C3D4")
    assert len(events) == 1
    assert events[0].payload["card_uid"] == "A1B2C3D4"

    # Unregister listener
    removed = adapter.unregister_event_listener(listener)
    assert removed is True
    assert adapter.listener_count == 0

    # Emit another event; listener should not receive it
    await adapter.simulate_rfid_scan("DEADBEEF")
    assert len(events) == 1  # Unchanged

    # Unregistering non-existent listener returns False
    assert adapter.unregister_event_listener(listener) is False


@pytest.mark.asyncio
async def test_event_dispatch_exception_isolation():
    """Verify that an exception in one listener does not crash other listeners or the emitter."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    received_healthy: List[HardwareEvent] = []

    async def healthy_listener(event: HardwareEvent) -> None:
        received_healthy.append(event)

    async def faulty_listener(event: HardwareEvent) -> None:
        raise ValueError("Simulated unexpected listener crash!")

    adapter.register_event_listener(faulty_listener)
    adapter.register_event_listener(healthy_listener)

    # Dispatched event should still reach healthy_listener without raising an uncaught exception
    event = await adapter.simulate_tamper()
    assert event.event_type == HardwareEventType.TAMPER_TRIGGERED
    assert len(received_healthy) == 1
    assert received_healthy[0].event_type == HardwareEventType.TAMPER_TRIGGERED


@pytest.mark.asyncio
async def test_simulate_rfid_scan():
    """Verify RFID simulation normalizes hex UID and supports metadata."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    event = await adapter.simulate_rfid_scan("e2806894", metadata={"protocol": "MIFARE_CLASSIC_1K"})

    assert event.event_type == HardwareEventType.RFID_SCANNED
    assert event.payload["card_uid"] == "E2806894"
    assert event.payload["protocol"] == "MIFARE_CLASSIC_1K"
    assert event.source_id == "MOCK_RC522_RFID"
    assert event in adapter.event_history


@pytest.mark.asyncio
async def test_simulate_keypad_pin_result():
    """Verify keypad pin result events."""
    adapter = MockHardwareAdapter(auto_initialize=True)

    ev = await adapter.simulate_keypad_pin_result("123456")
    assert ev.event_type == HardwareEventType.KEYPAD_PIN_RESULT
    assert ev.payload["result"] == "123456"


@pytest.mark.asyncio
async def test_simulate_door_sensor():
    """Verify door sensor toggle state and events."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    assert adapter.is_door_open is False

    open_ev = await adapter.simulate_door_sensor(True)
    assert adapter.is_door_open is True
    assert open_ev.event_type == HardwareEventType.DOOR_OPENED

    close_ev = await adapter.simulate_door_sensor(False)
    assert adapter.is_door_open is False
    assert close_ev.event_type == HardwareEventType.DOOR_CLOSED


@pytest.mark.asyncio
async def test_simulate_hardware_error():
    """Verify hardware error emission."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    err_ev = await adapter.simulate_hardware_error("ERR_I2C_NACK", "OLED display I2C bus NACK")

    assert err_ev.event_type == HardwareEventType.HARDWARE_ERROR
    assert err_ev.payload["error_code"] == "ERR_I2C_NACK"
    assert "OLED display" in err_ev.payload["details"]


@pytest.mark.asyncio
async def test_lock_actuation_and_event_broadcasting():
    """Verify set_lock updates state and dispatches LOCK_STATUS_CHANGED event."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    events: List[HardwareEvent] = []

    async def listener(event: HardwareEvent) -> None:
        events.append(event)

    adapter.register_event_listener(listener)

    # Unlock
    res = await adapter.set_lock(False)
    assert res is True
    assert adapter.is_locked is False

    # Lock again
    res = await adapter.set_lock(True)
    assert res is True
    assert adapter.is_locked is True

    # Confirm 2 lock change events were broadcast
    lock_events = [e for e in events if e.event_type == HardwareEventType.LOCK_STATUS_CHANGED]
    assert len(lock_events) == 2
    assert lock_events[0].payload["locked"] is False
    assert lock_events[1].payload["locked"] is True


@pytest.mark.asyncio
async def test_display_and_alarm_actuation():
    """Verify display updates and alarm siren actuation."""
    adapter = MockHardwareAdapter(auto_initialize=True)

    status = DisplayStatus(
        line1="PASSWORD REQUIRED",
        line2="ATTEMPT 1/3",
        led_color=LedColor.YELLOW,
        buzzer=True,
        duration_ms=1500,
    )
    await adapter.set_display(status)
    assert adapter.current_display == status

    # Alarm
    await adapter.trigger_alarm(4500)
    assert adapter.is_alarm_active is True
    assert adapter.alarm_duration_ms == 4500
    assert any(e.event_type == HardwareEventType.ALARM_TRIGGERED for e in adapter.event_history)


@pytest.mark.asyncio
async def test_concurrent_event_simulation_load():
    """Verify high-concurrency event generation and subscriber delivery."""
    adapter = MockHardwareAdapter(auto_initialize=True)
    received: List[HardwareEvent] = []

    async def collector(event: HardwareEvent) -> None:
        received.append(event)

    adapter.register_event_listener(collector)

    # Fire 50 concurrent simulation tasks
    tasks = [
        adapter.simulate_rfid_scan(f"CARD_{i:04d}")
        for i in range(50)
    ]
    dispatched = await asyncio.gather(*tasks)

    assert len(dispatched) == 50
    assert len(received) == 50
    assert len(adapter.event_history) == 50


if __name__ == "__main__":
    import sys

    print("Running Step 2 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
