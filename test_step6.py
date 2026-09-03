"""Automated test suite for Step 6 of The Inconvenient Vault.

Validates:
1. AudioCaptureInterface contract & MockAudioAdapter synthetic acoustic synthesis.
2. VoiceVerifier voiceprint extraction, L2 unit normalization, and cosine similarity.
3. Two-factor voice verification (Acoustic Speaker Matching + Challenge Passphrase Check).
4. Full 5-stage traversal of VaultAuthEngine leading to UNLOCKED state and solenoid actuation.
5. Voice authentication retry threshold exhaustion causing security LOCKOUT.
"""

import asyncio
import numpy as np
import pytest

from app.adapters.mock_audio import MockAudioAdapter
from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.audio.voice_verifier import VoiceVerifier
from app.core.engine import EngineConfig, VaultAuthEngine
from app.core.types import LedColor, VaultState
from app.vision.face_verifier import FaceVerifier


@pytest.fixture
def mock_audio() -> MockAudioAdapter:
    """Fixture providing an initialized MockAudioAdapter."""
    return MockAudioAdapter(default_speaker_seed=1, default_sample_rate=16000)


@pytest.fixture
def voice_verifier() -> VoiceVerifier:
    """Fixture providing an initialized VoiceVerifier pipeline."""
    return VoiceVerifier(default_threshold=0.85, default_sample_rate=16000)


@pytest.fixture
def mock_hardware() -> MockHardwareAdapter:
    """Fixture providing an initialized MockHardwareAdapter."""
    return MockHardwareAdapter(auto_initialize=True)


# ============================================================================
# 1. Audio Adapter & Waveform Synthesis Tests
# ============================================================================


def test_mock_audio_adapter_lifecycle(mock_audio: MockAudioAdapter):
    """Verify MockAudioAdapter captures valid audio waveforms and respects offline status."""
    assert mock_audio.is_available() is True

    audio = mock_audio.record_utterance(duration_sec=1.0)
    assert audio is not None
    assert isinstance(audio, np.ndarray)
    assert len(audio) == 16000
    assert audio.dtype == np.float32
    assert float(np.max(np.abs(audio))) <= 1.0

    # Offline toggle
    mock_audio.set_offline(True)
    assert mock_audio.is_available() is False
    assert mock_audio.record_utterance() is None

    # Release
    mock_audio.release()
    assert mock_audio.is_available() is False


def test_synthetic_utterance_generation_determinism(mock_audio: MockAudioAdapter):
    """Verify synthetic speech generation is deterministic for identical seeds and phrases."""
    u1 = mock_audio.generate_synthetic_utterance(speaker_seed=1, noise_level=0.0)
    u2 = mock_audio.generate_synthetic_utterance(speaker_seed=1, noise_level=0.0)
    assert np.array_equal(u1, u2)

    # Different seeds produce different waveforms
    u3 = mock_audio.generate_synthetic_utterance(speaker_seed=2, noise_level=0.0)
    assert not np.array_equal(u1, u3)


# ============================================================================
# 2. Voiceprint Extraction & Cosine Similarity Tests
# ============================================================================


def test_voiceprint_extraction_and_normalization(
    voice_verifier: VoiceVerifier, mock_audio: MockAudioAdapter
):
    """Verify 256D voiceprint extraction and strict L2 unit normalization."""
    audio = mock_audio.generate_synthetic_utterance(speaker_seed=1)
    voiceprint = voice_verifier.extract_voice_print(audio)

    assert voiceprint is not None
    assert isinstance(voiceprint, np.ndarray)
    assert voiceprint.shape == (256,)
    assert voiceprint.dtype == np.float32

    # L2 norm must equal 1.0 (unit vector)
    norm = float(np.linalg.norm(voiceprint))
    assert pytest.approx(norm, rel=1e-4) == 1.0


def test_voice_cosine_similarity_mathematical_properties(voice_verifier: VoiceVerifier):
    """Verify cosine similarity mathematical boundaries for voiceprints."""
    v_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v_b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v_c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    v_d = np.array([-1.0, 0.0, 0.0], dtype=np.float32)

    assert pytest.approx(voice_verifier.compute_similarity(v_a, v_b)) == 1.0
    assert pytest.approx(voice_verifier.compute_similarity(v_a, v_c)) == 0.0
    assert pytest.approx(voice_verifier.compute_similarity(v_a, v_d)) == -1.0


# ============================================================================
# 3. Two-Factor Voice Verification Tests (Speaker + Passphrase)
# ============================================================================


def test_speaker_acoustic_matching_and_rejection(
    voice_verifier: VoiceVerifier, mock_audio: MockAudioAdapter
):
    """Verify authorized speaker voiceprint matches while unauthorized speaker is rejected."""
    # Enroll Speaker 1
    enrolled_audio = mock_audio.generate_synthetic_utterance(speaker_seed=1, noise_level=0.0)
    enrolled_vp = voice_verifier.extract_voice_print(enrolled_audio)
    assert enrolled_vp is not None

    # Live capture of Speaker 1 (with realistic noise)
    live_speaker_1 = mock_audio.generate_synthetic_utterance(speaker_seed=1, noise_level=0.02)
    assert voice_verifier.verify_speaker(live_speaker_1, enrolled_vp, threshold=0.85) is True

    # Live capture of Speaker 2 (Intruder)
    live_speaker_2 = mock_audio.generate_synthetic_utterance(speaker_seed=2, noise_level=0.02)
    assert voice_verifier.verify_speaker(live_speaker_2, enrolled_vp, threshold=0.85) is False


def test_two_factor_voice_and_passphrase_verification(
    voice_verifier: VoiceVerifier, mock_audio: MockAudioAdapter
):
    """Verify both acoustic voiceprint and challenge passphrase must pass."""
    enrolled_audio = mock_audio.generate_synthetic_utterance(speaker_seed=1)
    enrolled_vp = voice_verifier.extract_voice_print(enrolled_audio)
    assert enrolled_vp is not None

    target_phrase = "OPEN SESAME OVERENGINEERED"

    # Case 1: Valid Speaker + Correct Phrase -> MATCH
    audio_s1 = mock_audio.generate_synthetic_utterance(speaker_seed=1, phrase=target_phrase)
    res1 = voice_verifier.verify_utterance_detailed(
        audio_data=audio_s1,
        enrolled_voice_print=enrolled_vp,
        expected_phrase=target_phrase,
        spoken_phrase=target_phrase,
    )
    assert res1.matched is True
    assert res1.speaker_matched is True
    assert res1.phrase_matched is True

    # Case 2: Valid Speaker + Incorrect Phrase -> REJECT
    res2 = voice_verifier.verify_utterance_detailed(
        audio_data=audio_s1,
        enrolled_voice_print=enrolled_vp,
        expected_phrase=target_phrase,
        spoken_phrase="WRONG PASSPHRASE HERE",
    )
    assert res2.matched is False
    assert res2.speaker_matched is True
    assert res2.phrase_matched is False

    # Case 3: Intruder Speaker + Correct Phrase -> REJECT
    audio_s2 = mock_audio.generate_synthetic_utterance(speaker_seed=2, phrase=target_phrase)
    res3 = voice_verifier.verify_utterance_detailed(
        audio_data=audio_s2,
        enrolled_voice_print=enrolled_vp,
        expected_phrase=target_phrase,
        spoken_phrase=target_phrase,
    )
    assert res3.matched is False
    assert res3.speaker_matched is False
    assert res3.phrase_matched is True


# ============================================================================
# 4. VaultAuthEngine Full End-to-End Traversal to UNLOCKED
# ============================================================================


@pytest.mark.asyncio
async def test_full_5_stage_e2e_authentication_to_unlocked(
    mock_hardware: MockHardwareAdapter,
    mock_audio: MockAudioAdapter,
    voice_verifier: VoiceVerifier,
):
    """Test full sequential authentication across all 5 stages to UNLOCKED."""
    # Enroll Speaker 1 voiceprint
    enrolled_audio = mock_audio.generate_synthetic_utterance(speaker_seed=1)
    enrolled_vp = voice_verifier.extract_voice_print(enrolled_audio)
    assert enrolled_vp is not None

    # Setup Computer Vision Face Verifier
    cam = MockCameraAdapter()
    face_vf = FaceVerifier(default_threshold=0.90)
    enrolled_face = face_vf.extract_embeddings(cam.generate_synthetic_face_frame(subject_seed=777))
    assert enrolled_face is not None

    engine = VaultAuthEngine(hardware=mock_hardware)
    engine.set_face_verifier(verifier=face_vf, enrolled_embedding=enrolled_face, threshold=0.90)
    engine.set_voice_verifier(
        verifier=voice_verifier,
        enrolled_voice_print=enrolled_vp,
        expected_phrase="OPEN SESAME OVERENGINEERED",
        threshold=0.85,
    )

    await engine.initialize()
    await engine.start_authentication()

    # Stage 1: RFID
    assert await engine.submit_rfid("E2806894") is True
    assert engine.state == VaultState.AWAITING_FACE

    # Stage 2: Fingerprint
    assert engine.state == VaultState.AWAITING_FACE

    # Stage 3: Face Frame
    live_face = cam.generate_synthetic_face_frame(subject_seed=777, noise_level=0.02)
    assert await engine.submit_face_frame(live_face) is True
    assert engine.state == VaultState.AWAITING_KEYPAD_PIN

    # Stage 4: Password
    assert await engine.submit_keypad_pin("VaultMasterKey#2026!") is True
    assert engine.state == VaultState.AWAITING_VOICE

    # Stage 5: Voice Audio Utterance
    live_voice = mock_audio.generate_synthetic_utterance(
        speaker_seed=1, noise_level=0.02
    )
    unlocked = await engine.submit_voice_audio(audio_data=live_voice)

    assert unlocked is True
    assert engine.state == VaultState.UNLOCKED

    # Verify physical lock actuation
    assert mock_hardware.is_locked is False
    assert mock_hardware.current_display.line1 == "VAULT UNLOCKED"
    assert mock_hardware.current_display.led_color == LedColor.GREEN


@pytest.mark.asyncio
async def test_engine_voice_mismatch_triggers_lockout(
    mock_hardware: MockHardwareAdapter,
    mock_audio: MockAudioAdapter,
    voice_verifier: VoiceVerifier,
):
    """Verify 3 failed voice authentication attempts trigger security LOCKOUT and alarm."""
    enrolled_audio = mock_audio.generate_synthetic_utterance(speaker_seed=1)
    enrolled_vp = voice_verifier.extract_voice_print(enrolled_audio)
    assert enrolled_vp is not None

    config = EngineConfig(max_failed_attempts=3)
    engine = VaultAuthEngine(hardware=mock_hardware, config=config)
    engine.set_voice_verifier(
        verifier=voice_verifier,
        enrolled_voice_print=enrolled_vp,
        expected_phrase="OPEN SESAME OVERENGINEERED",
        threshold=0.85,
    )

    await engine.initialize()
    await engine.start_authentication()
    await engine.submit_rfid("E2806894")
    await engine.submit_face("SUBJECT_001_OPERATOR")
    await engine.submit_keypad_pin("VaultMasterKey#2026!")
    assert engine.state == VaultState.AWAITING_VOICE

    # Intruder voice (Speaker 2)
    intruder_voice = mock_audio.generate_synthetic_utterance(speaker_seed=2)

    # 1st Failure
    assert await engine.submit_voice_audio(audio_data=intruder_voice) is False
    assert engine.failed_attempts == 1
    assert engine.state == VaultState.AWAITING_VOICE

    # 2nd Failure
    assert await engine.submit_voice_audio(audio_data=intruder_voice) is False
    assert engine.failed_attempts == 2
    assert engine.state == VaultState.AWAITING_VOICE

    # 3rd Failure -> Triggers LOCKOUT
    assert await engine.submit_voice_audio(audio_data=intruder_voice) is False
    assert engine.state == VaultState.LOCKOUT
    assert mock_hardware.is_locked is True
    assert mock_hardware.is_alarm_active is True
    assert mock_hardware.current_display.line1 == "SECURITY LOCKOUT"
    assert mock_hardware.current_display.led_color == LedColor.RED


if __name__ == "__main__":
    import sys

    print("Running Step 6 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
