"""PC-side safety state tracking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SafetyState(str, Enum):
    SAFE = "SAFE"
    ARM_PENDING = "ARM_PENDING"
    NORMAL = "NORMAL"
    DEBUG = "DEBUG"


@dataclass
class SafetyMonitor:
    """Track communication and controller safety state."""

    state: SafetyState = SafetyState.SAFE
    armed: bool = False
    config_accepted: bool = False
    last_drive_tx_ms: int = 0
    last_rx_ms: int = 0
    last_valid_telemetry_ms: int = 0
    last_telemetry_seq: int | None = None
    warning: bool = False
    stopped_by_timeout: bool = False
    fault: str | None = None
    stale_telemetry_count: int = 0

    def apply_config(self, *, preserve_fault: bool = False) -> None:
        """A sent config starts SAFE and must be acknowledged before ARM."""
        previous_fault = self.fault
        self.state = SafetyState.SAFE
        self.armed = False
        self.config_accepted = False
        self.last_telemetry_seq = None
        self.warning = False
        self.stopped_by_timeout = False
        self.fault = previous_fault if preserve_fault else None
        self.stale_telemetry_count = 0

    def mark_config_accepted(self) -> None:
        """Record that the ESP32 accepted the active config."""
        self.config_accepted = True

    def request_arm(self, now_ms: int) -> None:
        """Wait for ESP32 arm_ack before allowing NORMAL drive output."""
        self.state = SafetyState.ARM_PENDING
        self.armed = False
        self.last_drive_tx_ms = now_ms
        self.warning = False
        self.stopped_by_timeout = False
        self.fault = None

    def arm(self, now_ms: int, debug: bool = False) -> None:
        """Enter NORMAL or DEBUG only after explicit user action."""
        self.state = SafetyState.DEBUG if debug else SafetyState.NORMAL
        self.armed = True
        self.config_accepted = True
        self.last_drive_tx_ms = now_ms
        self.last_rx_ms = now_ms
        self.last_valid_telemetry_ms = now_ms
        self.last_telemetry_seq = None
        self.warning = False
        self.stopped_by_timeout = False
        self.fault = None
        self.stale_telemetry_count = 0

    def confirm_arm(self, now_ms: int, debug: bool = False) -> bool:
        """Accept arm_ack only while an explicit ARM request is pending."""
        if self.state != SafetyState.ARM_PENDING:
            return False
        self.arm(now_ms, debug=debug)
        return True

    def disarm(self, reason: str | None = None) -> None:
        """Force SAFE and require a new ARM before driving."""
        previous_fault = self.fault
        was_safe = self.state == SafetyState.SAFE and not self.armed
        self.state = SafetyState.SAFE
        self.armed = False
        self.warning = False
        self.stopped_by_timeout = False
        # Once an event forces SAFE, later consequences such as the DISARM ACK
        # must not erase the first actionable root cause. A new config/ARM
        # attempt explicitly starts a new diagnostic epoch and clears it.
        self.fault = previous_fault if was_safe and previous_fault is not None else reason

    def record_drive(self, now_ms: int) -> None:
        """Record a valid outgoing drive command."""
        self.last_drive_tx_ms = now_ms
        self.warning = False
        self.stopped_by_timeout = False

    def record_rx(self, now_ms: int) -> None:
        """Record any valid ESP32 serial message."""
        self.last_rx_ms = now_ms

    def record_telemetry(self, now_ms: int, seq: int | None = None) -> bool:
        """Record fresh telemetry; ignore duplicates and reject regressions."""
        self.record_rx(now_ms)
        if seq is not None and self.last_telemetry_seq is not None and seq < self.last_telemetry_seq:
            self.disarm("telemetry sequence regression")
            return False
        if seq is not None and seq == self.last_telemetry_seq:
            # A duplicate packet is stale data. It is not by itself fatal, but
            # it must not refresh the telemetry watchdog.
            self.stale_telemetry_count += 1
            return False
        if seq is not None:
            self.last_telemetry_seq = seq
        self.last_valid_telemetry_ms = now_ms
        self.warning = False
        self.stopped_by_timeout = False
        return True

    def update_timeout(self, now_ms: int) -> str | None:
        """Apply 200/300/500 ms timeout behavior."""
        if self.state == SafetyState.ARM_PENDING:
            age = now_ms - self.last_drive_tx_ms
            if age >= 500:
                self.disarm("arm ack timeout")
                return "safe"
            return None
        if not self.armed:
            return None
        tx_age = now_ms - self.last_drive_tx_ms
        rx_age = now_ms - self.last_valid_telemetry_ms
        age = max(tx_age, rx_age)
        if age >= 500:
            self.disarm("telemetry timeout" if rx_age >= tx_age else "drive tx timeout")
            return "safe"
        if age >= 300:
            self.stopped_by_timeout = True
            return "stop"
        if age >= 200:
            self.warning = True
            return "warn"
        return None

    def controller_disconnected(self) -> None:
        """Immediate safe behavior for joystick loss."""
        self.disarm("controller disconnected")
