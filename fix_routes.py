import re

with open("app/api/routes.py", "r") as f:
    routes = f.read()

# Replace FingerprintInputRequest with PhoneBiometricInputRequest
routes = routes.replace("FingerprintInputRequest", "PhoneBiometricInputRequest")
routes = routes.replace("PasswordInputRequest", "KeypadPinInputRequest")

# Replace simulate/fingerprint with simulate/phone_biometric
routes = routes.replace('"/api/v1/simulate/fingerprint"', '"/api/v1/simulate/phone_biometric"')
routes = routes.replace("def simulate_fingerprint", "def simulate_phone_biometric")
routes = routes.replace("engine.submit_fingerprint(", "engine.submit_phone_biometric(")
# The arguments for submit_phone_biometric are just success: bool, and reason: str
# So we need to rewrite the simulate_phone_biometric route logic.
routes = re.sub(
    r"matched = await engine.submit_phone_biometric\([\s\S]*?\)",
    "matched = await engine.submit_phone_biometric(success=payload.success, reason=payload.reason)",
    routes
)

routes = routes.replace("fingerprint_id=payload.fingerprint_id", "")
routes = routes.replace("fingerprint_id=user.fingerprint_id", "")
routes = routes.replace("fingerprint_id=u.fingerprint_id", "")

# Replace simulate/password with simulate/keypad_pin
routes = routes.replace('"/api/v1/simulate/password"', '"/api/v1/simulate/keypad_pin"')
routes = routes.replace("def simulate_password", "def simulate_keypad_pin")
routes = routes.replace("engine.submit_password(", "engine.submit_keypad_pin(")
routes = re.sub(
    r"await engine.submit_keypad_pin\([\s\S]*?\)",
    "await engine.submit_keypad_pin(pin=payload.pin)",
    routes
)

with open("app/api/routes.py", "w") as f:
    f.write(routes)
