import re

# 1. types.py
with open("app/core/types.py", "r") as f:
    models = f.read()

models = models.replace("    AWAITING_PHONE_BIOMETRIC = \"AWAITING_PHONE_BIOMETRIC\"\n", "")

with open("app/core/types.py", "w") as f:
    f.write(models)

# 2. engine.py
with open("app/core/engine.py", "r") as f:
    engine = f.read()

# Replace transition in submit_rfid
engine = engine.replace(
    "await self._transition_to(VaultState.AWAITING_PHONE_BIOMETRIC, reason=f\"RFID authenticated (User: {self._active_user.username})\")",
    "await self._transition_to(VaultState.AWAITING_FACE, reason=f\"RFID authenticated (User: {self._active_user.username})\")"
)
engine = engine.replace(
    "self._state = VaultState.AWAITING_PHONE_BIOMETRIC",
    "self._state = VaultState.AWAITING_FACE"
)

# Remove submit_phone_biometric
engine = re.sub(r'    async def submit_phone_biometric\([\s\S]*?(?=    # ========================================================================)', '', engine)

with open("app/core/engine.py", "w") as f:
    f.write(engine)

# 3. routes.py
with open("app/api/routes.py", "r") as f:
    routes = f.read()

# Remove PhoneBiometricInputRequest
routes = re.sub(r'class PhoneBiometricInputRequest[\s\S]*?    reason: str\n\n', '', routes)

# Remove /api/v1/simulate/phone_biometric
routes = re.sub(r'@router\.post\("/api/v1/simulate/phone_biometric"\)[\s\S]*?(?=@router\.post\("/api/v1/simulate/face"\))', '', routes)

with open("app/api/routes.py", "w") as f:
    f.write(routes)

