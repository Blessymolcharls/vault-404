import re

with open("test_step1.py", "r") as f:
    code = f.read()

code = code.replace('"AWAITING_PHONE_BIOMETRIC",', '')

with open("test_step1.py", "w") as f:
    f.write(code)

