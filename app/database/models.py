"""SQLAlchemy 2.0 Declarative Models for The Inconvenient Vault.

Defines schemas for multi-modal enrolled users and immutable,
cryptographic hash-chained security audit logs.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative database models."""

    pass


class User(Base):
    """Enrolled Vault Operator multi-modal credential record."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    rfid_uid: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_public_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    face_embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    voice_print_json: Mapped[str] = mapped_column(Text, nullable=False)
    voice_passphrase: Mapped[str] = mapped_column(
        String(128), default="OPEN SESAME OVERENGINEERED", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to audit logs
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")

    def get_face_embedding(self) -> np.ndarray:
        """Deserialize face embedding vector as NumPy float32 array."""
        return np.array(json.loads(self.face_embedding_json), dtype=np.float32)

    def get_voice_print(self) -> np.ndarray:
        """Deserialize voice print vector as NumPy float32 array."""
        return np.array(json.loads(self.voice_print_json), dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user record to dictionary representation."""
        return {
            "id": self.id,
            "username": self.username,
            "rfid_uid": self.rfid_uid,
            "phone_public_key": self.phone_public_key,
            "voice_passphrase": self.voice_passphrase,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    """Append-only, cryptographic SHA-256 hash-chained security event log."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Relationship to user
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")

    def get_metadata(self) -> Dict[str, Any]:
        """Parse JSON metadata dictionary."""
        try:
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit log record to dictionary representation."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "stage": self.stage,
            "event_type": self.event_type,
            "metadata": self.get_metadata(),
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }
