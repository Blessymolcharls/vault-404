"""Hardware Adapter Factory for The Inconvenient Vault.

Provides seamless runtime switching between MockHardwareAdapter (Simulation)
and ESP32SerialAdapter (Physical Embedded Microcontroller) with zero core engine changes.
"""

import logging
import os
from typing import Optional

from app.adapters.esp32_hardware import ESP32SerialAdapter
from app.adapters.mock_hardware import MockHardwareAdapter
from app.interfaces.hardware import HardwareInterface

logger = logging.getLogger("vault.adapters.factory")


def get_hardware_adapter(
    mode: Optional[str] = None,
    port: Optional[str] = None,
    baudrate: int = 115200,
    auto_initialize: bool = True,
) -> HardwareInterface:
    """Instantiate and return the configured HardwareInterface implementation.

    Args:
        mode: Explicit mode string ('REAL' or 'SIMULATED'). If None, inspects VAULT_HARDWARE_MODE env var.
        port: Explicit serial port (e.g. 'COM3' or '/dev/ttyUSB0'). If None, inspects VAULT_SERIAL_PORT.
        baudrate: Baud rate for serial communication (default: 115200).
        auto_initialize: Whether to pre-initialize the adapter if applicable.

    Returns:
        HardwareInterface: Instance of ESP32SerialAdapter or MockHardwareAdapter.
    """
    target_mode = (mode or os.environ.get("VAULT_HARDWARE_MODE", "SIMULATED")).strip().upper()

    if target_mode == "REAL":
        target_port = port or os.environ.get("VAULT_SERIAL_PORT", None)
        logger.info(f"Instantiating ESP32SerialAdapter (Port: {target_port or 'AUTO-DISCOVER'}, Baud: {baudrate})")
        return ESP32SerialAdapter(port=target_port, baudrate=baudrate)

    logger.info("Instantiating MockHardwareAdapter (Virtual Simulation Mode)")
    return MockHardwareAdapter(auto_initialize=auto_initialize)
