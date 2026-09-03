"""Automated test suite for Step 7 of The Inconvenient Vault.

Validates:
1. Multi-modal User enrollment, Argon2id hashing, and retrieval by RFID/UID.
2. Immutable, append-only, cryptographic SHA-256 hash-chained audit logging.
3. Tamper-evidence detection (asserting hash chain failure upon data corruption).
4. VaultAuthEngine end-to-end integration with database user profile and automatic audit trail.
"""

from typing import AsyncGenerator
from argon2 import PasswordHasher
import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.mock_audio import MockAudioAdapter
from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.audio.voice_verifier import VoiceVerifier
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import VaultState
from app.database.models import AuditLog, Base, User
from app.database.repository import SqliteVaultRepository
from app.database.session import init_db
from app.vision.face_verifier import FaceVerifier


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Fixture providing an in-memory SQLite database sessionmaker."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    yield session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def repository(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> SqliteVaultRepository:
    """Fixture providing an initialized SqliteVaultRepository."""
    return SqliteVaultRepository(session_factory=db_session_factory)


# ============================================================================
# 1. User Enrollment & Retrieval Tests
# ============================================================================


@pytest.mark.asyncio
async def test_user_enrollment_and_retrieval(repository: SqliteVaultRepository):
    """Verify user enrollment with Argon2id password, face embedding, and voice print."""
    ph = PasswordHasher()
    pwd_hash = ph.hash("VaultMasterKey#2026!")

    face_emb = np.random.randn(256).astype(np.float32)
    face_emb /= np.linalg.norm(face_emb)

    voice_print = np.random.randn(256).astype(np.float32)
    voice_print /= np.linalg.norm(voice_print)

    user = await repository.create_user(
        username="OPERATOR_001",
        rfid_uid="E2806894",
        fingerprint_id=1,
        password_hash=pwd_hash,
        face_embedding=face_emb,
        voice_print=voice_print,
        voice_passphrase="OPEN SESAME OVERENGINEERED",
    )

    assert user.id is not None
    assert user.username == "OPERATOR_001"
    assert user.rfid_uid == "E2806894"
    assert user.fingerprint_id == 1
    assert user.is_active is True

    # Retrieve by RFID
    found_user = await repository.get_user_by_rfid("E2806894")
    assert found_user is not None
    assert found_user.id == user.id

    # Verify deserialized biometric embeddings
    loaded_face = found_user.get_face_embedding()
    assert np.allclose(loaded_face, face_emb, atol=1e-5)

    loaded_voice = found_user.get_voice_print()
    assert np.allclose(loaded_voice, voice_print, atol=1e-5)

    # Retrieve by ID
    user_by_id = await repository.get_user_by_id(user.id)
    assert user_by_id is not None
    assert user_by_id.username == "OPERATOR_001"


# ============================================================================
# 2. Cryptographic Hash-Chained Audit Trail Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hash_chained_audit_trail_creation(repository: SqliteVaultRepository):
    """Verify cryptographic hash chaining across sequential audit logs."""
    log1 = await repository.log_audit_event(
        stage="IDLE", event_type="SYSTEM_BOOT", metadata={"version": "1.0.0"}
    )
    assert log1.previous_hash == "0" * 64
    assert len(log1.entry_hash) == 64

    log2 = await repository.log_audit_event(
        stage="AWAITING_RFID", event_type="AUTH_STARTED"
    )
    assert log2.previous_hash == log1.entry_hash

    log3 = await repository.log_audit_event(
        stage="AWAITING_FINGERPRINT", event_type="RFID_AUTH_SUCCESS", user_id=1
    )
    assert log3.previous_hash == log2.entry_hash

    # Verify audit trail integrity
    is_valid, error = await repository.verify_audit_trail_integrity()
    assert is_valid is True
    assert error is None

    # Retrieve audit logs
    logs = await repository.get_audit_logs(limit=10)
    assert len(logs) == 3
    assert logs[0].event_type == "SYSTEM_BOOT"
    assert logs[1].event_type == "AUTH_STARTED"
    assert logs[2].event_type == "RFID_AUTH_SUCCESS"


@pytest.mark.asyncio
async def test_tamper_detection_on_corrupted_audit_trail(
    repository: SqliteVaultRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
):
    """Verify that tampering with an audit record causes hash-chain verification to fail."""
    # Create 4 audit log entries
    await repository.log_audit_event(stage="IDLE", event_type="BOOT")
    await repository.log_audit_event(stage="AWAITING_RFID", event_type="SCAN_1")
    await repository.log_audit_event(stage="AWAITING_FINGERPRINT", event_type="FP_2")
    await repository.log_audit_event(stage="UNLOCKED", event_type="SUCCESS")

    # Verify healthy chain
    is_valid, _ = await repository.verify_audit_trail_integrity()
    assert is_valid is True

    # Tamper with entry #2 (modify event_type directly in database without updating hash)
    async with db_session_factory() as session:
        log2 = await session.get(AuditLog, 2)
        assert log2 is not None
        log2.event_type = "MALICIOUS_TAMPERED_EVENT"
        await session.commit()

    # Assert integrity check detects tampering
    is_valid, error_msg = await repository.verify_audit_trail_integrity()
    assert is_valid is False
    assert error_msg is not None
    assert "Tamper detected in Log ID 2" in error_msg


# ============================================================================
# 3. VaultAuthEngine End-to-End Database & Audit Logging Integration
# ============================================================================


@pytest.mark.asyncio
async def test_engine_database_user_and_audit_logging_e2e(
    repository: SqliteVaultRepository,
):
    """Verify VaultAuthEngine authenticates database user and generates complete audit trail."""
    ph = PasswordHasher()
    pwd_hash = ph.hash("VaultMasterKey#2026!")

    # Generate synthetic face and voice biometric profiles for Subject 777 / Speaker 1
    cam = MockCameraAdapter()
    face_vf = FaceVerifier(default_threshold=0.90)
    face_emb = face_vf.extract_embeddings(cam.generate_synthetic_face_frame(subject_seed=777))
    assert face_emb is not None

    audio = MockAudioAdapter()
    voice_vf = VoiceVerifier(default_threshold=0.85)
    voice_print = voice_vf.extract_voice_print(
        audio.generate_synthetic_utterance(speaker_seed=1)
    )
    assert voice_print is not None

    # Enroll user in SQLite database
    enrolled_user = await repository.create_user(
        username="ALICE_AGENT",
        rfid_uid="E2806894",
        fingerprint_id=1,
        password_hash=pwd_hash,
        face_embedding=face_emb,
        voice_print=voice_print,
        voice_passphrase="OPEN SESAME OVERENGINEERED",
    )

    # Initialize Engine with Repository
    hardware = MockHardwareAdapter(auto_initialize=True)
    engine = VaultAuthEngine(hardware=hardware, repository=repository)
    engine.set_face_verifier(verifier=face_vf, enrolled_embedding=face_emb, threshold=0.90)
    engine.set_voice_verifier(
        verifier=voice_vf,
        enrolled_voice_print=voice_print,
        expected_phrase="OPEN SESAME OVERENGINEERED",
        threshold=0.85,
    )

    await engine.initialize()
    await engine.start_authentication()

    # Step 1: RFID (Loads user from database)
    assert await engine.submit_rfid("E2806894") is True
    assert engine.active_user_id == enrolled_user.id
    assert engine.state == VaultState.AWAITING_FINGERPRINT

    # Step 2: Fingerprint
    assert await engine.submit_fingerprint(1, matched=True, confidence=0.98) is True
    assert engine.state == VaultState.AWAITING_FACE

    # Step 3: Face Frame
    live_face = cam.generate_synthetic_face_frame(subject_seed=777, noise_level=0.02)
    assert await engine.submit_face_frame(live_face) is True
    assert engine.state == VaultState.AWAITING_PASSWORD

    # Step 4: Argon2 Password
    assert await engine.submit_password("VaultMasterKey#2026!") is True
    assert engine.state == VaultState.AWAITING_VOICE

    # Step 5: Voice Utterance
    live_voice = audio.generate_synthetic_utterance(
        speaker_seed=1, phrase="OPEN SESAME OVERENGINEERED", noise_level=0.02
    )
    assert await engine.submit_voice_audio(live_voice, spoken_phrase="OPEN SESAME OVERENGINEERED") is True
    assert engine.state == VaultState.UNLOCKED

    # Verify physical hardware state
    assert hardware.is_locked is False

    # Verify Audit Trail in Database
    audit_logs = await repository.get_audit_logs(limit=50)
    assert len(audit_logs) >= 6

    # Verify user_id was associated with transition logs
    user_logs = [log for log in audit_logs if log.user_id == enrolled_user.id]
    assert len(user_logs) >= 5

    # Verify full audit chain integrity
    is_valid, error = await repository.verify_audit_trail_integrity()
    assert is_valid is True
    assert error is None


if __name__ == "__main__":
    import sys

    print("Running Step 7 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
