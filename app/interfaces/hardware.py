"""Abstract hardware interface contract for The Inconvenient Vault.

This abstraction completely isolates the high-level authentication state engine
from physical sensors, microcontrollers (Arduino/ESP32), serial interfaces (PySerial),
and low-level actuator circuitry.
"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable
from app.core.types import DisplayStatus, HardwareEvent

# Type alias for asynchronous event listener callbacks
HardwareEventCallback = Callable[[HardwareEvent], Awaitable[None]]


class HardwareInterface(ABC):
    """Abstract Base Class defining the contract for vault hardware abstraction layers.

    Implementations can be physical serial adapters (e.g. PySerial bridging to Arduino/ESP32),
    mock software emulators for testing, or network-bridged remote peripherals.
    """

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the hardware interface, establish communication, and verify peripherals.

        Returns:
            bool: True if initialization was successful and all required peripherals
                  are ready; False otherwise.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully release hardware resources, close ports, and power down indicators."""
        pass

    @abstractmethod
    def register_event_listener(self, callback: HardwareEventCallback) -> None:
        """Register an asynchronous callback listener to receive dispatched hardware events.

        Args:
            callback: Coroutine function accepting a HardwareEvent instance.
        """
        pass

    @abstractmethod
    async def set_display(self, status: DisplayStatus) -> None:
        """Update the physical LCD/OLED display text, indicator LED color, and buzzer state.

        Args:
            status: DisplayStatus model containing text lines, LED color, and buzzer config.
        """
        pass

    @abstractmethod
    async def set_lock(self, locked: bool) -> bool:
        """Engage or disengage the physical locking mechanism (solenoid / electromagnetic lock).

        Args:
            locked: True to engage lock (secure vault), False to disengage (unlock vault).

        Returns:
            bool: True if the lock actuation succeeded and the physical sensor confirms state.
        """
        pass

    @abstractmethod
    async def trigger_alarm(self, duration_ms: int) -> None:
        ...

    async def enable_keypad(self, expected_pin_hash: str) -> bool:
        return True

    async def disable_keypad(self) -> bool:
        return True

    async def set_password(self, password: str) -> bool:
        """Set the active hardware password on the microcontroller."""
        return True

    async def drive_motors(
        self, direction: str = "FORWARD", duration_ms: int = 3000, speed: int = 255
    ) -> bool:
        """Actuate the 4-motor getaway chassis.

        Args:
            direction: Movement vector ("FORWARD", "BACKWARD", "LEFT", "RIGHT").
            duration_ms: Duration in milliseconds before stopping (0 for continuous).
            speed: Motor PWM duty cycle (0-255).

        Returns:
            bool: True if motor command was transmitted and accepted.
        """
        return True

    async def stop_motors(self) -> bool:
        """Halt all getaway chassis motors immediately.

        Returns:
            bool: True if stop command was transmitted.
        """
        return True
