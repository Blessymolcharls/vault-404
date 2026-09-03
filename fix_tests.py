import glob

def fix_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Hardware mock
    content = content.replace("simulate_fingerprint_scan", "simulate_keypad_scan")
    # Actually wait, mock_hardware has simulate_fingerprint_scan. Let's not touch the mock_hardware's method name unless I changed it. I haven't changed mock_hardware's simulate_fingerprint_scan yet.
    # We should change mock_hardware.py first.

    # Fix states
    content = content.replace("AWAITING_FINGERPRINT", "AWAITING_PHONE_BIOMETRIC")
    content = content.replace("AWAITING_PASSWORD", "AWAITING_KEYPAD_PIN")

    # Fix Engine methods
    content = content.replace("engine.submit_fingerprint(1, matched=True, confidence=0.98)", "engine.submit_phone_biometric(True)")
    content = content.replace("engine.submit_fingerprint(finger_id=1, matched=True, confidence=0.98)", "engine.submit_phone_biometric(True)")
    content = content.replace("engine.submit_fingerprint(1)", "engine.submit_phone_biometric(True)")
    content = content.replace("engine.submit_password(\"VaultMasterKey#2026!\")", "engine.submit_keypad_pin(\"VaultMasterKey#2026!\")")
    content = content.replace("engine.submit_password(\"WRONG_PASSWORD\")", "engine.submit_keypad_pin(\"WRONG_PASSWORD\")")
    content = content.replace("engine.submit_password", "engine.submit_keypad_pin")

    # Fix display lines
    content = content.replace('"[2/5] FINGERPRINT"', '"[2/5] PHONE BIO"')
    content = content.replace('"[4/5] ENTER PASS"', '"[4/5] ENTER PIN"')

    with open(filepath, "w") as f:
        f.write(content)

for f in glob.glob("test_step*.py"):
    fix_file(f)
    print(f"Fixed {f}")
