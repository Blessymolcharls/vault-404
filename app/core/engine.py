"""Finite State Machine (FSM) Authentication Engine for The Inconvenient Vault.

Enforces strict sequential authentication:
IDLE -> AWAITING_RFID -> AWAITING_FACE -> AWAITING_FACE -> AWAITING_KEYPAD_PIN -> AWAITING_VOICE -> UNLOCKED
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
    VaultState,
)
from app.interfaces.audio import VoiceVerifierInterface
from app.interfaces.hardware import HardwareInterface
from app.interfaces.repository import VaultRepositoryInterface
from app.interfaces.vision import FaceRecognizerInterface

logger = logging.getLogger("vault.core.engine")

# Type alias for state change subscribers (e.g. WebSocket broadcasters)
StateChangeListener = Callable[["StateTransitionEvent"], Awaitable[None]]


class EngineConfig(BaseModel):
    """Configuration parameters for the VaultAuthEngine security lifecycle."""

    model_config = ConfigDict(frozen=True)

    stage_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Maximum idle seconds allowed in an active stage before timeout reset",
    )
    max_failed_attempts: int = Field(
        default=3,
        ge=1,
        description="Maximum consecutive failed verification attempts before triggering LOCKOUT",
    )
    auto_relock_delay_seconds: float = Field(
        default=10.0,
        ge=1.0,
        description="Seconds to remain UNLOCKED before auto-engaging lock and resetting to IDLE",
    )
    admin_override_code: str = Field(
        default="ADMIN_RESET_9999",
        description="Emergency admin override passcode to clear security lockout",
    )
    # Default credential parameters (used when standalone / no database user loaded)
    valid_rfid_uids: Set[str] = Field(
        default_factory=lambda: {"E2806894", "A1B2C3D4"},
        description="Authorized RFID tag UIDs",
    )


    valid_face_ids: Set[str] = Field(
        default_factory=lambda: {"SUBJECT_001_OPERATOR"},
        description="Authorized biometric facial recognition subject IDs",
    )
    min_face_confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum facial recognition similarity confidence",
    )
    valid_passwords: Set[str] = Field(
        default_factory=lambda: {"VaultMasterKey#2026!"},
        description="Authorized alphanumerical passcodes",
    )
    valid_voice_phrases: Set[str] = Field(
        default_factory=lambda: {"OPEN SESAME OVERENGINEERED"},
        description="Authorized vocal challenge passphrases",
    )
    min_voice_confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum voice transcription/acoustic matching confidence",
    )


class StateTransitionEvent(BaseModel):
    """Immutable data record broadcast to external listeners whenever the vault transitions states."""

    model_config = ConfigDict(frozen=True)

    previous_state: VaultState
    current_state: VaultState
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failed_attempts: int = 0
    user_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VaultAuthEngine:
    """Central Finite State Machine (FSM) enforcing 4-stage sequential authentication.

    Coordinates hardware interactions exclusively through the HardwareInterface abstraction
    and records immutable audit trails in the database repository.
    """

    def __init__(
        self,
        hardware: HardwareInterface,
        config: Optional[EngineConfig] = None,
        repository: Optional[VaultRepositoryInterface] = None,
    ) -> None:
        """Initialize the Vault Authentication Engine.

        Args:
            hardware: Abstract HardwareInterface implementation.
            config: Optional custom security configuration.
            repository: Optional persistence repository for database credentials & audit logging.
        """
        self._hardware = hardware
        self._config = config or EngineConfig()
        self._repository = repository
        self._state: VaultState = VaultState.IDLE
        self._failed_attempts: int = 0
        self._total_failed_attempts: int = 0
        self._state_listeners: List[StateChangeListener] = []
        self._transition_history: List[StateTransitionEvent] = []

        # Currently authenticated user context
        self._active_user: Optional[Any] = None
        self._active_user_id: Optional[int] = None
        self._password_hasher = PasswordHasher()

        self._lock = asyncio.Lock()
        self._timeout_task: Optional[asyncio.Task[None]] = None
        self._relock_task: Optional[asyncio.Task[None]] = None

        # Pluggable custom validation hooks
        self._rfid_validator: Optional[Callable[[str], Awaitable[bool]]] = None
        self._fingerprint_validator: Optional[Callable[[int, bool, float], Awaitable[bool]]] = None
        self._face_validator: Optional[Callable[[str, float, bool], Awaitable[bool]]] = None
        self._password_validator: Optional[Callable[[str], Awaitable[bool]]] = None
        self._voice_validator: Optional[Callable[[str, float, bool], Awaitable[bool]]] = None

        # Computer Vision Face Recognizer Subsystem
        self._face_verifier: Optional[FaceRecognizerInterface] = None
        self._enrolled_face_embedding: Optional[np.ndarray] = None
        self._face_threshold: float = 0.85

        # Voice Biometric Subsystem
        self._voice_verifier: Optional[VoiceVerifierInterface] = None
        self._enrolled_voice_print: Optional[np.ndarray] = None
        self._expected_voice_phrase: str = "OPEN SESAME OVERENGINEERED"
        self._voice_threshold: float = 0.85

        # Auto-subscribe to hardware events
        self._hardware.register_event_listener(self._handle_hardware_event)

    # ========================================================================
    # State Inspection Properties
    # ========================================================================

    @property
    def state(self) -> VaultState:
        """Return the current active state of the authentication engine."""
        return self._state

    @property
    def failed_attempts(self) -> int:
        """Return the count of consecutive failed attempts in the current stage."""
        return self._failed_attempts

    @property
    def total_failed_attempts(self) -> int:
        """Return total cumulative failed attempts across all stages."""
        return self._total_failed_attempts

    @property
    def active_user_id(self) -> Optional[int]:
        """Return the user ID currently undergoing authentication."""
        return self._active_user_id

    @property
    def active_user(self) -> Optional[Any]:
        """Return the database User record of the active operator."""
        return self._active_user

    @property
    def config(self) -> EngineConfig:
        """Return the active configuration object."""
        return self._config

    @property
    def repository(self) -> Optional[VaultRepositoryInterface]:
        """Return the attached database repository."""
        return self._repository

    @property
    def transition_history(self) -> List[StateTransitionEvent]:
        """Return a copy of the state transition history."""
        return list(self._transition_history)

    # ========================================================================
    # Pluggable Custom Validator & Subsystem Setters
    # ========================================================================

    def set_rfid_validator(self, validator: Callable[[str], Awaitable[bool]]) -> None:
        """Register a custom asynchronous RFID validator."""
        self._rfid_validator = validator

    def set_fingerprint_validator(
        self, validator: Callable[[int, bool, float], Awaitable[bool]]
    ) -> None:
        """Register a custom asynchronous fingerprint biometric validator."""
        self._fingerprint_validator = validator

    def set_face_validator(
        self, validator: Callable[[str, float, bool], Awaitable[bool]]
    ) -> None:
        """Register a custom asynchronous facial recognition validator."""
        self._face_validator = validator

    def set_face_verifier(
        self,
        verifier: FaceRecognizerInterface,
        enrolled_embedding: np.ndarray,
        threshold: float = 0.85,
    ) -> None:
        """Attach a computer vision FaceRecognizerInterface pipeline with an enrolled template.

        Args:
            verifier: FaceRecognizerInterface implementation.
            enrolled_embedding: Pre-enrolled reference facial embedding vector.
            threshold: Minimum cosine similarity threshold to authenticate.
        """
        self._face_verifier = verifier
        self._enrolled_face_embedding = enrolled_embedding
        self._face_threshold = threshold

    def set_password_validator(self, validator: Callable[[str], Awaitable[bool]]) -> None:
        """Register a custom asynchronous password validator."""
        self._password_validator = validator

    def set_voice_validator(
        self, validator: Callable[[str, float, bool], Awaitable[bool]]
    ) -> None:
        """Register a custom asynchronous vocal authentication validator."""
        self._voice_validator = validator

    def set_voice_verifier(
        self,
        verifier: VoiceVerifierInterface,
        enrolled_voice_print: np.ndarray,
        expected_phrase: str = "OPEN SESAME OVERENGINEERED",
        threshold: float = 0.85,
    ) -> None:
        """Attach an acoustic VoiceVerifierInterface pipeline with an enrolled voiceprint.

        Args:
            verifier: VoiceVerifierInterface implementation.
            enrolled_voice_print: Pre-enrolled reference speaker voiceprint vector.
            expected_phrase: Expected challenge passphrase string.
            threshold: Minimum acoustic similarity threshold to authenticate.
        """
        self._voice_verifier = verifier
        self._enrolled_voice_print = enrolled_voice_print
        self._expected_voice_phrase = expected_phrase
        self._voice_threshold = threshold

    # ========================================================================
    # State Listener Registration
    # ========================================================================

    def register_state_listener(self, listener: StateChangeListener) -> None:
        """Register an async callback invoked on every FSM state change."""
        if listener not in self._state_listeners:
            self._state_listeners.append(listener)

    def unregister_state_listener(self, listener: StateChangeListener) -> bool:
        """Unregister an async state change callback."""
        if listener in self._state_listeners:
            self._state_listeners.remove(listener)
            return True
        return False

    # ========================================================================
    # Core FSM Lifecycle & Transitions
    # ========================================================================

    async def initialize(self) -> bool:
        """Initialize the underlying hardware and set initial IDLE state."""
        hw_ready = await self._hardware.initialize()
        if not hw_ready:
            logger.error("Hardware initialization failed.")
            await self._transition_to(VaultState.ERROR, reason="Hardware initialization failed")
            return False

        await self._transition_to(VaultState.IDLE, reason="System initialized")
        return True

    async def start_authentication(self) -> bool:
        """Initiate authentication sequence from IDLE to AWAITING_RFID."""
        async with self._lock:
            if self._state != VaultState.IDLE:
                logger.warning(
                    f"Cannot start authentication: Vault is in state {self._state.value} (expected IDLE)."
                )
                return False

            self._failed_attempts = 0
            self._active_user = None
            self._active_user_id = None
            await self._transition_to(
                VaultState.AWAITING_RFID, reason="Authentication sequence initiated"
            )
            return True

    async def reset_to_idle(self, reason: str = "Manual reset to IDLE") -> None:
        """Reset the authentication engine safely to IDLE and secure the lock."""
        async with self._lock:
            if self._state == VaultState.LOCKOUT:
                logger.warning("Cannot reset to IDLE from LOCKOUT without admin override.")
                return

            self._failed_attempts = 0
            self._active_user = None
            self._active_user_id = None
            self._cancel_timers()
            await self._hardware.set_lock(True)
            await self._transition_to(VaultState.IDLE, reason=reason)

    async def trigger_tamper_lockout(self, reason: str = "Chassis Tamper Detected") -> None:
        """Force the engine immediately into LOCKOUT upon physical tamper or critical failure."""
        async with self._lock:
            self._cancel_timers()
            if self._repository:
                try:
                    await self._repository.log_audit_event(
                        stage=VaultState.LOCKOUT.value,
                        event_type="TAMPER",
                        user_id=self._active_user_id,
                        metadata={"reason": reason},
                    )
                except Exception as ex:
                    logger.error(f"Failed to log tamper audit record: {ex}")

            await self._transition_to(VaultState.LOCKOUT, reason=reason)

    async def clear_lockout(self, admin_override_key: str) -> bool:
        """Clear security lockout using the administrator override key."""
        async with self._lock:
            if self._state != VaultState.LOCKOUT:
                logger.info(f"Vault is not in LOCKOUT (current state: {self._state.value}).")
                return True

            if admin_override_key != self._config.admin_override_code:
                logger.warning(f"Admin override failed: Invalid passcode '{admin_override_key}'.")
                await self._hardware.trigger_alarm(3000)
                if self._repository:
                    try:
                        await self._repository.log_audit_event(
                            stage=VaultState.LOCKOUT.value,
                            event_type="ADMIN_OVERRIDE_FAILED",
                            user_id=None,
                            metadata={"attempted_key": admin_override_key},
                        )
                    except Exception as ex:
                        logger.error(f"Failed to log admin override failure: {ex}")
                return False

            logger.info("Admin override verified. Clearing security lockout.")
            self._failed_attempts = 0
            self._total_failed_attempts = 0
            self._active_user = None
            self._active_user_id = None
            self._cancel_timers()
            await self._hardware.set_lock(True)

            if self._repository:
                try:
                    await self._repository.log_audit_event(
                        stage=VaultState.IDLE.value,
                        event_type="LOCKOUT_CLEARED",
                        user_id=None,
                        metadata={"reason": "Admin override cleared lockout"},
                    )
                except Exception as ex:
                    logger.error(f"Failed to log lockout clear audit record: {ex}")

            await self._transition_to(VaultState.IDLE, reason="Admin override cleared lockout")
            return True

    # ========================================================================
    # Stage Submission Methods (Strict Sequence Enforcement)
    # ========================================================================

    async def submit_rfid(self, card_uid: str) -> bool:
        """Stage 1: Submit RFID tag UID for verification."""
        async with self._lock:
            if self._state != VaultState.AWAITING_RFID:
                logger.warning(
                    f"[OUT-OF-ORDER] RFID submitted while in state {self._state.value}. Rejected."
                )
                return False

            normalized_uid = card_uid.strip().upper()
            is_valid = False
            matched_user = None

            # 1. Check Database Repository if configured
            if self._repository:
                try:
                    matched_user = await self._repository.get_user_by_rfid(normalized_uid)
                    if matched_user:
                        is_valid = True
                        self._active_user = matched_user
                        self._active_user_id = matched_user.id
                        # Auto-load user face and voice biometric profiles
                        if self._face_verifier:
                            self._enrolled_face_embedding = matched_user.get_face_embedding()
                        if self._voice_verifier:
                            self._enrolled_voice_print = matched_user.get_voice_print()
                            self._expected_voice_phrase = matched_user.voice_passphrase
                except Exception as ex:
                    logger.error(f"Database error during RFID verification: {ex}")
                    is_valid = False

            # 2. Check Custom Validator Hook
            if not is_valid and self._rfid_validator:
                try:
                    is_valid = await self._rfid_validator(normalized_uid)
                except Exception as ex:
                    logger.error(f"Error in custom RFID validator: {ex}")
                    is_valid = False

            # 3. Fallback to Configured Allowed RFID UIDs
            if not is_valid and not self._repository and not self._rfid_validator:
                is_valid = normalized_uid in self._config.valid_rfid_uids

            if is_valid:
                logger.info(f"[STAGE 1 PASS] RFID UID '{normalized_uid}' authenticated.")
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.AWAITING_FACE,
                    reason=f"RFID authenticated ({normalized_uid})",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_RFID,
                    detail=f"Invalid RFID UID '{normalized_uid}'",
                )
                return False


    async def submit_face(
        self,
        face_id: str,
        confidence: float = 0.95,
        is_live: bool = True,
    ) -> bool:
        """Stage 2: Submit facial recognition detection result by identifier."""
        async with self._lock:
            if self._state != VaultState.AWAITING_FACE:
                logger.warning(
                    f"[OUT-OF-ORDER] Face recognition submitted while in state {self._state.value}. Rejected."
                )
                return False

            is_valid = False
            if self._face_validator:
                try:
                    is_valid = await self._face_validator(face_id, confidence, is_live)
                except Exception as ex:
                    logger.error(f"Error in custom face validator: {ex}")
                    is_valid = False
            else:
                is_valid = (
                    is_live
                    and face_id in self._config.valid_face_ids
                    and confidence >= self._config.min_face_confidence
                )

            if is_valid:
                logger.info(
                    f"[STAGE 2 PASS] Face ID '{face_id}' authenticated (Confidence: {confidence:.2f}, Live: {is_live})."
                )
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.AWAITING_KEYPAD_PIN,
                    reason=f"Face authenticated ({face_id})",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_FACE,
                    detail=f"Face failed (ID: {face_id}, Conf: {confidence:.2f}, Live: {is_live})",
                )
                return False

    async def submit_face_frame(self, frame: np.ndarray) -> bool:
        """Stage 2 (Vision Pipeline): Submit a captured image frame for biometric verification.

        Args:
            frame: Image array of shape (H, W, 3).

        Returns:
            bool: True if facial recognition & liveness matched successfully; False otherwise.
        """
        async with self._lock:
            if self._state != VaultState.AWAITING_FACE:
                logger.warning(
                    f"[OUT-OF-ORDER] Face frame submitted while in state {self._state.value}. Rejected."
                )
                return False

            if self._face_verifier is None or self._enrolled_face_embedding is None:
                logger.warning(
                    "Face verifier or enrolled template not configured. Falling back to default identifier match."
                )
                return False

            # Run face verifier
            matched = self._face_verifier.verify_face(
                frame,
                self._enrolled_face_embedding,
                threshold=self._face_threshold,
            )

            if matched:
                logger.info("[STAGE 2 PASS] Live facial frame authenticated successfully.")
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.AWAITING_KEYPAD_PIN,
                    reason="Live facial frame authenticated",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_FACE,
                    detail="Facial recognition verification or liveness check failed",
                )
                return False

    async def submit_keypad_pin(self, pin: str = "", hardware_verified: bool = False) -> bool:
        """Stage 3: Submit keypad PIN for verification."""
        async with self._lock:
            if self._state != VaultState.AWAITING_KEYPAD_PIN:
                logger.warning(
                    f"[OUT-OF-ORDER] Keypad PIN submitted while in state {self._state.value}. Rejected."
                )
                return False

            is_valid = False

            if hardware_verified:
                is_valid = True
            elif self._active_user is not None:
                try:
                    is_valid = self._password_hasher.verify(
                        self._active_user.password_hash, pin
                    )
                except VerifyMismatchError:
                    is_valid = False
                except Exception as ex:
                    logger.error(f"Error during Argon2 PIN verification: {ex}")
                    is_valid = False
            elif self._password_validator:
                try:
                    is_valid = await self._password_validator(pin)
                except Exception as ex:
                    logger.error(f"Error in custom password validator: {ex}")
                    is_valid = False
            else:
                is_valid = pin in self._config.valid_passwords

            if is_valid:
                logger.info("[STAGE 3 PASS] Keypad PIN authenticated successfully.")
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

    async def submit_voice(
        self,
        phrase: str,
        confidence: float = 0.95,
        voice_matched: bool = True,
    ) -> bool:
        """Stage 4: Submit voice recognition challenge by phrase for final unlock verification."""
        async with self._lock:
            if self._state != VaultState.AWAITING_VOICE:
                logger.warning(
                    f"[OUT-OF-ORDER] Voice submitted while in state {self._state.value}. Rejected."
                )
                return False

            is_valid = False
            normalized_phrase = phrase.strip().upper()

            if self._active_user is not None:
                is_valid = (
                    voice_matched
                    and normalized_phrase == self._active_user.voice_passphrase
                    and confidence >= self._config.min_voice_confidence
                )
            elif self._voice_validator:
                try:
                    is_valid = await self._voice_validator(
                        normalized_phrase, confidence, voice_matched
                    )
                except Exception as ex:
                    logger.error(f"Error in custom voice validator: {ex}")
                    is_valid = False
            else:
                is_valid = (
                    voice_matched
                    and normalized_phrase in self._config.valid_voice_phrases
                    and confidence >= self._config.min_voice_confidence
                )

            if is_valid:
                logger.info(
                    f"[STAGE 4 PASS] Voice passphrase '{normalized_phrase}' authenticated."
                )
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.UNLOCKED,
                    reason=f"Voice authenticated ({normalized_phrase})",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_VOICE,
                    detail=f"Voice authentication failed (Phrase: '{phrase}', Conf: {confidence:.2f})",
                )
                return False

    async def submit_voice_audio(
        self,
        audio_data: np.ndarray,
        spoken_phrase: Optional[str] = None,
        sample_rate: int = 16000,
    ) -> bool:
        """Stage 4 (Voice Biometrics): Submit a recorded audio waveform for 2-factor voice authentication."""
        async with self._lock:
            if self._state != VaultState.AWAITING_VOICE:
                logger.warning(
                    f"[OUT-OF-ORDER] Voice audio submitted while in state {self._state.value}. Rejected."
                )
                return False

            if self._voice_verifier is None or self._enrolled_voice_print is None:
                logger.warning(
                    "Voice verifier or enrolled voiceprint not configured. Falling back to phrase check."
                )
                if spoken_phrase:
                    return await self.submit_voice(spoken_phrase)
                return False

            phrase_to_check = spoken_phrase or self._expected_voice_phrase
            matched = self._voice_verifier.verify_utterance(
                audio_data=audio_data,
                enrolled_voice_print=self._enrolled_voice_print,
                expected_phrase=self._expected_voice_phrase,
                spoken_phrase=phrase_to_check,
                threshold=self._voice_threshold,
                sample_rate=sample_rate,
            )

            if matched:
                logger.info("🎉 [STAGE 4 PASS] Live voice biometric and passphrase authenticated!")
                self._failed_attempts = 0
                await self._transition_to(
                    VaultState.UNLOCKED,
                    reason=f"Voice biometric authenticated ({self._expected_voice_phrase})",
                )
                return True
            else:
                await self._handle_failed_attempt(
                    stage=VaultState.AWAITING_VOICE,
                    detail="Voice biometric voiceprint mismatch or incorrect challenge phrase",
                )
                return False

    # ========================================================================
    # Internal Hardware Event Listener & Dispatch
    # ========================================================================

    async def _handle_hardware_event(self, event: HardwareEvent) -> None:
        """Handle hardware events received asynchronously from the HardwareInterface."""
        logger.debug(f"VaultAuthEngine received hardware event: {event.event_type.value}")

        if event.event_type == HardwareEventType.TAMPER_TRIGGERED:
            logger.critical(f"TAMPER DETECTED via hardware bus: {event.payload}")
            await self.trigger_tamper_lockout(
                reason=f"Tamper Sensor Breach: {event.payload.get('description', 'Unknown')}"
            )

        elif event.event_type == HardwareEventType.RFID_SCANNED:
            card_uid = event.payload.get("card_uid")
            if card_uid:
                if self._state == VaultState.IDLE:
                    await self.start_authentication()
                if self._state == VaultState.AWAITING_RFID:
                    await self.submit_rfid(str(card_uid))

        elif event.event_type == HardwareEventType.KEYPAD_PIN_RESULT:
            if self._state == VaultState.AWAITING_KEYPAD_PIN:
                result = event.payload.get("result", "")
                if result == "KEYPAD_PIN_VERIFIED":
                    await self.submit_keypad_pin(hardware_verified=True)
                else:
                    await self.submit_keypad_pin(pin=result)

        elif event.event_type == HardwareEventType.HARDWARE_ERROR:
            logger.error(f"Hardware error reported: {event.payload}")

    # ========================================================================
    # Failure & Lockout Handling
    # ========================================================================

    async def _handle_failed_attempt(self, stage: VaultState, detail: str) -> None:
        """Increment failure counter, log audit record, and transition to LOCKOUT if threshold exceeded."""
        self._failed_attempts += 1
        self._total_failed_attempts += 1
        remaining = self._config.max_failed_attempts - self._failed_attempts

        logger.warning(
            f"[ATTEMPT FAILED] Stage: {stage.value} | Details: {detail} | "
            f"Failed: {self._failed_attempts}/{self._config.max_failed_attempts}"
        )

        if self._repository:
            try:
                await self._repository.log_audit_event(
                    stage=stage.value,
                    event_type="AUTH_FAILURE",
                    user_id=self._active_user_id,
                    metadata={
                        "detail": detail,
                        "failed_attempts": self._failed_attempts,
                        "remaining_attempts": max(0, remaining),
                    },
                )
            except Exception as ex:
                logger.error(f"Failed to record audit event for failed attempt: {ex}")

        if self._failed_attempts >= self._config.max_failed_attempts:
            logger.critical(
                f"Maximum failed attempts ({self._config.max_failed_attempts}) exceeded! Initiating LOCKOUT."
            )
            self._cancel_timers()
            await self._transition_to(
                VaultState.LOCKOUT,
                reason=f"Exceeded max failed attempts in {stage.value} ({detail})",
            )
        else:
            await self._hardware.trigger_alarm(2000)
            # Update display with warning buzzer and remaining attempts
            await self._hardware.set_display(
                DisplayStatus(
                    line1="ACCESS DENIED",
                    line2=f"RETRY ({remaining} LEFT)",
                    led_color=LedColor.RED,
                    buzzer=True,
                    duration_ms=1500,
                )
            )

    # ========================================================================
    # Transition Manager & Hardware Actuation
    # ========================================================================

    async def _transition_to(self, new_state: VaultState, reason: str) -> None:
        """Perform state transition, update hardware indicators, record audit logs, and manage timeouts."""
        previous_state = self._state
        self._state = new_state
        self._cancel_timers()

        logger.info(
            f"[STATE TRANSITION] {previous_state.value} -> {new_state.value} | Reason: {reason}"
        )

        # 1. Record Append-Only Hash-Chained Audit Record in Database
        if self._repository:
            try:
                event_classification = "STATE_TRANSITION"
                if new_state == VaultState.UNLOCKED:
                    event_classification = "AUTH_SUCCESS"
                elif new_state == VaultState.LOCKOUT:
                    event_classification = "LOCKOUT"

                await self._repository.log_audit_event(
                    stage=new_state.value,
                    event_type=event_classification,
                    user_id=self._active_user_id,
                    metadata={
                        "previous_state": previous_state.value,
                        "current_state": new_state.value,
                        "reason": reason,
                        "failed_attempts": self._failed_attempts,
                    },
                )
            except Exception as ex:
                logger.error(f"Failed to write state transition audit log: {ex}")

        # 2. Coordinate Hardware Actuation & Display Updates
        if new_state == VaultState.IDLE:
            await self._hardware.set_lock(True)
            await self._hardware.trigger_alarm(0)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="VAULT 404 READY",
                    line2="START AUTHENTICATION",
                    led_color=LedColor.BLUE,
                    buzzer=False,
                )
            )

        elif new_state == VaultState.AWAITING_RFID:
            await self._hardware.set_lock(True)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="[1/4] SCAN RFID",
                    line2="HOLD CARD NEAR",
                    led_color=LedColor.CYAN,
                    buzzer=True,
                    duration_ms=500,
                )
            )
            self._schedule_stage_timeout(self._config.stage_timeout_seconds)

        elif new_state == VaultState.AWAITING_FACE:
            await self._hardware.set_display(
                DisplayStatus(
                    line1="[2/4] FACE SCAN",
                    line2="LOOK AT CAMERA",
                    led_color=LedColor.CYAN,
                    buzzer=True,
                    duration_ms=500,
                )
            )
            self._schedule_stage_timeout(self._config.stage_timeout_seconds)

        elif new_state == VaultState.AWAITING_KEYPAD_PIN:
            hash_str = "TODO_GET_HASH"
            if self._active_user:
                hash_str = self._active_user.password_hash
            await self._hardware.enable_keypad(hash_str)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="[3/4] ENTER PIN",
                    line2="KEYPAD INPUT",
                    led_color=LedColor.CYAN,
                    buzzer=True,
                    duration_ms=500,
                )
            )
            self._schedule_stage_timeout(self._config.stage_timeout_seconds)

        elif new_state == VaultState.AWAITING_VOICE:
            await self._hardware.disable_keypad()
            await self._hardware.set_display(
                DisplayStatus(
                    line1="[4/4] VOICE PHRASE",
                    line2="SPEAK PASSPHRASE",
                    led_color=LedColor.CYAN,
                    buzzer=True,
                    duration_ms=500,
                )
            )
            self._schedule_stage_timeout(self._config.stage_timeout_seconds)

        elif new_state == VaultState.UNLOCKED:
            logger.info("🎉 All 4 stages passed! Actuating solenoid to UNLOCKED state.")
            await self._hardware.set_lock(False)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="VAULT UNLOCKED",
                    line2="ACCESS GRANTED",
                    led_color=LedColor.GREEN,
                    buzzer=True,
                    duration_ms=3000,
                )
            )
            self._schedule_auto_relock(self._config.auto_relock_delay_seconds)

        elif new_state == VaultState.LOCKOUT:
            logger.critical("🚨 Security lockout active! Actuating lock and firing alarm siren.")
            await self._hardware.set_lock(True)
            await self._hardware.trigger_alarm(5000)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="SECURITY LOCKOUT",
                    line2="ADMIN OVERRIDE REQ",
                    led_color=LedColor.RED,
                    buzzer=True,
                    duration_ms=5000,
                )
            )

        elif new_state == VaultState.ERROR:
            logger.error("Vault entered ERROR state.")
            await self._hardware.set_lock(True)
            await self._hardware.set_display(
                DisplayStatus(
                    line1="SYSTEM ERROR",
                    line2="SERVICE REQUIRED",
                    led_color=LedColor.RED,
                    buzzer=True,
                )
            )

        # Broadcast state change event to subscribers
        event = StateTransitionEvent(
            previous_state=previous_state,
            current_state=new_state,
            reason=reason,
            failed_attempts=self._failed_attempts,
            user_id=self._active_user_id,
        )
        self._transition_history.append(event)
        await self._broadcast_state_change(event)

    # ========================================================================
    # Timer & Timeout Management
    # ========================================================================

    def _cancel_timers(self) -> None:
        """Cancel any active stage timeout or relock background tasks."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

        if self._relock_task and not self._relock_task.done():
            self._relock_task.cancel()
            self._relock_task = None

    def _schedule_stage_timeout(self, seconds: float) -> None:
        """Schedule an asynchronous cancellable timeout for the current active stage."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        current_stage = self._state

        async def _timeout_coro() -> None:
            try:
                await asyncio.sleep(seconds)
                async with self._lock:
                    if self._state == current_stage:
                        logger.warning(
                            f"[TIMEOUT] Stage {current_stage.value} timed out after {seconds}s. Resetting to IDLE."
                        )
                        self._failed_attempts = 0
                        await self._transition_to(
                            VaultState.IDLE,
                            reason=f"Stage {current_stage.value} timed out after {seconds}s",
                        )
            except asyncio.CancelledError:
                pass

        self._timeout_task = asyncio.create_task(_timeout_coro())

    def _schedule_auto_relock(self, seconds: float) -> None:
        """Schedule automatic re-locking after the vault has been unlocked."""
        if self._relock_task and not self._relock_task.done():
            self._relock_task.cancel()

        async def _relock_coro() -> None:
            try:
                await asyncio.sleep(seconds)
                async with self._lock:
                    if self._state == VaultState.UNLOCKED:
                        logger.info(
                            f"[AUTO-RELOCK] Relocking vault after {seconds}s in UNLOCKED state."
                        )
                        await self._transition_to(
                            VaultState.IDLE,
                            reason=f"Auto-relock engaged after {seconds}s",
                        )
            except asyncio.CancelledError:
                pass

        self._relock_task = asyncio.create_task(_relock_coro())

    # ========================================================================
    # State Change Broadcasting
    # ========================================================================

    async def _broadcast_state_change(self, event: StateTransitionEvent) -> None:
        """Broadcast state transition event to all registered external listeners."""
        if not self._state_listeners:
            return

        tasks = [listener(event) for listener in self._state_listeners]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for listener, result in zip(self._state_listeners, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Error in state change listener {getattr(listener, '__qualname__', str(listener))}: {result}",
                    exc_info=result,
                )
