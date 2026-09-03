import re

# test_step10.py
with open("test_step10.py", "r") as f:
    t10 = f.read()

# Fix the assert engine.state == VaultState.AWAITING_FACE failure.
# Currently KEYPAD_PIN_RESULT is sent during AWAITING_PHONE_BIOMETRIC, which is rejected.
# The correct order is RFID -> Phone -> Face -> Keypad -> Voice
# We need to simulate Phone and Face before Keypad.
t10 = t10.replace('''        # 2. ESP32 emits KEYPAD_PIN_RESULT -> Engine verifies Stage 2
        adapter._process_incoming_json(
            json.dumps(
                {
                    "event": "KEYPAD_PIN_RESULT",
                    "payload": {"finger_id": 1, "matched": True, "confidence": 0.98},
                }
            )
        )
        await asyncio.sleep(0.05)''', 
'''        # 2. Simulate Phone Biometric
        await engine.submit_phone_biometric(success=True)
        assert engine.state == VaultState.AWAITING_FACE

        # 3. Simulate Face Biometric
        await engine.submit_face(face_id="SUBJECT_001_OPERATOR", confidence=0.98, is_live=True)
        assert engine.state == VaultState.AWAITING_KEYPAD_PIN

        # 4. ESP32 emits KEYPAD_PIN_RESULT -> Engine verifies Stage 4
        adapter._process_incoming_json(
            json.dumps(
                {
                    "event": "KEYPAD_PIN_RESULT",
                    "payload": {"pin": "VaultMasterKey#2026!"},
                }
            )
        )
        await asyncio.sleep(0.05)
        assert engine.state == VaultState.AWAITING_VOICE''')

with open("test_step10.py", "w") as f:
    f.write(t10)

