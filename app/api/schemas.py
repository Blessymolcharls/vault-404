"""Pydantic v2 Request & Response Data Schemas for the FastAPI REST/WebSocket API."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.core.types import DisplayStatus, LedColor, VaultState


class GenericResponse(BaseModel):
    """Standard API outcome envelope."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the requested operation succeeded")
    message: str = Field(description="Human-readable status summary")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Optional payload data")


class VaultStatusResponse(BaseModel):
    """Real-time diagnostic telemetry describing the state of the vault and peripherals."""

    model_config = ConfigDict(frozen=True)

    state: VaultState = Field(description="Current active finite state machine state")
    is_locked: bool = Field(description="Physical lock solenoid status (True=locked, False=unlocked)")
    is_alarm_active: bool = Field(description="Chassis alarm / siren actuation status")
    failed_attempts: int = Field(description="Failed verification attempts in current stage")
    max_failed_attempts: int = Field(description="Maximum failed attempts before lockout")
    active_user_id: Optional[int] = Field(default=None, description="Active user ID if identified")
    active_username: Optional[str] = Field(default=None, description="Active username if identified")
    display: DisplayStatus = Field(description="Current LCD and LED state")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResetVaultRequest(BaseModel):
    """Payload to reset the vault back to IDLE or clear a security lockout."""

    admin_override_key: Optional[str] = Field(
        default=None, description="Emergency administrator override key to clear LOCKOUT"
    )


class RfidInputRequest(BaseModel):
    """Payload for Stage 1 RFID scan ingestion."""

    card_uid: str = Field(..., description="Hexadecimal RFID tag UID (e.g., 'E2806894')")


class FaceInputRequest(BaseModel):
    """Payload for Stage 3 facial biometric submission."""

    subject_seed: Optional[int] = Field(
        default=None,
        description="Mock camera synthetic subject seed (e.g., 777 for authorized operator)",
    )
    image_base64: Optional[str] = Field(
        default=None,
        description="Optional Base64-encoded JPEG/PNG image bytes",
    )
    face_id: Optional[str] = Field(
        default="SUBJECT_001_OPERATOR",
        description="Fallback subject ID identifier",
    )
    noise_level: float = Field(default=0.01, ge=0.0, description="Simulated sensor noise variance")


class KeypadPinInputRequest(BaseModel):
    """Payload for Stage 4 keypad PIN submission."""

    pin: str = Field(..., min_length=1, description="Plaintext keypad PIN")


class VoiceInputRequest(BaseModel):
    """Payload for Stage 5 vocal challenge submission."""

    speaker_seed: Optional[int] = Field(
        default=None,
        description="Mock audio synthetic speaker seed (e.g., 1 for authorized operator)",
    )
    spoken_phrase: Optional[str] = Field(
        default="OPEN SESAME OVERENGINEERED",
        description="Spoken vocal challenge passphrase string",
    )
    noise_level: float = Field(default=0.01, ge=0.0, description="Simulated acoustic background noise variance")
    audio_base64: Optional[str] = Field(
        default=None,
        description="Optional Base64-encoded audio recording",
    )

class TamperRequest(BaseModel):
    """Payload to simulate physical tamper sensor breach."""

    reason: str = Field(default="Chassis Tamper Breached", description="Tamper event description")


class UserEnrollRequest(BaseModel):
    """Payload to enroll an operator with multi-modal credentials."""

    username: str = Field(..., min_length=2, max_length=64)
    rfid_uid: str = Field(..., min_length=4, max_length=32)
    password: str = Field(..., min_length=6)
    phone_public_key: Optional[str] = Field(default=None, description="Optional Base64 encoded ECDSA public key from phone")
    face_subject_seed: int = Field(default=777, description="Subject seed used to generate face profile")
    voice_speaker_seed: int = Field(default=1, description="Speaker seed used to generate voiceprint")
    voice_passphrase: str = Field(default="OPEN SESAME OVERENGINEERED")


class UserResponseSchema(BaseModel):
    """User profile response representation."""

    id: int
    username: str
    rfid_uid: str
    phone_public_key: Optional[str] = None
    voice_passphrase: str
    is_active: bool
    created_at: Optional[datetime] = None


class AuditLogEntrySchema(BaseModel):
    """Individual audit log record in the cryptographic chain."""

    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    stage: str
    event_type: str
    metadata: Dict[str, Any]
    previous_hash: str
    entry_hash: str


class AuditLogResponseSchema(BaseModel):
    """Paginated audit records accompanied by cryptographic hash-chain forensic verification status."""

    total_records: int
    is_chain_valid: bool
    integrity_error: Optional[str] = None
    logs: List[AuditLogEntrySchema]
