"""Interface contracts and abstract base classes for The Inconvenient Vault."""

from app.interfaces.audio import AudioCaptureInterface, VoiceVerifierInterface
from app.interfaces.hardware import HardwareEventCallback, HardwareInterface
from app.interfaces.repository import VaultRepositoryInterface
from app.interfaces.vision import CameraCaptureInterface, FaceRecognizerInterface

__all__ = [
    "HardwareInterface",
    "HardwareEventCallback",
    "CameraCaptureInterface",
    "FaceRecognizerInterface",
    "AudioCaptureInterface",
    "VoiceVerifierInterface",
    "VaultRepositoryInterface",
]
