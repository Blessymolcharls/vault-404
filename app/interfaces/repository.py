"""Abstract Database Repository Interface for The Inconvenient Vault.

Defines persistence contracts for user credential enrollment, lookups,
and append-only, cryptographic hash-chained audit logging.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class VaultRepositoryInterface(ABC):
    """Abstract Base Class for vault user and audit log persistence."""

    @abstractmethod
    async def create_user(
        self,
        username: str,
        rfid_uid: str,
        password_hash: str,
        face_embedding: Union[List[float], np.ndarray],
        voice_print: Union[List[float], np.ndarray],
        phone_public_key: Optional[str] = None,
        voice_passphrase: str = "OPEN SESAME OVERENGINEERED",
    ) -> Any:
        """Enroll and persist a new user with full multi-modal credential profiles.

        Args:
            username: Unique username.
            rfid_uid: Unique RFID/NFC tag UID string.
            password_hash: Argon2id password hash string.
            face_embedding: 256D normalized facial feature embedding vector.
            voice_print: 256D normalized acoustic voiceprint vector.
            voice_passphrase: Challenge vocal passphrase string.

        Returns:
            User model instance.
        """
        pass

    @abstractmethod
    async def get_user_by_rfid(self, rfid_uid: str) -> Optional[Any]:
        """Fetch active user record by RFID tag UID.

        Args:
            rfid_uid: Normalized hexadecimal RFID UID string.

        Returns:
            Optional[User]: User instance if found and active, None otherwise.
        """
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> Optional[Any]:
        """Fetch user record by primary key identifier.

        Args:
            user_id: Unique integer user ID.

        Returns:
            Optional[User]: User instance if found, None otherwise.
        """
        pass

    @abstractmethod
    async def list_users(self) -> List[Any]:
        """Retrieve all registered users.

        Returns:
            List[User]: All enrolled users.
        """
        pass

    @abstractmethod
    async def log_audit_event(
        self,
        stage: str,
        event_type: str,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Append an immutable, cryptographic hash-chained security event record.

        Args:
            stage: VaultState string when the event occurred.
            event_type: Security classification (e.g., AUTH_SUCCESS, AUTH_FAILURE, LOCKOUT).
            user_id: Optional ID of the user undergoing authentication.
            metadata: Structured diagnostic and event metadata.

        Returns:
            AuditLog model instance.
        """
        pass

    @abstractmethod
    async def get_audit_logs(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """Retrieve paginated audit log entries in chronological order.

        Args:
            limit: Maximum entries to return.
            offset: Pagination offset index.

        Returns:
            List[AuditLog]: Chronological list of audit log records.
        """
        pass

    @abstractmethod
    async def verify_audit_trail_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic SHA-256 hash chain across all audit log records.

        Traverses the entire audit log from the genesis entry to the latest entry,
        recomputing the hash chain to detect any tampering, modification, or deletion.

        Returns:
            Tuple[bool, Optional[str]]: (True, None) if the hash chain is fully intact;
                                        (False, error_message) if tampering is detected.
        """
        pass
