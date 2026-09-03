"""Audio Capture and Voice Biometric Interface Contracts.

Decouples the authentication engine from physical microphones, PyAudio,
sound cards, and speech-to-text / acoustic biometric model implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class AudioCaptureInterface(ABC):
    """Abstract Base Class for audio recording peripherals and streaming input."""

    @abstractmethod
    def record_utterance(
        self, duration_sec: float = 2.0, sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """Record an audio utterance as a 1D NumPy array of normalized 32-bit floats [-1.0, 1.0].

        Args:
            duration_sec: Duration in seconds to record.
            sample_rate: Audio sampling frequency in Hz (default: 16000).

        Returns:
            Optional[np.ndarray]: 1D float32 audio waveform, or None if recording failed.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the audio capture device is connected and ready.

        Returns:
            bool: True if available, False otherwise.
        """
        pass

    @abstractmethod
    def release(self) -> None:
        """Release audio capture hardware resources or stream handles."""
        pass


class VoiceVerifierInterface(ABC):
    """Abstract Base Class for acoustic speaker verification and passphrase checking."""

    @abstractmethod
    def extract_voice_print(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """Extract a normalized 1D acoustic speaker embedding (voice print).

        Args:
            audio_data: 1D float32 audio array.
            sample_rate: Sampling frequency in Hz.

        Returns:
            Optional[np.ndarray]: L2-normalized 1D floating-point embedding vector,
                                  or None if audio is silent or invalid.
        """
        pass

    @abstractmethod
    def compute_similarity(
        self, voice_print_a: np.ndarray, voice_print_b: np.ndarray
    ) -> float:
        """Compute cosine similarity score between two normalized voice prints.

        Args:
            voice_print_a: First voice print array.
            voice_print_b: Second voice print array.

        Returns:
            float: Cosine similarity score in range [-1.0, 1.0].
        """
        pass

    @abstractmethod
    def verify_speaker(
        self,
        sample: np.ndarray,
        enrolled_voice_print: np.ndarray,
        threshold: float = 0.85,
        sample_rate: int = 16000,
    ) -> bool:
        """Verify if the audio sample's acoustic voice print matches the enrolled profile.

        Args:
            sample: 1D audio sample array.
            enrolled_voice_print: Enrolled reference speaker embedding.
            threshold: Minimum cosine similarity required to authenticate.
            sample_rate: Sampling frequency in Hz.

        Returns:
            bool: True if similarity >= threshold, False otherwise.
        """
        pass

    @abstractmethod
    def verify_utterance(
        self,
        audio_data: np.ndarray,
        enrolled_voice_print: np.ndarray,
        expected_phrase: Optional[str] = None,
        spoken_phrase: Optional[str] = None,
        threshold: float = 0.85,
        sample_rate: int = 16000,
    ) -> bool:
        """Perform full two-factor voice verification: speaker acoustics + passphrase match.

        Args:
            audio_data: 1D audio waveform array.
            enrolled_voice_print: Enrolled speaker profile.
            expected_phrase: Expected challenge phrase string.
            spoken_phrase: Transcribed or provided spoken phrase string.
            threshold: Minimum acoustic similarity threshold.
            sample_rate: Sampling frequency in Hz.

        Returns:
            bool: True if both acoustic voice print and challenge phrase match.
        """
        pass
