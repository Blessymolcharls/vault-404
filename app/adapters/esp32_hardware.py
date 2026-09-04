"""ESP32 Serial Hardware Adapter for The Inconvenient Vault.

Implements the HardwareInterface over high-speed UART / USB serial
using framed, newline-delimited JSON commands and asynchronous telemetry dispatch.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import serial.tools.list_ports

from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
)
from app.interfaces.hardware import HardwareEventCallback, HardwareInterface

logger = logging.getLogger("vault.adapters.esp32")


class ESP32SerialAdapter(HardwareInterface):
    """Production Hardware Adapter bridging Python backend to ESP32 firmware over USB Serial."""

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        auto_reconnect: bool = True,
        timeout_seconds: float = 3.0,
    ) -> None:
        """Initialize the ESP32 Serial Adapter.

        Args:
            port: Serial COM port string (e.g., 'COM3' or '/dev/ttyUSB0'). If None, auto-discovers.
            baudrate: Serial communication baud rate (default: 115200).
            auto_reconnect: Whether to automatically attempt reconnection if disconnected.
            timeout_seconds: Communication timeout.
        """
        self._port = port
        self._baudrate = baudrate
        self._auto_reconnect = auto_reconnect
        self._timeout = timeout_seconds

        self._is_initialized = False
        self._is_locked = True
        self._is_alarm_active = False
        self._current_display = DisplayStatus(
            line1="VAULT 404", line2="CONNECTING...", led_color=LedColor.BLUE
        )
        self._listeners: List[HardwareEventCallback] = []

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._read_task: Optional[asyncio.Task[None]] = None
        self._write_lock = asyncio.Lock()

    # ========================================================================
    # State Inspection Properties
    # ========================================================================

    @property
    def is_initialized(self) -> bool:
        """Return whether serial communication with the ESP32 is established."""
        return self._is_initialized

    @property
    def is_locked(self) -> bool:
        """Return whether the vault physical solenoid is engaged."""
        return self._is_locked

    @property
    def is_alarm_active(self) -> bool:
        """Return whether the physical siren / alarm is active."""
        return self._is_alarm_active

    @property
    def current_display(self) -> DisplayStatus:
        """Return the current display status."""
        return self._current_display

    @property
    def port(self) -> Optional[str]:
        """Return the active or configured serial port."""
        return self._port

    # ========================================================================
    # Lifecycle & Connection Management
    # ========================================================================

    async def initialize(self) -> bool:
        """Discover and open the serial link to the ESP32, starting the background reader."""
        if self._is_initialized:
            logger.info(f"ESP32SerialAdapter already connected on port {self._port}.")
            return True

        target_port = self._port or self.discover_serial_port()
        if not target_port:
            logger.error("No valid ESP32 serial port detected or configured.")
            return False

        self._port = target_port
        try:
            import serial_asyncio

            logger.info(f"Connecting to ESP32 on {self._port} @ {self._baudrate} baud...")
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._port, baudrate=self._baudrate
            )
            self._is_initialized = True
            self._read_task = asyncio.create_task(self._rx_loop())

            # Send ping to verify bidirectional link
            await self._send_command({"cmd": "PING"})
            logger.info(f"Successfully established serial link with ESP32 on {self._port}.")
            return True
        except Exception as ex:
            logger.error(f"Failed to open serial port {self._port}: {ex}")
            self._is_initialized = False
            return False

    async def shutdown(self) -> None:
        """Gracefully release hardware resources and close the serial link."""
        self.release()

    def release(self) -> None:
        """Cleanly close the serial link and terminate the background reader loop."""
        self._is_initialized = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()

        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        logger.info("ESP32SerialAdapter released.")

    def close(self) -> None:
        """Alias for release."""
        self.release()

    @staticmethod
    def discover_serial_port() -> Optional[str]:
        """Auto-detect connected ESP32 / CP210x / CH340 / FTDI USB-UART bridge devices."""
        ports = list(serial.tools.list_ports.comports())
        esp_keywords = ["CP210", "CH340", "FTDI", "UART", "USB Serial", "ESP32"]

        for p in ports:
            desc = f"{p.description} {p.manufacturer or ''}"
            for kw in esp_keywords:
                if kw.lower() in desc.lower():
                    logger.info(f"Auto-detected ESP32 device on port {p.device} ({p.description})")
                    return p.device

        # If only one serial port is present, return it
        if len(ports) == 1:
            logger.info(f"Defaulting to sole available serial port: {ports[0].device}")
            return ports[0].device

        return None

    # ========================================================================
    # Hardware Actuation Methods (Host-to-ESP32 Commands)
    # ========================================================================

    async def set_display(self, status: DisplayStatus) -> bool:
        """Send SET_DISPLAY command to update physical LCD and RGB LED."""
        self._current_display = status
        cmd = {
            "cmd": "SET_DISPLAY",
            "line1": status.line1,
            "line2": status.line2,
            "led": status.led_color.value,
            "buzzer": status.buzzer,
            "duration_ms": status.duration_ms or 500,
        }
        return await self._send_command(cmd)

    async def set_lock(self, locked: bool, duration_ms: int = 5000) -> bool:
        """Send command to actuate physical servo lock."""
        self._is_locked = locked
        if locked:
            cmd = {"cmd": "SET_LOCK", "command": "COMMAND_LOCK", "state": "LOCKED"}
        else:
            cmd = {
                "cmd": "COMMAND_UNLOCK",
                "command": "COMMAND_UNLOCK",
                "state": "UNLOCKED",
                "parameters": {"duration_ms": duration_ms},
            }
        return await self._send_command(cmd)

    async def ping(self) -> bool:
        """Send PING command to verify ESP32 communication."""
        return await self._send_command({"cmd": "PING", "command": "PING"})

    async def enable_keypad(self, expected_pin_hash: str) -> bool:
        cmd = {"cmd": "ENABLE_KEYPAD", "command": "ENABLE_KEYPAD", "expected_pin_hash": expected_pin_hash}
        return await self._send_command(cmd)

    async def disable_keypad(self) -> bool:
        cmd = {"cmd": "DISABLE_KEYPAD", "command": "DISABLE_KEYPAD"}
        return await self._send_command(cmd)

    async def set_password(self, password: str) -> bool:
        """Send SET_PASSWORD command to update the physical hardware password."""
        cmd = {"cmd": "SET_PASSWORD", "command": "SET_PASSWORD", "password": password}
        return await self._send_command(cmd)

    async def trigger_alarm(self, duration_ms: int) -> None:
        """Send TRIGGER_ALARM command to activate or silence the siren."""
        self._is_alarm_active = duration_ms > 0
        cmd = {
            "cmd": "TRIGGER_ALARM",
            "command": "TRIGGER_ALARM",
            "duration_ms": duration_ms,
            "parameters": {"duration_ms": duration_ms},
        }
        await self._send_command(cmd)

    async def drive_motors(
        self, direction: str = "FORWARD", duration_ms: int = 3000, speed: int = 255
    ) -> bool:
        """Send DRIVE_MOTORS command to activate 4-motor getaway chassis."""
        cmd = {
            "cmd": "DRIVE_MOTORS",
            "command": "DRIVE_MOTORS",
            "direction": direction.upper(),
            "duration_ms": duration_ms,
            "speed": max(0, min(255, speed)),
            "parameters": {
                "direction": direction.upper(),
                "duration_ms": duration_ms,
                "speed": max(0, min(255, speed)),
            },
        }
        return await self._send_command(cmd)

    async def stop_motors(self) -> bool:
        """Send STOP_MOTORS command to halt 4-motor getaway chassis."""
        cmd = {"cmd": "STOP_MOTORS", "command": "STOP_MOTORS"}
        return await self._send_command(cmd)

    # ========================================================================
    # Event Listener Registration
    # ========================================================================

    def register_event_listener(self, callback: HardwareEventCallback) -> None:
        """Register an async callback for incoming hardware events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_event_listener(self, callback: HardwareEventCallback) -> bool:
        """Unregister a hardware event callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)
            return True
        return False

    # ========================================================================
    # Serial Protocol I/O & Background Parser Loop
    # ========================================================================

    async def _send_command(self, cmd_dict: Dict[str, Any]) -> bool:
        """Encode and transmit a newline-terminated JSON command to the ESP32."""
        if not self._is_initialized or not self._writer:
            logger.warning(f"Cannot send command {cmd_dict.get('cmd')}: Serial not initialized.")
            return False

        payload_bytes = (json.dumps(cmd_dict) + "\n").encode("utf-8")
        async with self._write_lock:
            try:
                self._writer.write(payload_bytes)
                await self._writer.drain()
                return True
            except Exception as ex:
                logger.error(f"Serial write error: {ex}")
                return False

    async def _rx_loop(self) -> None:
        """Asynchronous background loop parsing newline-terminated telemetry JSON from the ESP32."""
        logger.debug("ESP32 Serial RX loop started.")
        while self._is_initialized and self._reader:
            try:
                raw_line = await self._reader.readline()
                if not raw_line:
                    await asyncio.sleep(0.01)
                    continue

                line_str = raw_line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                self._process_incoming_json(line_str)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Error in Serial RX loop: {ex}")
                await asyncio.sleep(0.1)

    def _process_incoming_json(self, json_str: str) -> None:
        """Parse incoming JSON line, map event type, and dispatch HardwareEvent."""
        try:
            data = json.loads(json_str)
        except Exception:
            logger.debug(f"Ignoring non-JSON serial line: {json_str}")
            return

        event_name = data.get("event")
        payload = data.get("payload", {})

        if not event_name:
            return

        # Map ESP32 wire event name to HardwareEventType enum
        event_type_map = {
            "RFID_SCANNED": HardwareEventType.RFID_SCANNED,
            "FINGERPRINT_CAPTURED": HardwareEventType.FINGERPRINT_SCANNED,
            "FINGERPRINT_SCANNED": HardwareEventType.FINGERPRINT_SCANNED,
            "KEYPAD_STATUS": HardwareEventType.KEYPAD_STATUS,
            "KEYPAD_PIN_RESULT": HardwareEventType.KEYPAD_PIN_RESULT,
            "KEYPAD_PIN_SUBMITTED": HardwareEventType.KEYPAD_PIN_RESULT,
            "KEYPAD_KEY_PRESSED": HardwareEventType.KEYPAD_STATUS,
            "KEYPAD_CLEARED": HardwareEventType.KEYPAD_STATUS,
            "LOCK_STATUS_REPORT": HardwareEventType.LOCK_STATUS_CHANGED,
            "LOCK_CONFIRMED": HardwareEventType.LOCK_STATUS_CHANGED,
            "TAMPER_TRIGGERED": HardwareEventType.TAMPER_TRIGGERED,
            "TAMPER_DETECTED": HardwareEventType.TAMPER_TRIGGERED,
            "MOTOR_ACTIVATED": HardwareEventType.MOTOR_ACTIVATED,
            "MOTOR_STATUS": HardwareEventType.MOTOR_ACTIVATED,
            "MOTOR_STOPPED": HardwareEventType.MOTOR_STOPPED,
            "HARDWARE_ERROR": HardwareEventType.HARDWARE_ERROR,
        }

        if event_name in ("LOCK_STATUS_REPORT", "LOCK_CONFIRMED"):
            if "locked" in payload:
                self._is_locked = bool(payload["locked"])

        hw_type = event_type_map.get(event_name)
        if hw_type:
            event = HardwareEvent(
                event_type=hw_type,
                payload=payload,
                source_id=f"ESP32_{self._port}",
            )
            asyncio.create_task(self._dispatch_event(event))
        elif event_name == "PONG":
            logger.debug(f"Received PONG from ESP32: {payload}")
            if "locked" in payload:
                self._is_locked = bool(payload["locked"])
        elif event_name == "HARDWARE_BOOT":
            logger.info(f"ESP32 reported boot status: {payload}")

    async def _dispatch_event(self, event: HardwareEvent) -> None:
        """Dispatch hardware event to all registered listeners asynchronously."""
        if not self._listeners:
            return

        tasks = [listener(event) for listener in self._listeners]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for listener, result in zip(self._listeners, results):
            if isinstance(result, Exception):
                logger.error(f"Exception in hardware listener {listener}: {result}")
