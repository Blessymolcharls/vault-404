"""Production Hardware and peripheral adapters for The Inconvenient Vault."""

from app.adapters.audio import SoundDeviceAudioAdapter
from app.adapters.camera import OpenCVCameraAdapter
from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.adapters.factory import get_hardware_adapter

__all__ = [
    "ESP32SerialAdapter",
    "OpenCVCameraAdapter",
    "SoundDeviceAudioAdapter",
    "get_hardware_adapter",
]
