"""FastAPI APIRouter declaring all REST endpoints and the real-time WebSocket hub."""

import base64
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
import numpy as np

from app.adapters.mock_audio import MockAudioAdapter
from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.api.schemas import (
    AuditLogEntrySchema,
    AuditLogResponseSchema,
    FaceInputRequest,
    FingerprintInputRequest,
    GenericResponse,
    PasswordInputRequest,
    ResetVaultRequest,
    RfidInputRequest,
    TamperRequest,
    UserEnrollRequest,
    UserResponseSchema,
    VaultStatusResponse,
    VoiceInputRequest,
)
from app.api.websocket_manager import WebSocketManager
from app.audio.voice_verifier import VoiceVerifier
from app.core.engine import VaultAuthEngine
from app.core.types import VaultState
from app.interfaces.audio import AudioCaptureInterface, VoiceVerifierInterface
from app.interfaces.hardware import HardwareInterface
from app.interfaces.repository import VaultRepositoryInterface
from app.interfaces.vision import CameraCaptureInterface, FaceRecognizerInterface
from app.vision.face_verifier import FaceVerifier

logger = logging.getLogger("vault.api.routes")
router = APIRouter()


# ============================================================================
# Dependency Injection Resolvers
# ============================================================================


def get_engine(request: Request) -> VaultAuthEngine:
    """Retrieve singleton VaultAuthEngine instance from app state."""
    return request.app.state.engine


def get_hardware(request: Request) -> HardwareInterface:
    """Retrieve singleton HardwareInterface instance from app state."""
    return request.app.state.hardware


def get_repository(request: Request) -> VaultRepositoryInterface:
    """Retrieve singleton VaultRepositoryInterface instance from app state."""
    return request.app.state.repository


def get_ws_manager(request: Request) -> WebSocketManager:
    """Retrieve singleton WebSocketManager instance from app state."""
    return request.app.state.ws_manager


def get_camera(request: Request) -> CameraCaptureInterface:
    """Retrieve singleton CameraCaptureInterface instance from app state."""
    return request.app.state.camera


def get_audio(request: Request) -> AudioCaptureInterface:
    """Retrieve singleton AudioCaptureInterface instance from app state."""
    return request.app.state.audio


def get_face_verifier(request: Request) -> FaceRecognizerInterface:
    """Retrieve singleton FaceRecognizerInterface instance from app state."""
    return request.app.state.face_verifier


def get_voice_verifier(request: Request) -> VoiceVerifierInterface:
    """Retrieve singleton VoiceVerifierInterface instance from app state."""
    return request.app.state.voice_verifier


# ============================================================================
# State & Lifecycle Endpoints
# ============================================================================


@router.get(
    "/api/v1/vault/status",
    response_model=VaultStatusResponse,
    summary="Get current vault state, display, and peripheral diagnostics",
)
async def get_vault_status(
    engine: VaultAuthEngine = Depends(get_engine),
    hardware: HardwareInterface = Depends(get_hardware),
) -> VaultStatusResponse:
    """Return comprehensive live status of the vault engine and hardware."""
    active_username = None
    if engine.active_user is not None:
        active_username = getattr(engine.active_user, "username", None)

    # In mock hardware, inspect active status
    is_locked = True
    is_alarm_active = False
    display = engine._hardware._current_display if hasattr(engine._hardware, "_current_display") else None

    if isinstance(hardware, MockHardwareAdapter):
        is_locked = hardware.is_locked
        is_alarm_active = hardware.is_alarm_active
        display = hardware.current_display

    return VaultStatusResponse(
        state=engine.state,
        is_locked=is_locked,
        is_alarm_active=is_alarm_active,
        failed_attempts=engine.failed_attempts,
        max_failed_attempts=engine.config.max_failed_attempts,
        active_user_id=engine.active_user_id,
        active_username=active_username,
        display=display,
        timestamp=datetime.now(timezone.utc),
    )


@router.post(
    "/api/v1/vault/start",
    response_model=GenericResponse,
    summary="Initiate sequential authentication (IDLE -> AWAITING_RFID)",
)
async def start_authentication(
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Start the sequential authentication chain from IDLE state."""
    success = await engine.start_authentication()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot initiate authentication from current state: {engine.state.value}",
        )
    return GenericResponse(
        success=True,
        message="Authentication chain initiated. Awaiting Stage 1 RFID scan.",
        data={"state": engine.state.value},
    )


@router.post(
    "/api/v1/vault/reset",
    response_model=GenericResponse,
    summary="Safely reset the vault to IDLE or clear a security lockout",
)
async def reset_vault(
    payload: ResetVaultRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Reset vault to IDLE or clear active LOCKOUT with admin override key."""
    if engine.state == VaultState.LOCKOUT:
        if not payload.admin_override_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vault is in LOCKOUT. Admin override key is required.",
            )
        cleared = await engine.clear_lockout(payload.admin_override_key)
        if not cleared:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin override key. Lockout remains active.",
            )
        return GenericResponse(
            success=True,
            message="Security lockout cleared by admin override. Vault reset to IDLE.",
            data={"state": engine.state.value},
        )

    await engine.reset_to_idle(reason="Manual reset requested via API")
    return GenericResponse(
        success=True,
        message="Vault safely reset to IDLE state.",
        data={"state": engine.state.value},
    )


# ============================================================================
# Sequential Input Ingestion & Simulation Endpoints
# ============================================================================


@router.post(
    "/api/v1/simulate/rfid",
    response_model=GenericResponse,
    summary="Stage 1: Submit RFID tag UID for verification",
)
async def simulate_rfid(
    payload: RfidInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Submit an RFID UID payload during Stage 1."""
    if engine.state == VaultState.IDLE:
        await engine.start_authentication()

    matched = await engine.submit_rfid(payload.card_uid)
    return GenericResponse(
        success=matched,
        message="RFID authenticated successfully." if matched else "RFID rejected or unauthorized.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/simulate/fingerprint",
    response_model=GenericResponse,
    summary="Stage 2: Submit fingerprint biometric scan result",
)
async def simulate_fingerprint(
    payload: FingerprintInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Submit fingerprint scan result during Stage 2."""
    matched = await engine.submit_fingerprint(
        finger_id=payload.finger_id,
        matched=payload.matched,
        confidence=payload.confidence,
    )
    return GenericResponse(
        success=matched,
        message="Fingerprint authenticated successfully." if matched else "Fingerprint biometric failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/simulate/face",
    response_model=GenericResponse,
    summary="Stage 3: Submit facial recognition image frame or synthetic biometric seed",
)
async def simulate_face(
    payload: FaceInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
    camera: CameraCaptureInterface = Depends(get_camera),
) -> GenericResponse:
    """Submit facial frame during Stage 3."""
    matched = False

    # 1. Base64 Image provided
    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64)
            # Decode JPEG/PNG using OpenCV or NumPy
            import cv2

            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                matched = await engine.submit_face_frame(frame)
            else:
                raise ValueError("Could not decode image from base64")
        except Exception as ex:
            logger.error(f"Error processing base64 image: {ex}")
            matched = False

    # 2. Synthetic Subject Seed provided
    elif payload.subject_seed is not None:
        if isinstance(camera, MockCameraAdapter):
            frame = camera.generate_synthetic_face_frame(
                subject_seed=payload.subject_seed, noise_level=payload.noise_level
            )
            matched = await engine.submit_face_frame(frame)
        else:
            # Fallback to identifier match
            matched = await engine.submit_face(f"SUBJECT_{payload.subject_seed}")

    # 3. Fallback to face_id identifier
    else:
        matched = await engine.submit_face(payload.face_id or "SUBJECT_001_OPERATOR")

    return GenericResponse(
        success=matched,
        message="Face authenticated successfully." if matched else "Facial recognition failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/auth/password",
    response_model=GenericResponse,
    summary="Stage 4: Submit password secret key for verification",
)
async def auth_password(
    payload: PasswordInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Submit alphanumeric passphrase during Stage 4."""
    matched = await engine.submit_password(payload.password)
    return GenericResponse(
        success=matched,
        message="Password authenticated successfully." if matched else "Incorrect password.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/simulate/voice",
    response_model=GenericResponse,
    summary="Stage 5: Submit vocal challenge utterance or synthetic speaker seed",
)
async def simulate_voice(
    payload: VoiceInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
    audio: AudioCaptureInterface = Depends(get_audio),
) -> GenericResponse:
    """Submit voice audio waveform during Stage 5."""
    matched = False

    if payload.speaker_seed is not None:
        phrase = payload.spoken_phrase or "OPEN SESAME OVERENGINEERED"
        if isinstance(audio, MockAudioAdapter):
            utterance = audio.generate_synthetic_utterance(
                speaker_seed=payload.speaker_seed,
                phrase=phrase,
                noise_level=payload.noise_level,
            )
            matched = await engine.submit_voice_audio(utterance, spoken_phrase=phrase)
        else:
            matched = await engine.submit_voice(phrase)
    else:
        matched = await engine.submit_voice(payload.spoken_phrase or "OPEN SESAME OVERENGINEERED")

    return GenericResponse(
        success=matched,
        message="Voice authenticated! Vault is UNLOCKED." if matched else "Voice authentication failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/simulate/tamper",
    response_model=GenericResponse,
    summary="Simulate physical tamper sensor trip to trigger security lockdown",
)
async def simulate_tamper(
    payload: TamperRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Simulate physical enclosure breach, immediately entering LOCKOUT."""
    await engine.trigger_tamper_lockout(reason=payload.reason)
    return GenericResponse(
        success=True,
        message="Chassis tamper triggered. Vault is in SECURITY LOCKOUT.",
        data={"state": engine.state.value},
    )


# ============================================================================
# Audit Log & Cryptographic Verification Endpoints
# ============================================================================


@router.get(
    "/api/v1/audit/logs",
    response_model=AuditLogResponseSchema,
    summary="Query paginated audit logs with cryptographic hash-chain verification",
)
async def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: VaultRepositoryInterface = Depends(get_repository),
) -> AuditLogResponseSchema:
    """Retrieve paginated audit log entries and verify whole-chain integrity."""
    logs = await repository.get_audit_logs(limit=limit, offset=offset)
    is_valid, error = await repository.verify_audit_trail_integrity()

    entry_schemas = [
        AuditLogEntrySchema(
            id=log.id,
            timestamp=log.timestamp,
            user_id=log.user_id,
            stage=log.stage,
            event_type=log.event_type,
            metadata=log.get_metadata() if hasattr(log, "get_metadata") else {},
            previous_hash=log.previous_hash,
            entry_hash=log.entry_hash,
        )
        for log in logs
    ]

    return AuditLogResponseSchema(
        total_records=len(entry_schemas),
        is_chain_valid=is_valid,
        integrity_error=error,
        logs=entry_schemas,
    )


# ============================================================================
# User Enrollment Endpoints
# ============================================================================


@router.post(
    "/api/v1/users/enroll",
    response_model=UserResponseSchema,
    summary="Enroll a new vault operator with multi-modal biometric credentials",
)
async def enroll_user(
    payload: UserEnrollRequest,
    repository: VaultRepositoryInterface = Depends(get_repository),
    camera: CameraCaptureInterface = Depends(get_camera),
    audio: AudioCaptureInterface = Depends(get_audio),
    face_verifier: FaceRecognizerInterface = Depends(get_face_verifier),
    voice_verifier: VoiceVerifierInterface = Depends(get_voice_verifier),
) -> UserResponseSchema:
    """Enroll a new operator with Argon2id password hash, facial embeddings, and voiceprint."""
    ph = PasswordHasher()
    pwd_hash = ph.hash(payload.password)

    # Synthesize Face Embedding
    if isinstance(camera, MockCameraAdapter) and isinstance(face_verifier, FaceVerifier):
        face_frame = camera.generate_synthetic_face_frame(subject_seed=payload.face_subject_seed)
        face_emb = face_verifier.extract_embeddings(face_frame)
    else:
        face_emb = np.random.randn(256).astype(np.float32)
        face_emb /= np.linalg.norm(face_emb)

    # Synthesize Voiceprint
    if isinstance(audio, MockAudioAdapter) and isinstance(voice_verifier, VoiceVerifier):
        utterance = audio.generate_synthetic_utterance(speaker_seed=payload.voice_speaker_seed)
        voice_print = voice_verifier.extract_voice_print(utterance)
    else:
        voice_print = np.random.randn(256).astype(np.float32)
        voice_print /= np.linalg.norm(voice_print)

    user = await repository.create_user(
        username=payload.username,
        rfid_uid=payload.rfid_uid,
        fingerprint_id=payload.fingerprint_id,
        password_hash=pwd_hash,
        face_embedding=face_emb,
        voice_print=voice_print,
        voice_passphrase=payload.voice_passphrase,
    )

    return UserResponseSchema(
        id=user.id,
        username=user.username,
        rfid_uid=user.rfid_uid,
        fingerprint_id=user.fingerprint_id,
        voice_passphrase=user.voice_passphrase,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get(
    "/api/v1/users",
    response_model=List[UserResponseSchema],
    summary="List all enrolled vault operators",
)
async def list_users(
    repository: VaultRepositoryInterface = Depends(get_repository),
) -> List[UserResponseSchema]:
    """Retrieve all enrolled operators."""
    users = await repository.list_users()
    return [
        UserResponseSchema(
            id=u.id,
            username=u.username,
            rfid_uid=u.rfid_uid,
            fingerprint_id=u.fingerprint_id,
            voice_passphrase=u.voice_passphrase,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


# ============================================================================
# Real-Time WebSocket Telemetry Route
# ============================================================================


@router.websocket("/ws/vault")
async def websocket_vault_stream(
    websocket: WebSocket,
) -> None:
    """Dedicated bidirectional WebSocket connection for live telemetry stream."""
    ws_manager: WebSocketManager = websocket.app.state.ws_manager
    engine: VaultAuthEngine = websocket.app.state.engine
    hardware: HardwareInterface = websocket.app.state.hardware

    await ws_manager.connect(websocket)
    try:
        # Send initial status payload upon connect
        display = hardware.current_display if isinstance(hardware, MockHardwareAdapter) else None
        is_locked = hardware.is_locked if isinstance(hardware, MockHardwareAdapter) else True
        is_alarm_active = hardware.is_alarm_active if isinstance(hardware, MockHardwareAdapter) else False

        initial_status = {
            "event": "INITIAL_STATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "state": engine.state.value,
                "is_locked": is_locked,
                "is_alarm_active": is_alarm_active,
                "failed_attempts": engine.failed_attempts,
                "max_failed_attempts": engine.config.max_failed_attempts,
                "display": display.model_dump() if display else None,
            },
        }
        await websocket.send_json(initial_status)

        # Keep socket open and process any incoming ping/pong or client messages
        while True:
            data = await websocket.receive_text()
            # Respond to ping messages
            if data.strip().lower() == "ping":
                await websocket.send_json({"event": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as ex:
        logger.debug(f"WebSocket client stream closed: {ex}")
        await ws_manager.disconnect(websocket)
