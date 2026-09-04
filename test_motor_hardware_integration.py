"""Integration and unit tests for 4-Motor Getaway Subsystem."""

import asyncio
from datetime import datetime, timezone
import pytest
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
    VaultState,
)
from app.interfaces.hardware import HardwareEventCallback, HardwareInterface


class MockMotorHardwareAdapter(HardwareInterface):
    """Mock Hardware Adapter capturing motor commands and state transitions."""

    def __init__(self) -> None:
        self.is_initialized = True
        self.is_locked = True
        self.is_alarm_active = False
        self.current_display: DisplayStatus = DisplayStatus()
        self.listeners: list[HardwareEventCallback] = []
        self.motor_commands: list[dict] = []
        self.current_motor_state: str = "STOPPED"

    async def initialize(self) -> bool:
        self.is_initialized = True
        return True

    async def shutdown(self) -> None:
        self.is_initialized = False

    def register_event_listener(self, callback: HardwareEventCallback) -> None:
        if callback not in self.listeners:
            self.listeners.append(callback)

    async def set_display(self, status: DisplayStatus) -> None:
        self.current_display = status

    async def set_lock(self, locked: bool) -> bool:
        self.is_locked = locked
        return True

    async def trigger_alarm(self, duration_ms: int) -> None:
        self.is_alarm_active = duration_ms > 0

    async def drive_motors(
        self, direction: str = "FORWARD", duration_ms: int = 3000, speed: int = 255
    ) -> bool:
        self.current_motor_state = f"DRIVING_{direction}"
        cmd = {
            "cmd": "DRIVE_MOTORS",
            "direction": direction,
            "duration_ms": duration_ms,
            "speed": speed,
        }
        self.motor_commands.append(cmd)
        return True

    async def stop_motors(self) -> bool:
        self.current_motor_state = "STOPPED"
        cmd = {"cmd": "STOP_MOTORS"}
        self.motor_commands.append(cmd)
        return True


@pytest.mark.asyncio
async def test_motor_driver_direct_actuation() -> None:
    """Verify drive_motors and stop_motors record proper parameters."""
    adapter = MockMotorHardwareAdapter()
    await adapter.initialize()

    # Drive forward
    res1 = await adapter.drive_motors("FORWARD", duration_ms=4000, speed=200)
    assert res1 is True
    assert adapter.current_motor_state == "DRIVING_FORWARD"
    assert len(adapter.motor_commands) == 1
    assert adapter.motor_commands[-1]["direction"] == "FORWARD"
    assert adapter.motor_commands[-1]["duration_ms"] == 4000
    assert adapter.motor_commands[-1]["speed"] == 200

    # Stop motors
    res2 = await adapter.stop_motors()
    assert res2 is True
    assert adapter.current_motor_state == "STOPPED"
    assert len(adapter.motor_commands) == 2
    assert adapter.motor_commands[-1]["cmd"] == "STOP_MOTORS"


@pytest.mark.asyncio
async def test_vault_unlock_triggers_motor_getaway() -> None:
    """Verify transitioning to UNLOCKED automatically triggers 4-motor getaway."""
    hardware = MockMotorHardwareAdapter()
    config = EngineConfig(
        valid_rfid_uids=["TAG12345"],
        valid_face_ids=["FACE_001"],
        valid_passwords=["123456"],
        valid_voice_phrases=["OPEN SESAME OVERENGINEERED"],
        auto_relock_delay_seconds=5.0,
    )
    engine = VaultAuthEngine(hardware=hardware, config=config)
    await engine.initialize()

    # Complete 4-factor sequence
    assert await engine.start_authentication() is True
    assert engine.state == VaultState.AWAITING_RFID

    # Stage 1: RFID
    assert await engine.submit_rfid("TAG12345") is True
    assert engine.state == VaultState.AWAITING_FACE

    # Stage 2: Face
    assert await engine.submit_face("FACE_001", confidence=0.98) is True
    assert engine.state == VaultState.AWAITING_KEYPAD_PIN

    # Stage 3: PIN
    assert await engine.submit_keypad_pin(pin="123456") is True
    assert engine.state == VaultState.AWAITING_VOICE

    # Stage 4: Voice -> UNLOCKED
    assert await engine.submit_voice("OPEN SESAME OVERENGINEERED", confidence=0.95) is True
    assert engine.state == VaultState.UNLOCKED

    # Check that getaway motor drive was commanded
    assert hardware.is_locked is False
    assert any(
        cmd.get("cmd") == "DRIVE_MOTORS" and cmd.get("direction") == "FORWARD"
        for cmd in hardware.motor_commands
    )
    assert "GETAWAY ACTIVE" in hardware.current_display.line2


@pytest.mark.asyncio
async def test_lockout_and_idle_halt_motors() -> None:
    """Verify reset to IDLE and trigger tamper lockout immediately stop getaway motors."""
    hardware = MockMotorHardwareAdapter()
    engine = VaultAuthEngine(hardware=hardware)
    await engine.initialize()

    # Simulate driving motors
    await hardware.drive_motors("FORWARD", 5000)
    assert hardware.current_motor_state == "DRIVING_FORWARD"

    # Reset to IDLE halts motors
    await engine.reset_to_idle()
    assert hardware.current_motor_state == "STOPPED"
    assert hardware.motor_commands[-1]["cmd"] == "STOP_MOTORS"

    # Trigger tamper lockout halts motors
    await hardware.drive_motors("BACKWARD", 2000)
    assert hardware.current_motor_state == "DRIVING_BACKWARD"

    await engine.trigger_tamper_lockout("Chassis opened during getaway")
    assert engine.state == VaultState.LOCKOUT
    assert hardware.current_motor_state == "STOPPED"
    assert hardware.motor_commands[-1]["cmd"] == "STOP_MOTORS"
