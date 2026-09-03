"""Automated test suite for Step 3 of The Inconvenient Vault.

Validates:
1. Complete happy-path 5-stage sequential authentication to UNLOCKED.
2. Strict sequence enforcement & out-of-order rejection.
3. Hardware-driven event integration.
4. Retry failure threshold and automatic LOCKOUT.
5. Immediate tamper alert lockdown.
6. Stage timeout expiration and graceful reset.
7. Admin override passcode recovery.
8. State change subscriber broadcasting.
9. Custom validator hook injection.
"""

import asyncio
from typing import List
import pytest

from app.adapters.mock_hardware import MockHardwareAdapter
from app.core.engine import EngineConfig, StateTransitionEvent, VaultAuthEngine
from app.core.types import LedColor, VaultState


@pytest.fixture
def mock_hardware() -> MockHardwareAdapter:
    """Fixture providing an initialized mock hardware adapter."""
    return MockHardwareAdapter(auto_initialize=True)


@pytest.fixture
def engine(mock_hardware: MockHardwareAdapter) -> VaultAuthEngine:
    """Fixture providing an initialized VaultAuthEngine."""
    config = EngineConfig(
        stage_timeout_seconds=5.0,
        max_failed_attempts=3,
        auto_relock_delay_seconds=2.0,
        admin_override_code="ADMIN_RESET_9999",
    )
    eng = VaultAuthEngine(hardware=mock_hardware, config=config)
    return eng


@pytest.mark.asyncio
async def test_engine_initialization(mock_hardware: MockHardwareAdapter):
    """Verify VaultAuthEngine initializes hardware and enters IDLE state."""
    eng = VaultAuthEngine(hardware=mock_hardware)
    success = await eng.initialize()

    assert success is True
    assert eng.state == VaultState.IDLE
    assert mock_hardware.is_locked is True
    assert mock_hardware.current_display.line1 == "VAULT 404 READY"
    assert mock_hardware.current_display.led_color == LedColor.BLUE


@pytest.mark.asyncio
async def test_end_to_end_successful_authentication(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Test strict 5-stage happy path traversal resulting in UNLOCKED state."""
    # 0. Initialize & Start
    await engine.initialize()
    assert engine.state == VaultState.IDLE

    start_res = await engine.start_authentication()
    assert start_res is True
    assert engine.state == VaultState.AWAITING_RFID
    assert mock_hardware.current_display.line1 == "[1/5] SCAN RFID"

    # Stage 1: RFID
    rfid_res = await engine.submit_rfid("E2806894")
    assert rfid_res is True
    assert engine.state == VaultState.AWAITING_FINGERPRINT
    assert mock_hardware.current_display.line1 == "[2/5] FINGERPRINT"

    # Stage 2: Fingerprint
    fp_res = await engine.submit_fingerprint(finger_id=1, matched=True, confidence=0.98)
    assert fp_res is True
    assert engine.state == VaultState.AWAITING_FACE
    assert mock_hardware.current_display.line1 == "[3/5] FACE SCAN"

    # Stage 3: Face
    face_res = await engine.submit_face(
        face_id="SUBJECT_001_OPERATOR", confidence=0.96, is_live=True
    )
    assert face_res is True
    assert engine.state == VaultState.AWAITING_PASSWORD
    assert mock_hardware.current_display.line1 == "[4/5] ENTER PASS"

    # Stage 4: Password
    pwd_res = await engine.submit_password("VaultMasterKey#2026!")
    assert pwd_res is True
    assert engine.state == VaultState.AWAITING_VOICE
    assert mock_hardware.current_display.line1 == "[5/5] VOICE PHRASE"

    # Stage 5: Voice
    voice_res = await engine.submit_voice(
        phrase="OPEN SESAME OVERENGINEERED", confidence=0.97, voice_matched=True
    )
    assert voice_res is True
    assert engine.state == VaultState.UNLOCKED

    # Verify physical actuation
    assert mock_hardware.is_locked is False
    assert mock_hardware.current_display.line1 == "VAULT UNLOCKED"
    assert mock_hardware.current_display.led_color == LedColor.GREEN


@pytest.mark.asyncio
async def test_out_of_order_submissions_rejected(engine: VaultAuthEngine):
    """Verify any submission outside of the designated stage is rejected immediately."""
    await engine.initialize()
    assert engine.state == VaultState.IDLE

    # Submitting credentials when IDLE must fail
    assert await engine.submit_rfid("E2806894") is False
    assert await engine.submit_fingerprint(1) is False
    assert await engine.submit_face("SUBJECT_001_OPERATOR") is False
    assert await engine.submit_password("VaultMasterKey#2026!") is False
    assert await engine.submit_voice("OPEN SESAME OVERENGINEERED") is False
    assert engine.state == VaultState.IDLE

    # Advance to Stage 1 (AWAITING_RFID)
    await engine.start_authentication()
    assert engine.state == VaultState.AWAITING_RFID

    # Attempting Stage 3 or 4 while in Stage 1 must be rejected
    assert await engine.submit_face("SUBJECT_001_OPERATOR") is False
    assert await engine.submit_password("VaultMasterKey#2026!") is False
    assert await engine.submit_voice("OPEN SESAME OVERENGINEERED") is False
    assert engine.state == VaultState.AWAITING_RFID  # State unchanged


@pytest.mark.asyncio
async def test_hardware_event_driven_authentication(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Verify hardware adapter event bus triggers engine state advancements."""
    await engine.initialize()

    # Hardware simulates card scan while in IDLE -> starts auth and validates RFID
    await mock_hardware.simulate_rfid_scan("E2806894")
    assert engine.state == VaultState.AWAITING_FINGERPRINT

    # Hardware simulates fingerprint scan
    await mock_hardware.simulate_fingerprint_scan(finger_id=1, matched=True, confidence=0.99)
    assert engine.state == VaultState.AWAITING_FACE


@pytest.mark.asyncio
async def test_failed_attempts_and_lockout(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Verify exceeding max failed attempts triggers security LOCKOUT and alarm."""
    await engine.initialize()
    await engine.start_authentication()
    assert engine.state == VaultState.AWAITING_RFID

    # 1st failure
    assert await engine.submit_rfid("INVALID_CARD_1") is False
    assert engine.failed_attempts == 1
    assert engine.state == VaultState.AWAITING_RFID
    assert mock_hardware.current_display.line1 == "ACCESS DENIED"

    # 2nd failure
    assert await engine.submit_rfid("INVALID_CARD_2") is False
    assert engine.failed_attempts == 2
    assert engine.state == VaultState.AWAITING_RFID

    # 3rd failure -> triggers LOCKOUT
    assert await engine.submit_rfid("INVALID_CARD_3") is False
    assert engine.state == VaultState.LOCKOUT
    assert mock_hardware.is_locked is True
    assert mock_hardware.is_alarm_active is True
    assert mock_hardware.current_display.line1 == "SECURITY LOCKOUT"
    assert mock_hardware.current_display.led_color == LedColor.RED

    # Subsequent submissions in LOCKOUT are rejected
    assert await engine.submit_rfid("E2806894") is False
    assert await engine.start_authentication() is False


@pytest.mark.asyncio
async def test_tamper_event_triggers_immediate_lockout(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Verify hardware tamper alert triggers instant lockdown in any active stage."""
    await engine.initialize()
    await engine.start_authentication()
    await engine.submit_rfid("E2806894")
    assert engine.state == VaultState.AWAITING_FINGERPRINT

    # Trigger simulated chassis breach
    await mock_hardware.simulate_tamper(
        sensor="CHASSIS_MICROSWITCH", description="Lid opened without authorization"
    )

    assert engine.state == VaultState.LOCKOUT
    assert mock_hardware.is_locked is True
    assert mock_hardware.is_alarm_active is True
    assert mock_hardware.current_display.line1 == "SECURITY LOCKOUT"


@pytest.mark.asyncio
async def test_admin_override_clears_lockout(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Verify administrator override key clears LOCKOUT and restores IDLE."""
    await engine.initialize()
    await engine.trigger_tamper_lockout("Test lockout")
    assert engine.state == VaultState.LOCKOUT

    # Wrong override code fails
    cleared = await engine.clear_lockout("WRONG_CODE_123")
    assert cleared is False
    assert engine.state == VaultState.LOCKOUT

    # Correct override code succeeds
    cleared = await engine.clear_lockout("ADMIN_RESET_9999")
    assert cleared is True
    assert engine.state == VaultState.IDLE
    assert engine.failed_attempts == 0
    assert mock_hardware.is_locked is True


@pytest.mark.asyncio
async def test_stage_timeout_resets_to_idle(mock_hardware: MockHardwareAdapter):
    """Verify stage timeout timer safely resets active authentication back to IDLE."""
    config = EngineConfig(stage_timeout_seconds=0.1)  # 100ms timeout
    eng = VaultAuthEngine(hardware=mock_hardware, config=config)
    await eng.initialize()

    await eng.start_authentication()
    assert eng.state == VaultState.AWAITING_RFID

    # Wait for timeout to fire
    await asyncio.sleep(0.2)

    assert eng.state == VaultState.IDLE
    assert mock_hardware.is_locked is True


@pytest.mark.asyncio
async def test_state_change_listener_broadcast(engine: VaultAuthEngine):
    """Verify external subscribers receive StateTransitionEvent stream."""
    recorded_transitions: List[StateTransitionEvent] = []

    async def on_transition(event: StateTransitionEvent) -> None:
        recorded_transitions.append(event)

    engine.register_state_listener(on_transition)
    await engine.initialize()
    await engine.start_authentication()
    await engine.submit_rfid("E2806894")

    assert len(recorded_transitions) >= 3
    assert recorded_transitions[0].current_state == VaultState.IDLE
    assert recorded_transitions[1].current_state == VaultState.AWAITING_RFID
    assert recorded_transitions[2].current_state == VaultState.AWAITING_FINGERPRINT


@pytest.mark.asyncio
async def test_custom_validator_hook_injection(
    engine: VaultAuthEngine, mock_hardware: MockHardwareAdapter
):
    """Verify custom asynchronous validator callbacks can override default validation."""
    await engine.initialize()
    await engine.start_authentication()
    await engine.submit_rfid("E2806894")
    await engine.submit_fingerprint(1)
    await engine.submit_face("SUBJECT_001_OPERATOR")
    assert engine.state == VaultState.AWAITING_PASSWORD

    # Register custom password validator requiring special prefix
    async def custom_pwd_validator(password: str) -> bool:
        return password.startswith("DYNAMIC_SECRET_")

    engine.set_password_validator(custom_pwd_validator)

    # Standard password now rejected
    assert await engine.submit_password("VaultMasterKey#2026!") is False

    # Dynamic prefix password accepted
    assert await engine.submit_password("DYNAMIC_SECRET_987654") is True
    assert engine.state == VaultState.AWAITING_VOICE


if __name__ == "__main__":
    import sys

    print("Running Step 3 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
