"""Domain types, enums, and Pydantic models for The Inconvenient Vault."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VaultState(str, Enum):
    """Finite State Machine states representing the authentication stages of the vault."""

    IDLE = "IDLE"
    AWAITING_RFID = "AWAITING_RFID"
    AWAITING_FACE = "AWAITING_FACE"
    AWAITING_KEYPAD_PIN = "AWAITING_KEYPAD_PIN"
    AWAITING_VOICE = "AWAITING_VOICE"
    UNLOCKED = "UNLOCKED"
    LOCKOUT = "LOCKOUT"
    ERROR = "ERROR"


class HardwareEventType(str, Enum):
    """Categorized hardware event types emitted by peripheral microcontrollers and sensors."""

    # RFID Events
    RFID_SCANNED = "RFID_SCANNED"

    # Keypad Events
    KEYPAD_STATUS = "KEYPAD_STATUS"
    KEYPAD_PIN_RESULT = "KEYPAD_PIN_RESULT"

    # Lock & Mechanism Events
    LOCK_STATUS_CHANGED = "LOCK_STATUS_CHANGED"
    LOCK_ENGAGED = "LOCK_ENGAGED"
    LOCK_DISENGAGED = "LOCK_DISENGAGED"
    DOOR_OPENED = "DOOR_OPENED"
    DOOR_CLOSED = "DOOR_CLOSED"

    # Tamper & Alarm Events
    TAMPER_TRIGGERED = "TAMPER_TRIGGERED"
    ALARM_TRIGGERED = "ALARM_TRIGGERED"

    # Interactive & Sensor Triggers
    BUTTON_PRESSED = "BUTTON_PRESSED"
    PROXIMITY_DETECTED = "PROXIMITY_DETECTED"

    # Error Events
    HARDWARE_ERROR = "HARDWARE_ERROR"
    COMMUNICATION_ERROR = "COMMUNICATION_ERROR"


class LedColor(str, Enum):
    """Standardized LED status indicator colors."""

    OFF = "OFF"
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    YELLOW = "YELLOW"
    PURPLE = "PURPLE"
    CYAN = "CYAN"
    WHITE = "WHITE"
    ORANGE = "ORANGE"


class HardwareEvent(BaseModel):
    """Immutable data envelope representing an asynchronous event from the hardware layer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the hardware event was generated",
    )
    event_type: HardwareEventType = Field(
        ...,
        description="Classification of the hardware event",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured payload containing sensor readings, identifiers, or error messages",
    )
    source_id: Optional[str] = Field(
        default=None,
        description="Identifier of the specific hardware module or peripheral port",
    )


class DisplayStatus(BaseModel):
    """Configuration payload for the physical 16x2 / 20x4 alphanumeric display, status LEDs, and buzzer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    line1: str = Field(
        default="",
        max_length=20,
        description="Primary display text line (truncated to fit alphanumeric LCD/OLED)",
    )
    line2: str = Field(
        default="",
        max_length=20,
        description="Secondary display text line",
    )
    led_color: LedColor = Field(
        default=LedColor.OFF,
        description="Status indicator LED color",
    )
    buzzer: bool = Field(
        default=False,
        description="Flag to trigger an audible feedback chirp or tone",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Duration in milliseconds for the alert or tone pattern (0 = permanent/until next update)",
    )

    @field_validator("led_color", mode="before")
    @classmethod
    def parse_led_color(cls, v: Any) -> LedColor:
        """Parse string values into valid LedColor enum members."""
        if isinstance(v, str):
            try:
                return LedColor(v.upper())
            except ValueError:
                raise ValueError(f"Invalid LED color '{v}'. Allowed colors: {[c.value for c in LedColor]}")
        return v
