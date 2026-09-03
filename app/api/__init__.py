"""FastAPI REST and WebSocket API package for The Inconvenient Vault."""

from app.api.routes import router
from app.api.schemas import (
    AuditLogEntrySchema,
    AuditLogResponseSchema,
    FaceInputRequest,
    GenericResponse,
    KeypadPinInputRequest,
    ResetVaultRequest,
    RfidInputRequest,
    TamperRequest,
    UserEnrollRequest,
    UserResponseSchema,
    VaultStatusResponse,
    VoiceInputRequest,
)
from app.api.websocket_manager import WebSocketManager

__all__ = [
    "router",
    "WebSocketManager",
    "VaultStatusResponse",
    "ResetVaultRequest",
    "RfidInputRequest",
    "FaceInputRequest",
    "KeypadPinInputRequest",
    "VoiceInputRequest",
    "TamperRequest",
    "UserEnrollRequest",
    "UserResponseSchema",
    "AuditLogEntrySchema",
    "AuditLogResponseSchema",
    "GenericResponse",
]
