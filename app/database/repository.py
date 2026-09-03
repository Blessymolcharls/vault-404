"""Concrete SQLite & SQLAlchemy 2.0 Repository Implementation with Cryptographic Hash Chaining."""

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import AuditLog, User
from app.interfaces.repository import VaultRepositoryInterface

logger = logging.getLogger("vault.database.repository")

GENESIS_PREVIOUS_HASH = "0" * 64


def normalize_timestamp_str(ts: Union[datetime, str]) -> str:
    """Standardize datetime representation to deterministic ISO 8601 UTC string with Z suffix."""
    if isinstance(ts, str):
        return ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def calculate_audit_entry_hash(
    previous_hash: str,
    timestamp: Union[datetime, str],
    user_id: Optional[int],
    stage: str,
    event_type: str,
    metadata_json: str,
) -> str:
    """Compute deterministic SHA-256 hash for an audit log record in the cryptographic chain."""
    uid_str = str(user_id) if user_id is not None else ""
    ts_str = normalize_timestamp_str(timestamp)
    payload = f"{previous_hash}|{ts_str}|{uid_str}|{stage}|{event_type}|{metadata_json}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SqliteVaultRepository(VaultRepositoryInterface):
    """Asynchronous repository for user multi-modal credentials and append-only tamper-evident audit logs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize repository with an asynchronous sessionmaker factory."""
        self._session_factory = session_factory

    async def create_user(
        self,
        username: str,
        rfid_uid: str,
        fingerprint_id: int,
        password_hash: str,
        face_embedding: Union[List[float], np.ndarray],
        voice_print: Union[List[float], np.ndarray],
        voice_passphrase: str = "OPEN SESAME OVERENGINEERED",
    ) -> User:
        """Enroll and persist a new user record."""
        face_list = (
            face_embedding.tolist()
            if isinstance(face_embedding, np.ndarray)
            else list(face_embedding)
        )
        voice_list = (
            voice_print.tolist()
            if isinstance(voice_print, np.ndarray)
            else list(voice_print)
        )

        user = User(
            username=username.strip(),
            rfid_uid=rfid_uid.strip().upper(),
            fingerprint_id=fingerprint_id,
            password_hash=password_hash,
            face_embedding_json=json.dumps(face_list),
            voice_print_json=json.dumps(voice_list),
            voice_passphrase=voice_passphrase.strip().upper(),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        async with self._session_factory() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Enrolled new user '{username}' (ID: {user.id}, RFID: {rfid_uid})")
            return user

    async def get_user_by_rfid(self, rfid_uid: str) -> Optional[User]:
        """Fetch active user by RFID tag UID."""
        normalized_uid = rfid_uid.strip().upper()
        async with self._session_factory() as session:
            stmt = select(User).where(User.rfid_uid == normalized_uid, User.is_active == True)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Fetch user by ID."""
        async with self._session_factory() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_users(self) -> List[User]:
        """Retrieve all users."""
        async with self._session_factory() as session:
            stmt = select(User).order_by(User.id.asc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def log_audit_event(
        self,
        stage: str,
        event_type: str,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Append an immutable, cryptographic hash-chained security event record."""
        meta_str = json.dumps(metadata or {}, sort_keys=True)
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            # Query last audit log to get previous entry_hash
            stmt = select(AuditLog).order_by(desc(AuditLog.id)).limit(1)
            last_entry = (await session.execute(stmt)).scalar_one_or_none()

            previous_hash = last_entry.entry_hash if last_entry else GENESIS_PREVIOUS_HASH
            entry_hash = calculate_audit_entry_hash(
                previous_hash=previous_hash,
                timestamp=now,
                user_id=user_id,
                stage=stage,
                event_type=event_type,
                metadata_json=meta_str,
            )

            log_entry = AuditLog(
                timestamp=now,
                user_id=user_id,
                stage=stage,
                event_type=event_type,
                metadata_json=meta_str,
                previous_hash=previous_hash,
                entry_hash=entry_hash,
            )

            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)

            logger.info(
                f"[AUDIT LOG #{log_entry.id}] Stage: {stage} | Event: {event_type} | "
                f"Hash: {entry_hash[:12]}... (Prev: {previous_hash[:12]}...)"
            )
            return log_entry

    async def get_audit_logs(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        """Retrieve paginated audit logs in chronological order."""
        async with self._session_factory() as session:
            stmt = select(AuditLog).order_by(AuditLog.id.asc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def verify_audit_trail_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic SHA-256 hash chain across all audit log records."""
        async with self._session_factory() as session:
            stmt = select(AuditLog).order_by(AuditLog.id.asc())
            logs = list((await session.execute(stmt)).scalars().all())

            if not logs:
                return True, None

            expected_prev_hash = GENESIS_PREVIOUS_HASH

            for log in logs:
                # 1. Check previous_hash link
                if log.previous_hash != expected_prev_hash:
                    error_msg = (
                        f"Hash chain broken at Log ID {log.id}: expected previous_hash "
                        f"'{expected_prev_hash}', got '{log.previous_hash}'"
                    )
                    logger.error(f"[SECURITY ALERT] {error_msg}")
                    return False, error_msg

                # 2. Recompute current entry_hash
                recomputed_hash = calculate_audit_entry_hash(
                    previous_hash=log.previous_hash,
                    timestamp=log.timestamp,
                    user_id=log.user_id,
                    stage=log.stage,
                    event_type=log.event_type,
                    metadata_json=log.metadata_json,
                )

                if log.entry_hash != recomputed_hash:
                    error_msg = (
                        f"Tamper detected in Log ID {log.id}: entry_hash '{log.entry_hash}' "
                        f"does not match recomputed hash '{recomputed_hash}'"
                    )
                    logger.error(f"[SECURITY ALERT] {error_msg}")
                    return False, error_msg

                expected_prev_hash = log.entry_hash

            logger.info(f"Audit trail verified successfully across all {len(logs)} records.")
            return True, None
