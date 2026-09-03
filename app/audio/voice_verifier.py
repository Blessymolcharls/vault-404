"""Voice Biometric and Passphrase Verification Subsystem for The Inconvenient Vault.

Provides acoustic speaker voiceprint extraction, pitch and formant spectral analysis,
cosine similarity matching, and challenge passphrase validation.
"""

import logging
from typing import Optional
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
import scipy.signal

from app.interfaces.audio import VoiceVerifierInterface

logger = logging.getLogger("vault.audio.voice_verifier")


class VoiceVerificationResult(BaseModel):
    """Detailed verification metrics returned by the voice verification pipeline."""

    model_config = ConfigDict(frozen=True)

    matched: bool = Field(description="Whether full 2-factor voice authentication succeeded")
    similarity: float = Field(description="Cosine similarity score [-1.0, 1.0] of acoustic voiceprint")
    threshold: float = Field(description="Configured acoustic similarity threshold")
    speaker_matched: bool = Field(description="Whether acoustic voiceprint passed threshold")
    phrase_matched: bool = Field(description="Whether spoken challenge passphrase matched")
    expected_phrase: Optional[str] = Field(default=None, description="Target challenge phrase")
    spoken_phrase: Optional[str] = Field(default=None, description="Evaluated spoken phrase")


class VoiceVerifier(VoiceVerifierInterface):
    """Acoustic voiceprint analysis and two-factor voice verification pipeline."""

    def __init__(
        self,
        default_threshold: float = 0.85,
        default_sample_rate: int = 16000,
    ) -> None:
        """Initialize the VoiceVerifier pipeline.

        Args:
            default_threshold: Minimum cosine similarity for speaker verification.
            default_sample_rate: Audio sampling frequency in Hz.
        """
        self.default_threshold: float = default_threshold
        self.default_sample_rate: int = default_sample_rate

    def extract_voice_print(
        self, audio_data: np.ndarray, sample_rate: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """Extract an L2-normalized 256-dimensional acoustic spectral and pitch voiceprint.

        Args:
            audio_data: 1D float32 audio waveform.
            sample_rate: Audio sampling rate in Hz (default: 16000).

        Returns:
            Optional[np.ndarray]: 1D L2-normalized 256D float32 vector, or None if invalid.
        """
        if audio_data is None or len(audio_data) < 512:
            logger.warning("extract_voice_print received insufficient or None audio data.")
            return None

        sr = sample_rate or self.default_sample_rate
        audio_flat = audio_data.flatten().astype(np.float32)

        # Check for near-silent audio
        energy = float(np.mean(audio_flat ** 2))
        if energy < 1e-7:
            logger.warning("Audio data is silent or near-zero energy.")
            return None

        # 1. Welch Power Spectral Density (128 sub-band spectral energy moments)
        nperseg = min(1024, len(audio_flat))
        freqs, psd = scipy.signal.welch(
            audio_flat, fs=sr, nperseg=nperseg, noverlap=nperseg // 2
        )
        log_psd = np.log10(psd + 1e-12)

        # Resample log_psd to 128 bins
        bins_per_band = max(1, (len(log_psd) - 1) // 128)
        sub_bands = []
        for i in range(128):
            start_idx = i * bins_per_band
            end_idx = min(len(log_psd), (i + 1) * bins_per_band)
            if start_idx < len(log_psd):
                sub_bands.append(float(np.mean(log_psd[start_idx:end_idx])))
            else:
                sub_bands.append(0.0)

        sub_bands_arr = np.array(sub_bands, dtype=np.float32)
        sub_bands_arr = sub_bands_arr - float(np.mean(sub_bands_arr))

        # 2. Autocorrelation Pitch-Lag Profile (128 lags capturing pitch frequencies)
        autocorr = np.correlate(audio_flat, audio_flat, mode="full")
        center = len(autocorr) // 2
        max_lag = min(128, len(autocorr) - center - 20)
        lags = np.zeros(128, dtype=np.float32)
        if max_lag > 0 and autocorr[center] > 1e-12:
            raw_lags = autocorr[center + 20 : center + 20 + max_lag] / autocorr[center]
            lags[:max_lag] = raw_lags.astype(np.float32)

        lags = lags - float(np.mean(lags))

        # Concatenate: 128 spectral sub-bands + 128 pitch lags = 256 features
        raw_feature = np.concatenate([sub_bands_arr, lags])
        norm = float(np.linalg.norm(raw_feature))
        if norm > 1e-12:
            normalized_voiceprint = raw_feature / norm
        else:
            normalized_voiceprint = raw_feature

        return normalized_voiceprint.astype(np.float32)

    def compute_similarity(
        self, voice_print_a: np.ndarray, voice_print_b: np.ndarray
    ) -> float:
        """Compute cosine similarity score between two normalized voice prints.

        Args:
            voice_print_a: First 1D voiceprint vector.
            voice_print_b: Second 1D voiceprint vector.

        Returns:
            float: Cosine similarity score in range [-1.0, 1.0].
        """
        if voice_print_a is None or voice_print_b is None:
            return 0.0

        flat_a = voice_print_a.flatten().astype(np.float64)
        flat_b = voice_print_b.flatten().astype(np.float64)

        norm_a = np.linalg.norm(flat_a)
        norm_b = np.linalg.norm(flat_b)

        if norm_a < 1e-12 or norm_b < 1e-12:
            return 0.0

        dot = np.dot(flat_a, flat_b)
        cosine_sim = float(dot / (norm_a * norm_b))
        return max(-1.0, min(1.0, cosine_sim))

    def verify_speaker(
        self,
        sample: np.ndarray,
        enrolled_voice_print: np.ndarray,
        threshold: Optional[float] = None,
        sample_rate: Optional[int] = None,
    ) -> bool:
        """Verify if the audio sample's voice print matches the enrolled profile above threshold."""
        th = threshold if threshold is not None else self.default_threshold
        vp = self.extract_voice_print(sample, sample_rate=sample_rate)
        if vp is None:
            return False

        sim = self.compute_similarity(vp, enrolled_voice_print)
        return sim >= th

    def verify_utterance_detailed(
        self,
        audio_data: np.ndarray,
        enrolled_voice_print: np.ndarray,
        expected_phrase: Optional[str] = None,
        spoken_phrase: Optional[str] = None,
        threshold: Optional[float] = None,
        sample_rate: Optional[int] = None,
    ) -> VoiceVerificationResult:
        """Execute full 2-factor verification returning comprehensive acoustic and phrase metrics."""
        th = threshold if threshold is not None else self.default_threshold
        sr = sample_rate or self.default_sample_rate

        # 1. Acoustic Speaker Verification
        vp = self.extract_voice_print(audio_data, sample_rate=sr)
        if vp is None:
            return VoiceVerificationResult(
                matched=False,
                similarity=0.0,
                threshold=th,
                speaker_matched=False,
                phrase_matched=False,
                expected_phrase=expected_phrase,
                spoken_phrase=spoken_phrase,
            )

        sim = self.compute_similarity(vp, enrolled_voice_print)
        speaker_matched = bool(sim >= th)

        # 2. Challenge Passphrase Verification
        phrase_matched = True
        if expected_phrase is not None:
            if spoken_phrase is not None:
                norm_expected = " ".join(expected_phrase.strip().upper().split())
                norm_spoken = " ".join(spoken_phrase.strip().upper().split())
                phrase_matched = norm_expected == norm_spoken
            else:
                phrase_matched = False

        matched = speaker_matched and phrase_matched

        logger.info(
            f"[VOICE VERIFICATION] Acoustic Sim: {sim:.4f} (Threshold: {th:.4f}, SpeakerOK: {speaker_matched}) | "
            f"PhraseOK: {phrase_matched} -> Matched: {matched}"
        )

        return VoiceVerificationResult(
            matched=matched,
            similarity=sim,
            threshold=th,
            speaker_matched=speaker_matched,
            phrase_matched=phrase_matched,
            expected_phrase=expected_phrase,
            spoken_phrase=spoken_phrase,
        )

    def verify_utterance(
        self,
        audio_data: np.ndarray,
        enrolled_voice_print: np.ndarray,
        expected_phrase: Optional[str] = None,
        spoken_phrase: Optional[str] = None,
        threshold: Optional[float] = None,
        sample_rate: Optional[int] = None,
    ) -> bool:
        """Contract fulfillment for VoiceVerifierInterface."""
        result = self.verify_utterance_detailed(
            audio_data=audio_data,
            enrolled_voice_print=enrolled_voice_print,
            expected_phrase=expected_phrase,
            spoken_phrase=spoken_phrase,
            threshold=threshold,
            sample_rate=sample_rate,
        )
        return result.matched
