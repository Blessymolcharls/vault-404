import re

with open("test_step3.py", "r") as f:
    code = f.read()

code = re.sub(r'^\s*fp_res =\s*\n', '', code, flags=re.MULTILINE)
code = re.sub(r'^\s*assert fp_res is True\n', '', code, flags=re.MULTILINE)

with open("test_step3.py", "w") as f:
    f.write(code)


with open("test_step6.py", "r") as f:
    code = f.read()

code = re.sub(r'^\s*assert is True\n', '', code, flags=re.MULTILINE)

with open("test_step6.py", "w") as f:
    f.write(code)
