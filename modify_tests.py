import glob
import re

for filename in glob.glob("test_step*.py"):
    with open(filename, "r") as f:
        code = f.read()

    # In test_step1.py, AWAITING_PHONE_BIOMETRIC might be in VaultState checks
    code = code.replace("        VaultState.AWAITING_PHONE_BIOMETRIC,\n", "")

    # In other tests, we have:
    # assert engine.state == VaultState.AWAITING_PHONE_BIOMETRIC
    # # Step 2: Fingerprint
    # assert await engine.submit_phone_biometric(True) is True
    
    code = re.sub(
        r'\s*assert engine\.state == VaultState\.AWAITING_PHONE_BIOMETRIC\s*# Step 2:.*?assert await engine\.submit_phone_biometric\(True\) is True',
        '',
        code,
        flags=re.DOTALL
    )

    code = re.sub(
        r'\s*assert engine\.state == VaultState\.AWAITING_PHONE_BIOMETRIC\s*assert await engine\.submit_phone_biometric\(True\) is True',
        '',
        code,
        flags=re.DOTALL
    )

    code = re.sub(
        r'\s*await engine\.submit_phone_biometric\(True\)',
        '',
        code,
        flags=re.DOTALL
    )
    
    code = re.sub(
        r'\s*await engine\.submit_phone_biometric\(success=True\)',
        '',
        code,
        flags=re.DOTALL
    )

    # In test_step8.py (REST API tests):
    # response = client.post("/api/v1/simulate/phone_biometric", json={"success": True, "reason": "Test FP"})
    # assert response.status_code == 200
    code = re.sub(
        r'\s*# Step 2: Fingerprint\s*response = client\.post\("/api/v1/simulate/phone_biometric", json={"success": True, "reason": "Test FP"}\)\s*assert response\.status_code == 200\s*data = response\.json\(\)\s*assert data\["matched"\] is True\s*assert data\["new_state"\] == "AWAITING_FACE"',
        '',
        code,
        flags=re.DOTALL
    )
    code = re.sub(
        r'\s*response = client\.post\("/api/v1/simulate/phone_biometric", json={"success": True, "reason": "Test FP"}\)\s*assert response\.status_code == 200\s*data = response\.json\(\)\s*assert data\["matched"\] is True\s*assert data\["new_state"\] == "AWAITING_FACE"',
        '',
        code,
        flags=re.DOTALL
    )

    # In test_step7.py we have a mock audit log creation
    code = code.replace(
        'stage="AWAITING_PHONE_BIOMETRIC"',
        'stage="AWAITING_FACE"'
    )
    code = code.replace(
        'event_type="FP_2"',
        'event_type="FACE_2"'
    )

    # test_step9.py: e2e test via ui
    code = re.sub(
        r'\s*# 2\. Fingerprint\s*assert await engine\.submit_phone_biometric\(True\) is True',
        '',
        code,
        flags=re.DOTALL
    )

    with open(filename, "w") as f:
        f.write(code)

