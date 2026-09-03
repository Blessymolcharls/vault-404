#!/usr/bin/env python3
"""Interactive Terminal Test Harness for The Inconvenient Vault Hardware Simulator.

Provides real-time terminal visualization of virtual LCD displays, LED status indicators,
electronic lock states, alarm triggers, and allows triggering simulated hardware events.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import List

# Ensure UTF-8 output encoding for cross-platform terminal compatibility (especially Windows cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.adapters.mock_hardware import MockHardwareAdapter
from app.core.types import (
    DisplayStatus,
    HardwareEvent,
    HardwareEventType,
    LedColor,
)

# ANSI Color Codes for terminal UI
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_BLUE = "\033[44m"
BG_BLACK = "\033[40m"
BG_DARK = "\033[100m"

COLOR_MAP = {
    LedColor.OFF: f"{DIM}[OFF]{RESET}",
    LedColor.RED: f"{RED}[RED]{RESET}",
    LedColor.GREEN: f"{GREEN}[GREEN]{RESET}",
    LedColor.BLUE: f"{BLUE}[BLUE]{RESET}",
    LedColor.YELLOW: f"{YELLOW}[YELLOW]{RESET}",
    LedColor.PURPLE: f"{MAGENTA}[PURPLE]{RESET}",
    LedColor.CYAN: f"{CYAN}[CYAN]{RESET}",
    LedColor.WHITE: f"{WHITE}[WHITE]{RESET}",
    LedColor.ORANGE: f"{YELLOW}[ORANGE]{RESET}",
}


class TerminalSimulatorHarness:
    """Terminal harness managing MockHardwareAdapter lifecycle and user interaction."""

    def __init__(self) -> None:
        self.adapter = MockHardwareAdapter()
        self.event_log: List[str] = []
        self.max_log_entries = 8

    def _on_event_received(self, event: HardwareEvent) -> None:
        """Format and append dispatched hardware events to the live log buffer."""
        ts = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
        payload_str = ", ".join(f"{k}={v}" for k, v in event.payload.items())
        log_line = f"{CYAN}[{ts}]{RESET} {BOLD}{event.event_type.value}{RESET} ({event.source_id or 'N/A'}): {payload_str}"
        self.event_log.append(log_line)
        if len(self.event_log) > self.max_log_entries:
            self.event_log.pop(0)

    async def async_event_listener(self, event: HardwareEvent) -> None:
        """Async callback registered with MockHardwareAdapter."""
        self._on_event_received(event)

    def render_ui(self) -> None:
        """Render the virtual hardware display, lock state, and event log in the terminal."""
        disp = self.adapter.current_display
        led_display = COLOR_MAP.get(disp.led_color, f"[{disp.led_color.value}]")
        lock_status = (
            f"{RED}{BOLD}[LOCKED (LOCKED)]{RESET}"
            if self.adapter.is_locked
            else f"{GREEN}{BOLD}[UNLOCKED (OPEN)]{RESET}"
        )
        alarm_status = (
            f"{RED}{BOLD}[ALARM ACTIVE ({self.adapter.alarm_duration_ms}ms)]{RESET}"
            if self.adapter.is_alarm_active
            else f"{DIM}[SILENT]{RESET}"
        )
        buzzer_status = (
            f"{YELLOW}{BOLD}[BUZZER ACTIVE]{RESET}"
            if disp.buzzer
            else f"{DIM}[BUZZER OFF]{RESET}"
        )
        door_status = (
            f"{YELLOW}{BOLD}[DOOR OPEN]{RESET}"
            if self.adapter.is_door_open
            else f"{DIM}[DOOR CLOSED]{RESET}"
        )

        l1 = disp.line1.ljust(20)[:20]
        l2 = disp.line2.ljust(20)[:20]

        print("\n" + "=" * 70)
        print(f"{BOLD}{CYAN}      THE INCONVENIENT VAULT -- HARDWARE SIMULATOR (STEP 2){RESET}")
        print("=" * 70)
        print(f"  Status: {'INITIALIZED' if self.adapter.is_initialized else 'OFFLINE'} | Lock: {lock_status} | Door: {door_status}")
        print(f"  Indicators: LED {led_display} | Buzzer: {buzzer_status} | Siren: {alarm_status}")
        print("-" * 70)
        print(f"  {BG_BLUE}{WHITE}{BOLD} +----------------------+ {RESET}")
        print(f"  {BG_BLUE}{WHITE}{BOLD} | > {l1:<20} | {RESET}  <-- 16x2 / 20x4 Alphanumeric LCD")
        print(f"  {BG_BLUE}{WHITE}{BOLD} | > {l2:<20} | {RESET}")
        print(f"  {BG_BLUE}{WHITE}{BOLD} +----------------------+ {RESET}")
        print("-" * 70)
        print(f"{BOLD}  Recent Hardware Event Bus Logs:{RESET}")
        if not self.event_log:
            print(f"  {DIM}(No events dispatched yet){RESET}")
        else:
            for entry in self.event_log:
                print(f"  {entry}")
        print("=" * 70)

    async def run_smoke_test(self) -> bool:
        """Run an automated non-interactive verification sequence."""
        print(f"{CYAN}--- Starting Automated Simulator Smoke Test ---{RESET}")
        await self.adapter.initialize()
        self.adapter.register_event_listener(self.async_event_listener)

        # 1. Update Display
        await self.adapter.set_display(
            DisplayStatus(
                line1="SCAN RFID CARD",
                line2="STEP 1 OF 5",
                led_color=LedColor.BLUE,
                buzzer=False,
            )
        )
        assert self.adapter.current_display.line1 == "SCAN RFID CARD"

        # 2. Simulate RFID Scan
        rfid_event = await self.adapter.simulate_rfid_scan("E2806894")
        assert rfid_event.event_type == HardwareEventType.RFID_SCANNED
        assert rfid_event.payload["card_uid"] == "E2806894"

        # 3. Simulate Fingerprint
        fp_event = await self.adapter.simulate_keypad_pin_result(finger_id=1, matched=True, confidence=0.98)
        assert fp_event.event_type == HardwareEventType.KEYPAD_PIN_RESULT

        # 4. Simulate Tamper
        tamper_event = await self.adapter.simulate_tamper()
        assert tamper_event.event_type == HardwareEventType.TAMPER_TRIGGERED

        # 5. Lock Actuation
        await self.adapter.set_lock(False)
        assert self.adapter.is_locked is False

        # 6. Alarm
        await self.adapter.trigger_alarm(3000)
        assert self.adapter.is_alarm_active is True

        # Render final smoke state
        self.render_ui()
        print(f"{GREEN}✓ Automated smoke test passed successfully! ({len(self.event_log)} events received){RESET}")
        await self.adapter.shutdown()
        return True

    async def run_interactive(self) -> None:
        """Run the interactive terminal menu loop."""
        await self.adapter.initialize()
        self.adapter.register_event_listener(self.async_event_listener)

        # Set initial display
        await self.adapter.set_display(
            DisplayStatus(
                line1="VAULT 404 READY",
                line2="TAP RFID CARD",
                led_color=LedColor.BLUE,
                buzzer=False,
            )
        )

        while True:
            self.render_ui()
            print(f"{BOLD}Simulate Hardware Action:{RESET}")
            print("  [1]  Tap Authorized RFID Card (E2806894)")
            print("  [2]  Tap Unauthorized RFID Card (DEADBEEF)")
            print("  [3]  Enter Custom RFID UID")
            print("  [4]  Scan Fingerprint (Matched - ID: 1)")
            print("  [5]  Scan Fingerprint (Failed / Rejected)")
            print("  [6]  Trigger Tamper Detection Switch")
            print("  [7]  Actuate Solenoid: UNLOCK")
            print("  [8]  Actuate Solenoid: LOCK")
            print("  [9]  Toggle Door Sensor (Open / Close)")
            print("  [10] Update Custom Display & LED")
            print("  [11] Trigger Alarm Buzzer (2000ms)")
            print("  [12] Simulate Peripheral Hardware Error")
            print("  [0]  Exit Simulator")

            choice = await asyncio.to_thread(input, f"\n{BOLD}Select option (0-12): {RESET}")
            choice = choice.strip()

            if choice == "0":
                print(f"\n{YELLOW}Shutting down hardware simulator...{RESET}")
                await self.adapter.shutdown()
                print(f"{GREEN}Simulator exited cleanly.{RESET}")
                break

            elif choice == "1":
                await self.adapter.simulate_rfid_scan("E2806894")
                await self.adapter.set_display(
                    DisplayStatus(line1="RFID ACCEPTED", line2="ID: E2806894", led_color=LedColor.GREEN, buzzer=True)
                )

            elif choice == "2":
                await self.adapter.simulate_rfid_scan("DEADBEEF")
                await self.adapter.set_display(
                    DisplayStatus(line1="RFID DENIED", line2="INVALID CARD", led_color=LedColor.RED, buzzer=True)
                )

            elif choice == "3":
                custom_uid = await asyncio.to_thread(input, "Enter custom RFID UID (hex): ")
                custom_uid = custom_uid.strip().upper() or "A1B2C3D4"
                await self.adapter.simulate_rfid_scan(custom_uid)

            elif choice == "4":
                await self.adapter.simulate_keypad_pin_result(finger_id=1, matched=True, confidence=0.97)
                await self.adapter.set_display(
                    DisplayStatus(line1="FINGERPRINT OK", line2="MATCH 97%", led_color=LedColor.GREEN, buzzer=True)
                )

            elif choice == "5":
                await self.adapter.simulate_keypad_pin_result(finger_id=99, matched=False, confidence=0.21)
                await self.adapter.set_display(
                    DisplayStatus(line1="FP REJECTED", line2="NO MATCH", led_color=LedColor.RED, buzzer=True)
                )

            elif choice == "6":
                await self.adapter.simulate_tamper(sensor="OPTICAL_LIGHT_SENSOR", description="Enclosure opened")
                await self.adapter.trigger_alarm(5000)
                await self.adapter.set_display(
                    DisplayStatus(line1="TAMPER ALERT!", line2="CHASSIS BREACH", led_color=LedColor.RED, buzzer=True)
                )

            elif choice == "7":
                await self.adapter.set_lock(False)
                await self.adapter.set_display(
                    DisplayStatus(line1="SOLENOID RELEASED", line2="VAULT UNLOCKED", led_color=LedColor.GREEN)
                )

            elif choice == "8":
                await self.adapter.set_lock(True)
                await self.adapter.set_display(
                    DisplayStatus(line1="SOLENOID ENGAGED", line2="VAULT LOCKED", led_color=LedColor.BLUE)
                )

            elif choice == "9":
                new_door_state = not self.adapter.is_door_open
                await self.adapter.simulate_door_sensor(new_door_state)

            elif choice == "10":
                l1 = await asyncio.to_thread(input, "Line 1 text (max 20): ")
                l2 = await asyncio.to_thread(input, "Line 2 text (max 20): ")
                color_name = await asyncio.to_thread(input, "LED Color (RED/GREEN/BLUE/YELLOW/PURPLE/CYAN/WHITE/OFF): ")
                color_val = color_name.strip().upper() or "BLUE"
                try:
                    led_c = LedColor(color_val)
                except ValueError:
                    led_c = LedColor.BLUE
                await self.adapter.set_display(DisplayStatus(line1=l1, line2=l2, led_color=led_c))

            elif choice == "11":
                await self.adapter.trigger_alarm(2000)

            elif choice == "12":
                await self.adapter.simulate_hardware_error(
                    error_code="ERR_UART_PARITY",
                    details="UART parity frame error on AS608 optical fingerprint reader",
                )

            else:
                print(f"{RED}Invalid selection. Please choose an option from the menu.{RESET}")

            # Brief pause to let any async background tasks update
            await asyncio.sleep(0.05)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="The Inconvenient Vault - Hardware Simulator Interactive CLI"
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run non-interactive automated smoke test sequence and exit.",
    )
    args = parser.parse_args()

    harness = TerminalSimulatorHarness()
    if args.smoke_test:
        success = asyncio.run(harness.run_smoke_test())
        sys.exit(0 if success else 1)
    else:
        try:
            asyncio.run(harness.run_interactive())
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Interrupted by user. Exiting...{RESET}")
            sys.exit(0)


if __name__ == "__main__":
    main()
