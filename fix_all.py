import re

with open("app/core/engine.py", "r") as f:
    engine = f.read()
engine = engine.replace("AWAITING_PHONE_BIOMETRIC", "AWAITING_FACE")
with open("app/core/engine.py", "w") as f:
    f.write(engine)

for test_file in ["test_step3.py", "test_step5.py", "test_step6.py", "test_step7.py", "test_step8.py", "test_step9.py", "test_step10.py"]:
    try:
        with open(test_file, "r") as f:
            code = f.read()
        code = code.replace("VaultState.AWAITING_PHONE_BIOMETRIC", "VaultState.AWAITING_FACE")
        # For the REST API tests where the value is checked via string:
        code = code.replace('"AWAITING_PHONE_BIOMETRIC"', '"AWAITING_FACE"')
        # Replace submit_face instead of submit_face_frame (if any mismatches)
        with open(test_file, "w") as f:
            f.write(code)
    except Exception as e:
        pass

