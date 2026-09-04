"""Production Audio Capture Adapter for The Inconvenient Vault.

Records live acoustic utterances from physical microphones using sounddevice
with automatic device enumeration, sample rate conversion, and float32 normalization.
"""

import logging
import os
from typing import Optional
import numpy as np

from app.interfaces.audio import AudioCaptureInterface

logger = logging.getLogger("vault.adapters.audio")


class SoundDeviceAudioAdapter(AudioCaptureInterface):
    """Production audio adapter capturing live microphone audio via sounddevice."""

    def __init__(
        self,
        device_index: Optional[int] = None,
        default_sample_rate: int = 16000,
    ) -> None:
        """Initialize the SoundDevice Audio Adapter.

        Args:
            device_index: Hardware input device index. If None, uses system default.
            default_sample_rate: Standard sampling rate in Hz (default: 16000).
        """
        if device_index is None:
            env_dev = os.environ.get("VAULT_AUDIO_DEVICE_INDEX")
            if env_dev is not None:
                try:
                    self._device_index: Optional[int] = int(env_dev)
                except ValueError:
                    self._device_index = None
            else:
                self._device_index = None
        else:
            self._device_index = device_index

        self._sample_rate = default_sample_rate
        self._is_available = self._check_device_availability()

    def _check_device_availability(self) -> bool:
        """Check if a valid physical audio input device exists."""
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            if self._device_index is not None:
                dev = sd.query_devices(self._device_index)
                if dev.get("max_input_channels", 0) > 0:
                    logger.info(f"Selected audio input device [{self._device_index}]: {dev.get('name')}")
                    return True
                logger.warning(f"Audio device index {self._device_index} has 0 input channels.")
                return False

            default_input = sd.query_devices(kind="input")
            if default_input and default_input.get("max_input_channels", 0) > 0:
                logger.info(f"Default audio input device detected: {default_input.get('name')}")
                return True

            logger.warning("No default audio input device found with recording capabilities.")
            return False
        except Exception as ex:
            logger.warning(f"Failed to query sounddevice audio devices: {ex}")
            return False

    def is_available(self) -> bool:
        """Return whether physical microphone input is available."""
        return self._check_device_availability()

    def release(self) -> None:
        """Release audio recording resources."""
        try:
            import sounddevice as sd

            sd.stop()
            logger.info("SoundDevice audio resources released.")
        except Exception as ex:
            logger.warning(f"Error releasing sounddevice: {ex}")

    def record_utterance(
        self, duration_sec: float = 2.0, sample_rate: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """Record live acoustic audio from the physical microphone.

        Args:
            duration_sec: Duration of utterance in seconds (default: 2.0).
            sample_rate: Sampling frequency in Hz (default: 16000).

        Returns:
            Optional[np.ndarray]: 1D float32 audio waveform in range [-1.0, 1.0],
                                  or None if recording failed.
        """
        sr = sample_rate or self._sample_rate
        num_samples = int(duration_sec * sr)

        try:
            import sounddevice as sd

            logger.info(f"Recording live audio utterance ({duration_sec}s @ {sr}Hz)...")
            recording = sd.rec(
                frames=num_samples,
                samplerate=sr,
                channels=1,
                dtype="float32",
                device=self._device_index,
            )
            sd.wait()

            audio_1d = recording.flatten()
            # Normalize to [-1.0, 1.0] if clipping or low magnitude
            peak = float(np.max(np.abs(audio_1d)))
            if peak > 1.0:
                audio_1d = audio_1d / peak

            logger.info(f"Audio recording complete. Peak amplitude: {peak:.4f}")
            return audio_1d.astype(np.float32)

        except Exception as ex:
            logger.error(f"Failed to record live audio utterance via sounddevice: {ex}")
            return None

    @staticmethod
    def calculate_rms(audio_data: np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) signal energy of an audio waveform."""
        if audio_data is None or len(audio_data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio_data))))
