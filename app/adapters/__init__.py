"""Hardware and peripheral simulation adapters for The Inconvenient Vault."""

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.adapters.factory import get_hardware_adapter
from app.adapters.mock_audio import MockAudioAdapter
from app.adapters.mock_camera import MockCameraAdapter
from app.adapters.mock_hardware import MockHardwareAdapter

__all__ = [
    "MockHardwareAdapter",
    "MockCameraAdapter",
    "MockAudioAdapter",
    "ESP32SerialAdapter",
    "get_hardware_adapter",
]
