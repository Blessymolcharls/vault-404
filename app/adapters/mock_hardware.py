"""Mock Hardware Adapter for The Inconvenient Vault.

Provides a thread-safe and async-safe software simulator fulfilling the
HardwareInterface contract without physical hardware or serial interfaces.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
)
from app.interfaces.hardware import HardwareEventCallback, HardwareInterface

logger = logging.getLogger("vault.adapters.mock_hardware")


class MockHardwareAdapter(HardwareInterface):
    """Thread-safe and async-safe virtual hardware emulator.

    Emulates physical peripherals including:
    - 16x2 / 20x4 Alphanumeric LCD display and status RGB LEDs
    - Solenoid / electromagnetic lock relay
    - Tamper alert switch and audible alarm siren/buzzer
    - Optical fingerprint sensor (AS608 / R503 emulator)
    - RFID reader (RC522 / PN532 emulator)
    - Magnetic reed door contact sensor
    """

    def __init__(self, auto_initialize: bool = False) -> None:
        """Initialize internal state of the mock hardware adapter.

        Args:
            auto_initialize: If True, immediately marks the hardware as initialized.
        """
        self._is_initialized: bool = auto_initialize
        self._is_locked: bool = True
        self._is_alarm_active: bool = False
        self._alarm_duration_ms: int = 0
        self._current_display: DisplayStatus = DisplayStatus(
            line1="SYSTEM READY",
            line2="AWAITING INIT",
            led_color=LedColor.OFF,
            buzzer=False,
            duration_ms=0,
        )
        self._listeners: List[HardwareEventCallback] = []
        self._event_history: List[HardwareEvent] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._door_open: bool = False

    # ========================================================================
    # State Inspection Properties (Read-Only)
    # ========================================================================

    @property
    def is_initialized(self) -> bool:
        """Return whether the hardware adapter is currently initialized."""
        return self._is_initialized

    @property
    def is_locked(self) -> bool:
        """Return the current solenoid/relay physical lock state."""
        return self._is_locked

    @property
    def is_alarm_active(self) -> bool:
        """Return whether the alarm siren/buzzer is actively firing."""
        return self._is_alarm_active

    @property
    def alarm_duration_ms(self) -> int:
        """Return the current configured alarm trigger duration in milliseconds."""
        return self._alarm_duration_ms

    @property
    def current_display(self) -> DisplayStatus:
        """Return the active display and LED status."""
        return self._current_display

    @property
    def is_door_open(self) -> bool:
        """Return the physical magnetic door reed sensor status."""
        return self._door_open

    @property
    def event_history(self) -> List[HardwareEvent]:
        """Return a copy of all dispatched hardware events."""
        return list(self._event_history)

    @property
    def listener_count(self) -> int:
        """Return the number of currently registered event listeners."""
        return len(self._listeners)

    # ========================================================================
    # HardwareInterface Contract Implementation
    # ========================================================================

    async def initialize(self) -> bool:
        """Initialize the mock hardware bus and peripheral state."""
        async with self._lock:
            if self._is_initialized:
                logger.warning("MockHardwareAdapter is already initialized.")
                return True

            logger.info("Initializing MockHardwareAdapter virtual peripherals...")
            self._is_initialized = True
            self._is_locked = True
            self._is_alarm_active = False
            self._alarm_duration_ms = 0
            self._current_display = DisplayStatus(
                line1="VAULT 404 READY",
                line2="AWAITING RFID",
                led_color=LedColor.BLUE,
                buzzer=False,
                duration_ms=0,
            )
            logger.info("MockHardwareAdapter initialized successfully. State: LOCKED, LED: BLUE")
            return True

    async def shutdown(self) -> None:
        """Gracefully power down virtual peripherals and release listeners."""
        async with self._lock:
            if not self._is_initialized:
                logger.warning("MockHardwareAdapter is already shut down.")
                return

            logger.info("Shutting down MockHardwareAdapter...")
            self._is_initialized = False
            self._is_alarm_active = False
            self._alarm_duration_ms = 0
            self._current_display = DisplayStatus(
                line1="SYSTEM OFF",
                line2="",
                led_color=LedColor.OFF,
                buzzer=False,
                duration_ms=0,
            )
            logger.info("MockHardwareAdapter shutdown complete.")

    def register_event_listener(self, callback: HardwareEventCallback) -> None:
        """Register an asynchronous callback to receive dispatched hardware events.

        Args:
            callback: Coroutine function accepting a HardwareEvent instance.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug(f"Registered event listener: {callback.__qualname__}")

    def unregister_event_listener(self, callback: HardwareEventCallback) -> bool:
        """Unregister a previously registered event listener.

        Args:
            callback: The callback to remove.

        Returns:
            bool: True if removed, False if not found.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)
            logger.debug(f"Unregistered event listener: {callback.__qualname__}")
            return True
        return False

    async def set_display(self, status: DisplayStatus) -> None:
        """Update the virtual alphanumeric display, status LED, and buzzer state.

        Args:
            status: DisplayStatus model containing text, color, and buzzer flags.

        Raises:
            RuntimeError: If the hardware adapter is not initialized.
        """
        if not self._is_initialized:
            raise RuntimeError("Cannot update display: MockHardwareAdapter is not initialized.")

        async with self._lock:
            self._current_display = status
            logger.info(
                f"[DISPLAY UPDATE] L1: '{status.line1}' | L2: '{status.line2}' | "
                f"LED: {status.led_color.value} | Buzzer: {status.buzzer} | Duration: {status.duration_ms}ms"
            )

    async def set_lock(self, locked: bool) -> bool:
        """Actuate the electronic lock mechanism and emit a status event.

        Args:
            locked: True to engage physical lock, False to disengage (unlock).

        Returns:
            bool: True confirming actuation success.

        Raises:
            RuntimeError: If the hardware adapter is not initialized.
        """
        if not self._is_initialized:
            raise RuntimeError("Cannot actuate lock: MockHardwareAdapter is not initialized.")

        async with self._lock:
            previous_state = self._is_locked
            self._is_locked = locked
            logger.info(f"[LOCK ACTUATION] Solenoid state changed: {'LOCKED' if locked else 'UNLOCKED'}")

            # Emit lock status event if state transitioned
            if previous_state != locked:
                event = HardwareEvent(
                    event_type=HardwareEventType.LOCK_STATUS_CHANGED,
                    payload={"locked": locked, "previous_state": previous_state},
                    source_id="MOCK_SOLENOID_RELAY",
                )
                await self._dispatch_event(event)

            return True

    async def enable_keypad(self, expected_pin_hash: str) -> bool:
        return True

    async def disable_keypad(self) -> bool:
        return True

    async def trigger_alarm(self, duration_ms: int) -> None:
        """Trigger the virtual audible alarm and strobe alert. Passing duration_ms <= 0 silences the alarm.

        Args:
            duration_ms: Duration in milliseconds for the alarm burst (or 0 to silence).

        Raises:
            RuntimeError: If the hardware adapter is not initialized.
        """
        if not self._is_initialized:
            raise RuntimeError("Cannot trigger alarm: MockHardwareAdapter is not initialized.")

        async with self._lock:
            if duration_ms <= 0:
                self._is_alarm_active = False
                self._alarm_duration_ms = 0
                logger.info("[ALARM SILENCED] Siren deactivated.")
            else:
                self._is_alarm_active = True
                self._alarm_duration_ms = duration_ms
                logger.warning(f"[ALARM TRIGGERED] Siren active for {duration_ms}ms!")

            event = HardwareEvent(
                event_type=HardwareEventType.ALARM_TRIGGERED,
                payload={"duration_ms": duration_ms, "triggered_at": datetime.now(timezone.utc).isoformat()},
                source_id="MOCK_ALARM_BUZZER",
            )
            await self._dispatch_event(event)

    def release(self) -> None:
        """Release mock hardware resources."""
        self._is_initialized = False
        self._listeners.clear()

    # ========================================================================
    # Programmatic Hardware Simulation Injection Hooks
    # ========================================================================

    async def simulate_rfid_scan(
        self,
        card_uid: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HardwareEvent:
        """Simulate a physical RFID/NFC card tap on the reader.

        Args:
            card_uid: Hexadecimal UID of the simulated RFID tag (e.g., 'E2806894').
            metadata: Optional additional metadata (card type, block data, RSSI).

        Returns:
            HardwareEvent: The dispatched event.
        """
        payload = {"card_uid": card_uid.upper()}
        if metadata:
            payload.update(metadata)

        event = HardwareEvent(
            event_type=HardwareEventType.RFID_SCANNED,
            payload=payload,
            source_id="MOCK_RC522_RFID",
        )
        logger.info(f"[SIMULATED RFID] Tag Scanned UID: {card_uid}")
        await self._dispatch_event(event)
        return event

    async def simulate_keypad_pin_result(self, result_str: str) -> HardwareEvent:
        event = HardwareEvent(
            event_type=HardwareEventType.KEYPAD_PIN_RESULT,
            payload={"result": result_str},
            source_id="MOCK_KEYPAD",
        )
        await self._dispatch_event(event)
        return event
    async def simulate_tamper(
        self,
        sensor: str = "ENCLOSURE_MICROSWITCH",
        description: str = "Physical chassis enclosure opened",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HardwareEvent:
        """Simulate a tamper trigger (optical sensor, vibration sensor, or chassis switch).

        Args:
            sensor: Identifier of the tamper sensor.
            description: Description of the detected breach event.
            metadata: Optional extra telemetry.

        Returns:
            HardwareEvent: The dispatched event.
        """
        payload: Dict[str, Any] = {
            "sensor": sensor,
            "description": description,
        }
        if metadata:
            payload.update(metadata)

        event = HardwareEvent(
            event_type=HardwareEventType.TAMPER_TRIGGERED,
            payload=payload,
            source_id="MOCK_TAMPER_SWITCH",
        )
        logger.warning(f"[SIMULATED TAMPER] Sensor: {sensor} | Breach: {description}")
        await self._dispatch_event(event)
        return event

    async def simulate_door_sensor(
        self,
        open_state: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HardwareEvent:
        """Simulate opening or closing of the heavy vault security door.

        Args:
            open_state: True if door opened, False if door closed.
            metadata: Optional sensor metadata.

        Returns:
            HardwareEvent: The dispatched event.
        """
        self._door_open = open_state
        event_type = (
            HardwareEventType.DOOR_OPENED if open_state else HardwareEventType.DOOR_CLOSED
        )
        payload: Dict[str, Any] = {"door_open": open_state}
        if metadata:
            payload.update(metadata)

        event = HardwareEvent(
            event_type=event_type,
            payload=payload,
            source_id="MOCK_DOOR_REED_SWITCH",
        )
        logger.info(f"[SIMULATED DOOR SENSOR] Door state: {'OPEN' if open_state else 'CLOSED'}")
        await self._dispatch_event(event)
        return event

    async def simulate_hardware_error(
        self,
        error_code: str,
        details: str,
        source_id: str = "MOCK_PERIPHERAL_BUS",
    ) -> HardwareEvent:
        """Simulate an unexpected bus failure, parity error, or peripheral disconnect.

        Args:
            error_code: String classification of the hardware error.
            details: Human-readable diagnostic details.
            source_id: Originating peripheral component name.

        Returns:
            HardwareEvent: The dispatched event.
        """
        event = HardwareEvent(
            event_type=HardwareEventType.HARDWARE_ERROR,
            payload={"error_code": error_code, "details": details},
            source_id=source_id,
        )
        logger.error(f"[SIMULATED HARDWARE ERROR] [{error_code}] {details} (Source: {source_id})")
        await self._dispatch_event(event)
        return event

    # ========================================================================
    # Internal Event Dispatcher with Error Isolation
    # ========================================================================

    async def _dispatch_event(self, event: HardwareEvent) -> None:
        """Dispatch a hardware event asynchronously to all registered listeners with error isolation.

        Args:
            event: HardwareEvent instance to broadcast.
        """
        self._event_history.append(event)
        if not self._listeners:
            return

        # Invoke all callbacks concurrently; protect against listener exceptions
        tasks = [listener(event) for listener in self._listeners]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for listener, result in zip(self._listeners, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Error in hardware event listener {getattr(listener, '__qualname__', str(listener))}: {result}",
                    exc_info=result,
                )
