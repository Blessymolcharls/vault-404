import re

# 1. Update hardware interface
with open("app/interfaces/hardware.py", "r") as f:
    hw_int = f.read()

if "def enable_keypad" not in hw_int:
    hw_int = hw_int.replace(
        "    async def trigger_alarm(self, duration_ms: int) -> None:",
        "    async def trigger_alarm(self, duration_ms: int) -> None:\n        ...\n\n    async def enable_keypad(self, expected_pin_hash: str) -> bool:\n        ...\n\n    async def disable_keypad(self) -> bool:\n"
    )
    with open("app/interfaces/hardware.py", "w") as f:
        f.write(hw_int)

# 2. Update esp32 hardware
with open("app/adapters/esp32_hardware.py", "r") as f:
    esp32_hw = f.read()

if "def enable_keypad" not in esp32_hw:
    esp32_hw = esp32_hw.replace(
        "    async def trigger_alarm(self, duration_ms: int) -> None:",
        "    async def enable_keypad(self, expected_pin_hash: str) -> bool:\n        cmd = {\"cmd\": \"ENABLE_KEYPAD\", \"expected_pin_hash\": expected_pin_hash}\n        return await self._send_command(cmd)\n\n    async def disable_keypad(self) -> bool:\n        cmd = {\"cmd\": \"DISABLE_KEYPAD\"}\n        return await self._send_command(cmd)\n\n    async def trigger_alarm(self, duration_ms: int) -> None:"
    )
    esp32_hw = esp32_hw.replace(
        '"FINGERPRINT_MATCHED": HardwareEventType.FINGERPRINT_MATCHED,',
        '"KEYPAD_STATUS": HardwareEventType.KEYPAD_STATUS,'
    )
    esp32_hw = esp32_hw.replace(
        '"FINGERPRINT_FAILED": HardwareEventType.FINGERPRINT_FAILED,',
        '"KEYPAD_PIN_RESULT": HardwareEventType.KEYPAD_PIN_RESULT,'
    )
    with open("app/adapters/esp32_hardware.py", "w") as f:
        f.write(esp32_hw)

# 3. Update mock hardware
with open("app/adapters/mock_hardware.py", "r") as f:
    mock_hw = f.read()

if "def enable_keypad" not in mock_hw:
    mock_hw = mock_hw.replace(
        "    async def trigger_alarm(self, duration_ms: int) -> None:",
        "    async def enable_keypad(self, expected_pin_hash: str) -> bool:\n        return True\n\n    async def disable_keypad(self) -> bool:\n        return True\n\n    async def trigger_alarm(self, duration_ms: int) -> None:"
    )
    with open("app/adapters/mock_hardware.py", "w") as f:
        f.write(mock_hw)

# 4. Update engine.py to call enable_keypad and disable_keypad
with open("app/core/engine.py", "r") as f:
    engine = f.read()

if "await self._hardware.enable_keypad" not in engine:
    # Add to AWAITING_KEYPAD_PIN transition
    engine = engine.replace(
        'elif new_state == VaultState.AWAITING_KEYPAD_PIN:',
        'elif new_state == VaultState.AWAITING_KEYPAD_PIN:\n            hash_str = "TODO_GET_HASH"\n            if self._active_user:\n                hash_str = self._active_user.password_hash\n            await self._hardware.enable_keypad(hash_str)'
    )
    # Add disable_keypad to transition to IDLE or ERROR or LOCKOUT or UNLOCKED, maybe just AWAITING_VOICE
    engine = engine.replace(
        'elif new_state == VaultState.AWAITING_VOICE:',
        'elif new_state == VaultState.AWAITING_VOICE:\n            await self._hardware.disable_keypad()'
    )
    with open("app/core/engine.py", "w") as f:
        f.write(engine)

