"""Hardware Adapter Factory for The Inconvenient Vault.

Instantiates and configures the production ESP32SerialAdapter for physical embedded microcontroller communication.
"""

import logging
import os
from typing import Optional

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.interfaces.hardware import HardwareInterface

logger = logging.getLogger("vault.adapters.factory")


def get_hardware_adapter(
    port: Optional[str] = None,
    baudrate: int = 115200,
    auto_reconnect: bool = True,
) -> HardwareInterface:
    """Instantiate and return the production ESP32 Hardware Adapter.

    Args:
        port: Explicit serial port (e.g. 'COM3' or '/dev/ttyUSB0'). If None, inspects VAULT_SERIAL_PORT or auto-discovers.
        baudrate: Baud rate for serial communication (default: 115200).
        auto_reconnect: Whether to automatically reconnect if serial link drops.

    Returns:
        HardwareInterface: Instance of ESP32SerialAdapter.
    """
    target_port = port or os.environ.get("VAULT_SERIAL_PORT", None)
    logger.info(f"Instantiating ESP32SerialAdapter (Port: {target_port or 'AUTO-DISCOVER'}, Baud: {baudrate})")
    return ESP32SerialAdapter(
        port=target_port,
        baudrate=baudrate,
        auto_reconnect=auto_reconnect,
    )
