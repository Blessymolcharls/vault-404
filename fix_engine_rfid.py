import re

with open("app/core/engine.py", "r") as f:
    engine = f.read()

engine = engine.replace("VaultState.AWAITING_PHONE_BIOMETRIC", "VaultState.AWAITING_FACE")

with open("app/core/engine.py", "w") as f:
    f.write(engine)

