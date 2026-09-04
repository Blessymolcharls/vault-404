"""Centralized Password Authentication and Cryptographic Hashing for Vault-404.

Provides single-point-of-truth verification for all keypad and authentication interfaces
(physical ESP32 serial, virtual simulator, REST API, and internal state engine)
using Argon2id hashing and secure environment variable configuration.
"""

import logging
import os
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded
load_dotenv()

logger = logging.getLogger("vault.core.auth")
_hasher = PasswordHasher()


def get_configured_password() -> Optional[str]:
    """Retrieve the raw configured VAULT_PASSWORD from environment."""
    pwd = os.environ.get("VAULT_PASSWORD")
    if pwd is not None:
        pwd = pwd.strip()
        if len(pwd) > 0:
            return pwd
    return None


def get_configured_password_hash() -> Optional[str]:
    """Generate an Argon2 hash of the configured VAULT_PASSWORD from environment.
    
    Returns:
        Optional[str]: Argon2 hash string, or None if VAULT_PASSWORD is not set.
    """
    raw = get_configured_password()
    if not raw:
        return None
    return _hasher.hash(raw)


def verify_password(
    candidate: Optional[str],
    expected_hash: Optional[str] = None,
) -> bool:
    """Centralized verification function for all keypad and password authentication in Vault-404.
    
    All hardware events, API endpoints, CLI simulator actions, and FSM stages MUST route
    through this function to perform password validation.

    Args:
        candidate: Plaintext candidate password entered by the user or hardware keypad.
        expected_hash: Optional specific Argon2 hash to verify against (e.g. database user).
                       If None, verifies against the active VAULT_PASSWORD environment configuration.

    Returns:
        bool: True if authentication succeeds; False if candidate is invalid, incorrect, or unconfigured.
    """
    if candidate is None or not isinstance(candidate, str):
        logger.warning("[AUTH REJECTED] Candidate password is None or not a string.")
        return False

    candidate_str = candidate.strip()
    if len(candidate_str) == 0:
        logger.warning("[AUTH REJECTED] Candidate password is empty.")
        return False

    # 1. Direct match against active configured VAULT_PASSWORD environment variable
    env_pwd = get_configured_password()
    if env_pwd and candidate_str == env_pwd:
        logger.info("[AUTH SUCCESS] Password matched configured VAULT_PASSWORD environment variable.")
        return True

    # 2. Match against expected Argon2 hash if provided (e.g., from DB user)
    if expected_hash:
        try:
            _hasher.verify(expected_hash, candidate_str)
            logger.info("[AUTH SUCCESS] Password successfully verified against expected hash.")
            return True
        except (VerifyMismatchError, InvalidHashError):
            pass
        except Exception as ex:
            logger.warning(f"[AUTH ERROR] Error verifying expected hash: {ex}")

    # 3. Match against hashed environment password if hash wasn't verified above
    if env_pwd:
        try:
            target_hash = _hasher.hash(env_pwd)
            _hasher.verify(target_hash, candidate_str)
            logger.info("[AUTH SUCCESS] Password successfully verified with Argon2.")
            return True
        except Exception:
            pass

    logger.warning("[AUTH FAILED] Incorrect password provided.")
    return False
