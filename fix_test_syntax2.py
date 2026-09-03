import re

with open("test_step3.py", "r") as f:
    code = f.read()

code = re.sub(r'^\s*assert is False\n', '', code, flags=re.MULTILINE)

with open("test_step3.py", "w") as f:
    f.write(code)

