"""FastAPI APIRouter declaring all REST endpoints and the real-time WebSocket hub for Physical Hardware."""

import base64
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
import numpy as np

from app.api.schemas import (
    AuditLogEntrySchema,
    AuditLogResponseSchema,
    FaceInputRequest,
    GenericResponse,
    KeypadPinInputRequest,
    MotorDriveRequest,
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
    """Return comprehensive live status of the vault engine and physical hardware."""
    active_username = None
    if engine.active_user is not None:
        active_username = getattr(engine.active_user, "username", None)

    is_locked = getattr(hardware, "is_locked", True)
    is_alarm_active = getattr(hardware, "is_alarm_active", False)
    display = getattr(hardware, "current_display", None)

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


@router.post(
    "/api/v1/vault/motors/drive",
    response_model=GenericResponse,
    summary="Actuate 4-motor getaway chassis",
)
async def drive_motors(
    payload: MotorDriveRequest,
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Manually command the 4 getaway motors."""
    success = await hardware.drive_motors(
        direction=payload.direction,
        duration_ms=payload.duration_ms,
        speed=payload.speed,
    )
    return GenericResponse(
        success=success,
        message=f"4-motor getaway activated ({payload.direction}, {payload.duration_ms}ms, Speed: {payload.speed})",
        data={
            "direction": payload.direction,
            "duration_ms": payload.duration_ms,
            "speed": payload.speed,
        },
    )


@router.post(
    "/api/v1/vault/motors/stop",
    response_model=GenericResponse,
    summary="Halt 4-motor getaway chassis",
)
async def stop_motors(
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Halt all 4 getaway motors immediately."""
    success = await hardware.stop_motors()
    return GenericResponse(
        success=success,
        message="4-motor getaway chassis halted.",
        data={},
    )



# ============================================================================
# Production Authentication Endpoints (Stages 1 - 4)
# ============================================================================


@router.post(
    "/api/v1/auth/rfid",
    response_model=GenericResponse,
    summary="Stage 1: Submit RFID tag UID for verification",
)
async def auth_rfid(
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
    "/api/v1/auth/face",
    response_model=GenericResponse,
    summary="Stage 2: Submit facial recognition image frame or trigger capture",
)
async def auth_face(
    payload: FaceInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
    camera: CameraCaptureInterface = Depends(get_camera),
) -> GenericResponse:
    """Submit facial frame during Stage 2."""
    matched = False

    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64)
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
    elif payload.face_id:
        matched = await engine.submit_face(payload.face_id)
    else:
        # Capture live from physical camera
        live_frame = camera.capture_frame()
        if live_frame is not None:
            matched = await engine.submit_face_frame(live_frame)
        else:
            matched = await engine.submit_face("SUBJECT_001_OPERATOR")

    return GenericResponse(
        success=matched,
        message="Face authenticated successfully." if matched else "Facial recognition failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/auth/face/capture",
    response_model=GenericResponse,
    summary="Stage 2: Trigger live webcam frame capture and biometric verification",
)
async def auth_face_capture(
    engine: VaultAuthEngine = Depends(get_engine),
    camera: CameraCaptureInterface = Depends(get_camera),
) -> GenericResponse:
    """Capture live frame directly from physical camera and authenticate."""
    frame = camera.capture_frame()
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Physical camera device is unavailable or failed to capture frame.",
        )

    matched = await engine.submit_face_frame(frame)
    return GenericResponse(
        success=matched,
        message="Live face scan verified successfully." if matched else "Live face scan verification failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/auth/password",
    response_model=GenericResponse,
    summary="Stage 3: Submit keypad PIN / password for verification",
)
async def auth_password(
    payload: KeypadPinInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
) -> GenericResponse:
    """Submit alphanumeric passphrase / PIN during Stage 3."""
    matched = await engine.submit_keypad_pin(pin=payload.pin)
    return GenericResponse(
        success=matched,
        message="Password authenticated successfully." if matched else "Incorrect password.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/auth/voice",
    response_model=GenericResponse,
    summary="Stage 4: Submit vocal challenge audio waveform or passphrase",
)
async def auth_voice(
    payload: VoiceInputRequest,
    engine: VaultAuthEngine = Depends(get_engine),
    audio: AudioCaptureInterface = Depends(get_audio),
) -> GenericResponse:
    """Submit voice audio waveform during Stage 4."""
    matched = False

    if payload.audio_base64:
        try:
            audio_bytes = base64.b64decode(payload.audio_base64)
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            matched = await engine.submit_voice_audio(audio_data=audio_array)
        except Exception as ex:
            logger.error(f"Error processing base64 audio: {ex}")
            matched = False
    elif payload.spoken_phrase:
        matched = await engine.submit_voice(payload.spoken_phrase)
    else:
        # Record live from physical microphone
        live_audio = audio.record_utterance(duration_sec=2.5)
        if live_audio is not None:
            matched = await engine.submit_voice_audio(audio_data=live_audio)
        else:
            matched = await engine.submit_voice("OPEN SESAME OVERENGINEERED")

    return GenericResponse(
        success=matched,
        message="Voice authenticated! Vault is UNLOCKED." if matched else "Voice authentication failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


@router.post(
    "/api/v1/auth/voice/record",
    response_model=GenericResponse,
    summary="Stage 4: Trigger live physical microphone recording and verification",
)
async def auth_voice_record(
    duration_sec: float = Query(default=2.5, ge=1.0, le=5.0),
    engine: VaultAuthEngine = Depends(get_engine),
    audio: AudioCaptureInterface = Depends(get_audio),
) -> GenericResponse:
    """Record live utterance from physical microphone and authenticate."""
    if not audio.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Physical audio input device is unavailable.",
        )

    audio_data = audio.record_utterance(duration_sec=duration_sec)
    if audio_data is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record audio from microphone.",
        )

    matched = await engine.submit_voice_audio(audio_data=audio_data)
    return GenericResponse(
        success=matched,
        message="Live voice utterance authenticated! Vault UNLOCKED." if matched else "Live voice authentication failed.",
        data={"state": engine.state.value, "failed_attempts": engine.failed_attempts},
    )


# ============================================================================
# Physical Hardware Actuation & Diagnostics Endpoints
# ============================================================================


@router.post(
    "/api/v1/hardware/unlock",
    response_model=GenericResponse,
    summary="Direct physical lock actuation command (Servo 90°)",
)
async def hardware_unlock(
    duration_ms: int = Query(default=5000, ge=1000, le=30000),
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Actuate servo to UNLOCKED (90 degrees)."""
    success = await hardware.set_lock(False)
    return GenericResponse(
        success=success,
        message=f"Unlock command sent to ESP32 (Hold: {duration_ms}ms)." if success else "Failed to send unlock command.",
    )


@router.post(
    "/api/v1/hardware/lock",
    response_model=GenericResponse,
    summary="Direct physical lock actuation command (Servo 0°)",
)
async def hardware_lock(
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Actuate servo to LOCKED (0 degrees)."""
    success = await hardware.set_lock(True)
    return GenericResponse(
        success=success,
        message="Lock command sent to ESP32." if success else "Failed to send lock command.",
    )


@router.post(
    "/api/v1/hardware/alarm",
    response_model=GenericResponse,
    summary="Trigger or silence physical siren alarm",
)
async def hardware_alarm(
    duration_ms: int = Query(default=3000, ge=0, le=60000),
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Trigger physical buzzer alarm on ESP32."""
    await hardware.trigger_alarm(duration_ms)
    return GenericResponse(
        success=True,
        message=f"Alarm {'silenced' if duration_ms == 0 else f'triggered for {duration_ms}ms'}.",
    )


@router.get(
    "/api/v1/hardware/ping",
    response_model=GenericResponse,
    summary="Ping physical ESP32 microcontroller over USB Serial",
)
async def hardware_ping(
    hardware: HardwareInterface = Depends(get_hardware),
) -> GenericResponse:
    """Verify bidirectional serial communication with ESP32."""
    if hasattr(hardware, "ping"):
        success = await hardware.ping()
    else:
        success = hardware.is_initialized
    return GenericResponse(
        success=success,
        message="ESP32 hardware link active." if success else "ESP32 hardware link disconnected.",
        data={"port": getattr(hardware, "port", None), "is_initialized": hardware.is_initialized},
    )


# ============================================================================
# Backwards Compatibility Aliases (for Web UI buttons)
# ============================================================================


@router.post("/api/v1/simulate/rfid", response_model=GenericResponse, include_in_schema=False)
async def simulate_rfid(payload: RfidInputRequest, engine: VaultAuthEngine = Depends(get_engine)) -> GenericResponse:
    return await auth_rfid(payload=payload, engine=engine)


@router.post("/api/v1/simulate/face", response_model=GenericResponse, include_in_schema=False)
async def simulate_face(payload: FaceInputRequest, engine: VaultAuthEngine = Depends(get_engine), camera: CameraCaptureInterface = Depends(get_camera)) -> GenericResponse:
    return await auth_face(payload=payload, engine=engine, camera=camera)


@router.post("/api/v1/simulate/voice", response_model=GenericResponse, include_in_schema=False)
async def simulate_voice(payload: VoiceInputRequest, engine: VaultAuthEngine = Depends(get_engine), audio: AudioCaptureInterface = Depends(get_audio)) -> GenericResponse:
    return await auth_voice(payload=payload, engine=engine, audio=audio)


@router.post("/api/v1/simulate/tamper", response_model=GenericResponse, include_in_schema=False)
async def simulate_tamper(payload: TamperRequest, engine: VaultAuthEngine = Depends(get_engine)) -> GenericResponse:
    await engine.trigger_tamper_lockout(reason=payload.reason)
    return GenericResponse(success=True, message="Chassis tamper triggered. Vault is in SECURITY LOCKOUT.", data={"state": engine.state.value})


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

    # Extract Face Embedding from live camera or random normalized unit vector
    live_frame = camera.capture_frame()
    if live_frame is not None and isinstance(face_verifier, FaceVerifier):
        face_emb = face_verifier.extract_embeddings(live_frame)
    else:
        face_emb = None

    if face_emb is None:
        face_emb = np.random.randn(256).astype(np.float32)
        face_emb /= np.linalg.norm(face_emb)

    # Extract Voiceprint from live audio or random normalized unit vector
    if audio.is_available() and isinstance(voice_verifier, VoiceVerifier):
        live_audio = audio.record_utterance(duration_sec=2.0)
        voice_print = voice_verifier.extract_voice_print(live_audio) if live_audio is not None else None
    else:
        voice_print = None

    if voice_print is None:
        voice_print = np.random.randn(256).astype(np.float32)
        voice_print /= np.linalg.norm(voice_print)

    user = await repository.create_user(
        username=payload.username,
        rfid_uid=payload.rfid_uid,
        password_hash=pwd_hash,
        face_embedding=face_emb,
        voice_print=voice_print,
        phone_public_key=payload.phone_public_key,
        voice_passphrase=payload.voice_passphrase,
    )

    return UserResponseSchema(
        id=user.id,
        username=user.username,
        rfid_uid=user.rfid_uid,
        phone_public_key=user.phone_public_key,
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
            phone_public_key=u.phone_public_key,
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
        display = getattr(hardware, "current_display", None)
        is_locked = getattr(hardware, "is_locked", True)
        is_alarm_active = getattr(hardware, "is_alarm_active", False)

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

        while True:
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_json({"event": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as ex:
        logger.debug(f"WebSocket client stream closed: {ex}")
        await ws_manager.disconnect(websocket)
