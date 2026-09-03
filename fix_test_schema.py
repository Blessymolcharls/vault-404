import re

# test_step1.py
with open("test_step1.py", "r") as f:
    t1 = f.read()
t1 = t1.replace("FINGERPRINT_MATCHED", "KEYPAD_STATUS")
t1 = t1.replace("FINGERPRINT_FAILED", "KEYPAD_PIN_RESULT")
with open("test_step1.py", "w") as f:
    f.write(t1)

# test_step2.py
with open("test_step2.py", "r") as f:
    t2 = f.read()
t2 = t2.replace("test_simulate_fingerprint_scan_and_capture", "test_simulate_keypad_scan_and_capture")
t2 = re.sub(r'await adapter\.simulate_fingerprint_scan\([^)]+\)', 'await adapter.simulate_keypad_pin_result("KEYPAD_PIN_VERIFIED")', t2)
with open("test_step2.py", "w") as f:
    f.write(t2)

# test_step7.py
with open("test_step7.py", "r") as f:
    t7 = f.read()
t7 = re.sub(r'^\s*fingerprint_id=1,\n', '', t7, flags=re.MULTILINE)
with open("test_step7.py", "w") as f:
    f.write(t7)

# test_step8.py
with open("test_step8.py", "r") as f:
    t8 = f.read()
t8 = t8.replace('"/api/v1/simulate/fingerprint"', '"/api/v1/simulate/phone_biometric"')
t8 = re.sub(r'json=\{"finger_id": 1, "matched": True, "confidence": 0\.98\}', 'json={"success": True, "reason": ""}', t8)
t8 = t8.replace('"/api/v1/simulate/password"', '"/api/v1/simulate/keypad_pin"')
t8 = re.sub(r'json=\{"password": "VaultMasterKey#2026!"\}', 'json={"pin": "VaultMasterKey#2026!"}', t8)
with open("test_step8.py", "w") as f:
    f.write(t8)

# test_step9.py
with open("test_step9.py", "r") as f:
    t9 = f.read()
t9 = t9.replace('"/api/v1/simulate/fingerprint"', '"/api/v1/simulate/phone_biometric"')
t9 = re.sub(r'json=\{"finger_id": 1, "matched": True, "confidence": 0\.98\}', 'json={"success": True, "reason": ""}', t9)
t9 = t9.replace('"/api/v1/simulate/password"', '"/api/v1/simulate/keypad_pin"')
t9 = re.sub(r'json=\{"password": "VaultMasterKey#2026!"\}', 'json={"pin": "VaultMasterKey#2026!"}', t9)
with open("test_step9.py", "w") as f:
    f.write(t9)

# test_step10.py
with open("test_step10.py", "r") as f:
    t10 = f.read()
t10 = re.sub(r'"fingerprint": \{\"matched\": true, \"id\": 1\}', '"keypad": {"status": "KEYPAD_PIN_VERIFIED"}', t10)
t10 = t10.replace('FINGERPRINT_MATCHED', 'KEYPAD_PIN_RESULT')
t10 = re.sub(r'await adapter\.simulate_fingerprint_scan\([^)]+\)', 'await adapter.simulate_keypad_pin_result("KEYPAD_PIN_VERIFIED")', t10)
with open("test_step10.py", "w") as f:
    f.write(t10)

