import re

with open("app/core/engine.py", "r") as f:
    code = f.read()

# Replace AWAITING_FINGERPRINT with AWAITING_PHONE_BIOMETRIC
code = code.replace("AWAITING_FINGERPRINT", "AWAITING_PHONE_BIOMETRIC")

# Replace AWAITING_PASSWORD with AWAITING_KEYPAD_PIN
code = code.replace("AWAITING_PASSWORD", "AWAITING_KEYPAD_PIN")

# Replace submit_fingerprint
code = re.sub(
    r"async def submit_fingerprint[\s\S]*?(?=async def submit_face)",
    """async def submit_phone_biometric(self, success: bool, reason: str = "") -> bool:
        \"\"\"Stage 2: Submit phone biometric verification result.\"\"\"
        async with self._lock:
            if self._state != VaultState.AWAITING_PHONE_BIOMETRIC:
                logger.warning(
                    f"[OUT-OF-ORDER] Phone biometric submitted while in state {self._state.value}. Rejected."
                )
                return False

            if success:
                logger.info("[STAGE 2 PASS] Phone biometric authenticated.")
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.AWAITING_FACE,
                    reason="Phone biometric authenticated",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_PHONE_BIOMETRIC,
                    detail=f"Phone biometric failed: {reason}",
                )
                return False

    """, code
)

# Replace submit_password
code = re.sub(
    r"async def submit_password[\s\S]*?(?=async def submit_voice\()",
    """async def submit_keypad_pin(self, pin: str = None, hardware_verified: bool = False) -> bool:
        \"\"\"Stage 4: Submit Keypad PIN or hardware verification result.\"\"\"
        async with self._lock:
            if self._state != VaultState.AWAITING_KEYPAD_PIN:
                logger.warning(
                    f"[OUT-OF-ORDER] Keypad PIN submitted while in state {self._state.value}. Rejected."
                )
                return False

            is_valid = False

            if hardware_verified:
                is_valid = True
            elif pin is not None:
                # 1. Database Argon2id Hash Verification
                if self._active_user is not None:
                    try:
                        is_valid = self._password_hasher.verify(
                            self._active_user.password_hash, pin
                        )
                    except VerifyMismatchError:
                        is_valid = False
                    except Exception as ex:
                        logger.error(f"Error during Argon2 password verification: {ex}")
                        is_valid = False
                # 2. Default Config Passwords
                else:
                    is_valid = pin in self._config.valid_passwords

            if is_valid:
                logger.info("[STAGE 4 PASS] Keypad PIN authenticated successfully.")
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.AWAITING_VOICE,
                    reason="Keypad PIN authenticated",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_KEYPAD_PIN,
                    detail="Incorrect PIN entered",
                )
                return False

    """, code
)

# Replace hardware event handling
code = re.sub(
    r"elif event.event_type in \([\s\S]*?HardwareEventType.FINGERPRINT_FAILED,[\s\S]*?await self.submit_fingerprint\(finger_id, matched, confidence\)",
    """elif event.event_type == HardwareEventType.KEYPAD_PIN_RESULT:
            if self._state == VaultState.AWAITING_KEYPAD_PIN:
                result = event.payload.get("result", "")
                await self.submit_keypad_pin(hardware_verified=(result == "KEYPAD_PIN_VERIFIED"))""",
    code
)

# Update transition UI texts
code = code.replace('line1="[2/5] FINGERPRINT",', 'line1="[2/5] PHONE BIO",')
code = code.replace('line2="PLACE ON SCANNER",', 'line2="CHECK PHONE",')

code = code.replace('line1="[4/5] ENTER PASS",', 'line1="[4/5] ENTER PIN",')
code = code.replace('line2="ENTER SECRET KEY",', 'line2="KEYPAD INPUT",')

# Add trigger_alarm in _handle_failed_attempt
code = code.replace('        if self._failed_attempts >= self._config.max_failed_attempts:',
'''        if self._failed_attempts >= self._config.max_failed_attempts:''')
code = code.replace(
'''        else:
            # Update display with warning buzzer and remaining attempts''',
'''        else:
            await self._hardware.trigger_alarm(2000)
            # Update display with warning buzzer and remaining attempts''')

with open("app/core/engine.py", "w") as f:
    f.write(code)

