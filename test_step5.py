"""Automated test suite for Step 5 of The Inconvenient Vault.

Validates:
1. CameraCaptureInterface contract & MockCameraAdapter synthetic frame generation.
2. FaceVerifier feature embedding extraction, L2 normalization, and cosine similarity.
3. Anti-spoofing / liveness detection and blur sensitivity.
4. Biometric matching (Subject A vs Subject B distinct templates).
5. VaultAuthEngine integration: frame ingestion, advancement to AWAITING_KEYPAD_PIN,
   and retry threshold lockout.
"""

import asyncio
import numpy as np
import pytest

from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import LedColor, VaultState
from app.vision.face_verifier import FaceVerifier


@pytest.fixture
def mock_camera() -> MockCameraAdapter:
    """Fixture providing a mock camera adapter."""
    return MockCameraAdapter(default_seed=42)


@pytest.fixture
def face_verifier() -> FaceVerifier:
    """Fixture providing an initialized FaceVerifier pipeline."""
    return FaceVerifier(default_threshold=0.90, min_liveness_threshold=0.35)


@pytest.fixture
def mock_hardware() -> MockHardwareAdapter:
    """Fixture providing an initialized mock hardware adapter."""
    return MockHardwareAdapter(auto_initialize=True)


# ============================================================================
# 1. Camera Adapter & Synthetic Frame Tests
# ============================================================================


def test_mock_camera_lifecycle_and_frame_capture(mock_camera: MockCameraAdapter):
    """Verify MockCameraAdapter captures valid image arrays and respects offline status."""
    assert mock_camera.is_opened() is True

    frame = mock_camera.capture_frame()
    assert frame is not None
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (480, 640, 3)
    assert frame.dtype == np.uint8

    # Test offline toggle
    mock_camera.set_offline(True)
    assert mock_camera.is_opened() is False
    assert mock_camera.capture_frame() is None

    # Test release
    mock_camera.release()
    assert mock_camera.is_opened() is False


def test_synthetic_face_generation_consistency(mock_camera: MockCameraAdapter):
    """Verify synthetic face generation produces consistent frames for identical seeds."""
    frame1 = mock_camera.generate_synthetic_face_frame(subject_seed=100, noise_level=0.0)
    frame2 = mock_camera.generate_synthetic_face_frame(subject_seed=100, noise_level=0.0)
    assert np.array_equal(frame1, frame2)

    # Different seeds produce different frames
    frame3 = mock_camera.generate_synthetic_face_frame(subject_seed=200, noise_level=0.0)
    assert not np.array_equal(frame1, frame3)


# ============================================================================
# 2. Embedding Extraction & Cosine Similarity Tests
# ============================================================================


def test_embedding_extraction_and_normalization(
    face_verifier: FaceVerifier, mock_camera: MockCameraAdapter
):
    """Verify facial embedding vector extraction and strict L2 unit normalization."""
    frame = mock_camera.generate_synthetic_face_frame(subject_seed=42)
    embedding = face_verifier.extract_embeddings(frame)

    assert embedding is not None
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (256,)
    assert embedding.dtype == np.float32

    # L2 norm must equal 1.0 (unit vector)
    norm = float(np.linalg.norm(embedding))
    assert pytest.approx(norm, rel=1e-4) == 1.0


def test_cosine_similarity_mathematical_properties(face_verifier: FaceVerifier):
    """Verify cosine similarity mathematical boundary values."""
    vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    vec_b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    vec_c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    vec_d = np.array([-1.0, 0.0, 0.0], dtype=np.float32)

    # Identical vectors -> 1.0
    assert pytest.approx(face_verifier.compute_similarity(vec_a, vec_b)) == 1.0
    # Orthogonal vectors -> 0.0
    assert pytest.approx(face_verifier.compute_similarity(vec_a, vec_c)) == 0.0
    # Opposite vectors -> -1.0
    assert pytest.approx(face_verifier.compute_similarity(vec_a, vec_d)) == -1.0


# ============================================================================
# 3. Anti-Spoofing & Liveness Tests
# ============================================================================


def test_liveness_detection_focus_and_blur(
    face_verifier: FaceVerifier, mock_camera: MockCameraAdapter
):
    """Verify liveness check scores sharp images higher than blurred images."""
    sharp_frame = mock_camera.generate_synthetic_face_frame(subject_seed=42, blur=False)
    blurred_frame = mock_camera.generate_synthetic_face_frame(subject_seed=42, blur=True)

    sharp_liveness = face_verifier.check_liveness(sharp_frame)
    blurred_liveness = face_verifier.check_liveness(blurred_frame)

    assert sharp_liveness > face_verifier.min_liveness_threshold
    assert sharp_liveness > blurred_liveness
    assert blurred_liveness < face_verifier.min_liveness_threshold


# ============================================================================
# 4. Biometric Face Verification Tests
# ============================================================================


def test_face_verification_matching_and_rejection(
    face_verifier: FaceVerifier, mock_camera: MockCameraAdapter
):
    """Verify authorized subject template matches while unauthorized subject is rejected."""
    # Enroll Subject A (Seed 777)
    enrolled_frame = mock_camera.generate_synthetic_face_frame(subject_seed=777, noise_level=0.0)
    enrolled_embedding = face_verifier.extract_embeddings(enrolled_frame)
    assert enrolled_embedding is not None

    # Live capture of Subject A (with slight realistic camera noise)
    live_frame_subject_a = mock_camera.generate_synthetic_face_frame(
        subject_seed=777, noise_level=0.02
    )
    result_a = face_verifier.verify_face_detailed(live_frame_subject_a, enrolled_embedding)
    assert result_a.matched is True
    assert result_a.similarity >= 0.90
    assert result_a.is_live is True

    # Live capture of Subject B (Unauthorized intruder - Seed 200)
    live_frame_subject_b = mock_camera.generate_synthetic_face_frame(
        subject_seed=200, noise_level=0.02
    )
    result_b = face_verifier.verify_face_detailed(live_frame_subject_b, enrolled_embedding)
    assert result_b.matched is False
    assert result_b.similarity < 0.80


# ============================================================================
# 5. VaultAuthEngine Computer Vision Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_engine_face_frame_advances_to_password(
    mock_hardware: MockHardwareAdapter,
    mock_camera: MockCameraAdapter,
    face_verifier: FaceVerifier,
):
    """Test full sequential progression up to AWAITING_FACE and frame verification."""
    # Enroll Subject A template into engine
    enrolled_frame = mock_camera.generate_synthetic_face_frame(subject_seed=777, noise_level=0.0)
    enrolled_embedding = face_verifier.extract_embeddings(enrolled_frame)
    assert enrolled_embedding is not None

    engine = VaultAuthEngine(hardware=mock_hardware)
    engine.set_face_verifier(
        verifier=face_verifier,
        enrolled_embedding=enrolled_embedding,
        threshold=0.90,
    )

    await engine.initialize()
    await engine.start_authentication()

    # Step 1: RFID
    assert await engine.submit_rfid("E2806894") is True
    assert engine.state == VaultState.AWAITING_FACE

    # Step 3: Face Frame (Live capture of Subject A)
    live_frame = mock_camera.generate_synthetic_face_frame(subject_seed=777, noise_level=0.02)
    face_ok = await engine.submit_face_frame(live_frame)

    assert face_ok is True
    assert engine.state == VaultState.AWAITING_KEYPAD_PIN
    assert mock_hardware.current_display.line1 == "[3/4] ENTER PIN"


@pytest.mark.asyncio
async def test_engine_unrecognized_face_triggers_lockout(
    mock_hardware: MockHardwareAdapter,
    mock_camera: MockCameraAdapter,
    face_verifier: FaceVerifier,
):
    """Verify 3 consecutive failed facial frames trigger security LOCKOUT and alarm."""
    enrolled_frame = mock_camera.generate_synthetic_face_frame(subject_seed=777)
    enrolled_embedding = face_verifier.extract_embeddings(enrolled_frame)
    assert enrolled_embedding is not None

    config = EngineConfig(max_failed_attempts=3)
    engine = VaultAuthEngine(hardware=mock_hardware, config=config)
    engine.set_face_verifier(
        verifier=face_verifier,
        enrolled_embedding=enrolled_embedding,
        threshold=0.90,
    )

    await engine.initialize()
    await engine.start_authentication()
    await engine.submit_rfid("E2806894")
    assert engine.state == VaultState.AWAITING_FACE

    # Intruder face (Seed 200)
    intruder_frame = mock_camera.generate_synthetic_face_frame(subject_seed=200)

    # 1st Failure
    assert await engine.submit_face_frame(intruder_frame) is False
    assert engine.failed_attempts == 1
    assert engine.state == VaultState.AWAITING_FACE

    # 2nd Failure
    assert await engine.submit_face_frame(intruder_frame) is False
    assert engine.failed_attempts == 2
    assert engine.state == VaultState.AWAITING_FACE

    # 3rd Failure -> Triggers LOCKOUT
    assert await engine.submit_face_frame(intruder_frame) is False
    assert engine.state == VaultState.LOCKOUT
    assert mock_hardware.is_locked is True
    assert mock_hardware.is_alarm_active is True
    assert mock_hardware.current_display.led_color == LedColor.RED


if __name__ == "__main__":
    import sys

    print("Running Step 5 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
