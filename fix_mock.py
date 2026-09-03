import re

with open("app/adapters/mock_hardware.py", "r") as f:
    mock_hw = f.read()

mock_hw = re.sub(
    r"async def simulate_fingerprint_scan[\s\S]*?(?=async def simulate_fingerprint_capture)",
    """async def simulate_keypad_pin_result(self, result_str: str) -> HardwareEvent:
        event = HardwareEvent(
            event_type=HardwareEventType.KEYPAD_PIN_RESULT,
            payload={"result": result_str},
            source_id="MOCK_KEYPAD",
        )
        await self._dispatch_event(event)
        return event
    """,
    mock_hw
)

mock_hw = re.sub(
    r"async def simulate_fingerprint_capture[\s\S]*?(?=async def simulate_tamper)",
    "",
    mock_hw
)

with open("app/adapters/mock_hardware.py", "w") as f:
    f.write(mock_hw)

with open("test_step3.py", "r") as f:
    test = f.read()

# Replace the hardware-driven test in test_step3
test = test.replace(
    """    # Hardware simulates fingerprint scan
    await mock_hardware.simulate_keypad_scan(finger_id=1, matched=True, confidence=0.99)
    assert engine.state == VaultState.AWAITING_FACE""",
    """    # Phone biometric and face are not hardware events, so just pass them
    await engine.submit_phone_biometric(True)
    await engine.submit_face("SUBJECT_001_OPERATOR", confidence=0.96, is_live=True)
    
    # Hardware simulates keypad pin result
    await mock_hardware.simulate_keypad_pin_result("KEYPAD_PIN_VERIFIED")
    assert engine.state == VaultState.AWAITING_VOICE"""
)

# And in cli_simulator.py, fix references to fingerprint and password
with open("cli_simulator.py", "r") as f:
    cli = f.read()

cli = cli.replace("FINGERPRINT_MATCHED", "KEYPAD_PIN_RESULT")
cli = cli.replace("FINGERPRINT_FAILED", "KEYPAD_PIN_RESULT")
cli = cli.replace("simulate_fingerprint_scan", "simulate_keypad_pin_result")

with open("cli_simulator.py", "w") as f:
    f.write(cli)

with open("test_step3.py", "w") as f:
    f.write(test)
