"""ESP32-free simulation backend.

The simulator intentionally mirrors the public JSON/NDJSON behavior of the
MCB44 firmware closely enough that PC-side code can exercise the same protocol
path without a physical ESP32.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from math import copysign, isfinite
from typing import Any, Callable, Mapping


def _utc_now_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass
class _RngNamespace:
    """Small typed holder for deterministic fault decisions."""

    rng: random.Random


@dataclass
class SimulatedFaultProfile:
    """Injectable failure modes for deterministic fake-device tests."""

    seed: int | None = None
    packet_drop_probability: float = 0.0
    response_delay_ms: int = 0
    malformed_json_count: int = 0
    telemetry_stop: bool = False
    command_receive_stop_after_ms: int | None = None
    disconnect_after_ms: int | None = None
    reboot_after_ms: int | None = None
    hello_ack: bool = True
    config_ack_ok: bool = True
    arm_ack_ok: bool = True
    telemetry_seq_stale: bool = False
    telemetry_seq_regression_count: int = 0
    explicit_fault: str | None = None
    explicit_fault_once: bool = True
    explicit_fault_flags: int = 1
    explicit_fault_after_arm: bool = True
    encoder_anomaly: bool = False
    rpm_stuck: bool = False
    rpm_stuck_value: float | list[float] | None = None
    servo_stuck: bool = False
    servo_stuck_value: float | list[float] | None = None
    _namespace: _RngNamespace = field(default_factory=lambda: _RngNamespace(rng=random.Random()), init=False, repr=False)

    def __post_init__(self) -> None:
        self._namespace.rng = random.Random(self.seed)

    @property
    def rng(self) -> random.Random:
        return self._namespace.rng


FakeResponse = dict[str, Any] | bytes
COMMAND_STOP_MS = 300
COMMAND_SAFE_MS = 500
FAULT_COMMAND_TIMEOUT = 1 << 5


@dataclass
class SimulatedEsp32:
    """Stateful MCB44/ESP32 simulator for protocol and motion testing."""

    encoder_count: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    wheel_rpm: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    motor_pwm: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    servo_deg: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    commanded_drive_target: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    commanded_servo_deg: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    seq: int = 0
    armed: bool = False
    state: str = "SAFE"
    config_revision: int = 1
    last_drive_seq: int = 0
    node_id: str = "mcb44_drive_main"
    role: str = "drive"
    board: str = "MCB44"
    firmware: str = "mcb44_4wis"
    fw_version: str = "fake-v1"
    pca9685_ok: bool = True
    pca9685_address: int = 64
    faults: SimulatedFaultProfile = field(default_factory=SimulatedFaultProfile)
    clock_ms: Callable[[], int] = field(default=_utc_now_ms, repr=False, compare=False)
    processed_command_count: int = 0
    last_command_rx_ms: int | None = None
    reboot_count: int = 0
    event_log: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _start_time_ms: int = field(default=0, init=False, repr=False)
    _manual_disconnect: bool = field(default=False, init=False)
    _manual_command_stop: bool = field(default=False, init=False)
    _pending_reboot: bool = field(default=False, init=False)
    _last_telemetry_seq: int | None = field(default=None, init=False)
    _last_reconnect_seq: int = field(default=0, init=False)
    _scheduled_reboot_consumed: bool = field(default=False, init=False)
    _packet_drop_active: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._start_time_ms = int(self.clock_ms())

    def disconnect(self) -> None:
        """Force this device to stop answering any message."""
        self._manual_disconnect = True

    def reconnect(self, now_ms: int | None = None) -> None:
        """Restore normal message handling after manual disconnect."""
        self._manual_disconnect = False
        self._manual_command_stop = False
        self._start_time_ms = self._resolve_now(now_ms)
        self._last_reconnect_seq += 1
        self._pending_reboot = False

    def stop_command_reception(self) -> None:
        """Temporarily ignore all commands."""
        self._manual_command_stop = True

    def resume_command_reception(self) -> None:
        """Resume command acceptance after a command stop fault."""
        self._manual_command_stop = False

    def request_reboot(self) -> None:
        """Trigger a firmware reboot on next protocol message."""
        self._pending_reboot = True

    def activate_packet_drop(self) -> None:
        """Enable randomized response loss after deterministic setup/ARM."""
        self._packet_drop_active = True

    def deactivate_packet_drop(self) -> None:
        self._packet_drop_active = False

    def should_drop_response(self) -> bool:
        if not self._packet_drop_active or self.faults.packet_drop_probability <= 0.0:
            return False
        return self.faults.rng.random() < self.faults.packet_drop_probability

    def response_delay_ms(self) -> int:
        return max(0, int(self.faults.response_delay_ms))

    def handle_message(self, message: Mapping[str, Any], now_ms: int | None = None) -> list[FakeResponse]:
        """Handle one decoded PC message and return firmware-like replies."""
        message_type = str(message.get("type", ""))
        now_ms = self._resolve_now(now_ms)
        if self.poll(now_ms) == "reboot":
            return []
        if self._is_command_stopped(now_ms):
            self.event_log.append({"timestamp": now_ms, "event": "command_ignored", "type": message_type})
            return self._augment_responses([self._command_stop_telemetry(now_ms)])

        self.processed_command_count += 1
        self.last_command_rx_ms = now_ms

        explicit_fault = self._consume_explicit_fault()

        if message_type == "who_are_you":
            return self._augment_responses([self.node_identity()])
        if message_type == "hello":
            if not self.faults.hello_ack:
                return self._augment_responses([])
            return self._augment_responses([self.hello_ack()])
        if message_type == "config":
            self.config_revision = int(message.get("config_revision", self.config_revision)) + 1
            self.pca9685_address = int(message.get("pca9685_address", self.pca9685_address))
            self._enter_safe()
            self.last_drive_seq = 0
            ack = (
                {
                    "v": 1,
                    "type": "config_ack",
                    "ok": False,
                    "reason": "config rejected by fake injector",
                    "config_revision": self.config_revision,
                }
                if not self.faults.config_ack_ok
                else {
                    "v": 1,
                    "type": "config_ack",
                    "ok": True,
                    "reason": "stored (simulated)",
                    "config_revision": self.config_revision,
                }
            )
            responses = [ack]
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)
        if message_type == "arm":
            responses = []
            mode = str(message.get("mode", "normal")).lower()
            if mode not in {"normal", "debug"}:
                responses.append(self.fault("unsupported arm mode"))
            elif not self.faults.arm_ack_ok:
                self._enter_safe()
                responses.append(self.arm_ack(False, "arm rejected by fake injector"))
            else:
                self.armed = True
                self.state = "DEBUG" if mode == "debug" else "NORMAL"
                self.last_drive_seq = 0
                responses.append(self.arm_ack(True, "armed (simulated)"))
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)
        if message_type == "disarm":
            self._enter_safe()
            responses = [self.arm_ack(True, "disarmed")]
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)
        if message_type == "ping":
            responses = [{"v": 1, "type": "pong", "seq": int(message.get("seq", 0))}]
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)
        if message_type == "drive":
            responses = self._handle_drive(message)
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)
        if message_type == "debug":
            responses = [self.fault("debug command requires DEBUG arm")] if not (self.armed and self.state == "DEBUG") else []
            if explicit_fault is not None:
                responses.append(explicit_fault)
            return self._augment_responses(responses)

        responses = [self.fault("unknown type")]
        if explicit_fault is not None:
            responses.append(explicit_fault)
        return self._augment_responses(responses)

    def _augment_responses(self, responses: list[FakeResponse]) -> list[FakeResponse]:
        if self._consume_malformed():
            return [b"{bad json"]
        if self.faults.telemetry_stop:
            responses = [response for response in responses if not isinstance(response, dict) or response.get("type") != "telemetry"]
        return responses

    def _consume_malformed(self) -> bool:
        if self.faults.malformed_json_count <= 0:
            return False
        self.faults.malformed_json_count -= 1
        return True

    def _consume_explicit_fault(self) -> dict[str, Any] | None:
        if self.faults.explicit_fault is None:
            return None
        if self.faults.explicit_fault_after_arm and not self.armed:
            return None
        reason = str(self.faults.explicit_fault)
        if self.faults.explicit_fault_once:
            self.faults.explicit_fault = None
        self._enter_safe()
        return self.fault(reason, flags=self.faults.explicit_fault_flags)

    def _next_telemetry_seq(self, expected_seq: int) -> int:
        if self.faults.telemetry_seq_stale:
            return expected_seq if self._last_telemetry_seq is None else self._last_telemetry_seq
        if self.faults.telemetry_seq_regression_count > 0 and self._last_telemetry_seq is not None:
            self.faults.telemetry_seq_regression_count -= 1
            return max(0, self._last_telemetry_seq - 1)
        return expected_seq

    def _resolve_now(self, now_ms: int | None) -> int:
        return int(self.clock_ms()) if now_ms is None else int(now_ms)

    def poll(self, now_ms: int | None = None) -> str | None:
        """Advance time-triggered transport/reboot state without a command."""
        resolved = self._resolve_now(now_ms)
        if self._is_disconnected(resolved):
            raise RuntimeError("simulated ESP32 serial disconnect")
        if self._is_rebooting(resolved):
            self._apply_reboot(resolved)
            return "reboot"
        return None

    def _is_disconnected(self, now_ms: int) -> bool:
        if self._manual_disconnect:
            return True
        if self.faults.disconnect_after_ms is not None:
            return now_ms - self._start_time_ms >= self.faults.disconnect_after_ms
        return False

    def _is_command_stopped(self, now_ms: int) -> bool:
        if self._manual_command_stop:
            return True
        if self.faults.command_receive_stop_after_ms is not None:
            return now_ms - self._start_time_ms >= self.faults.command_receive_stop_after_ms
        return False

    def _command_stop_telemetry(self, now_ms: int) -> dict[str, object]:
        """Keep firmware-like telemetry alive while incoming commands stall."""
        age_ms = max(0, now_ms - (self.last_command_rx_ms if self.last_command_rx_ms is not None else self._start_time_ms))
        fault_flags = 0
        if self.armed and age_ms >= COMMAND_SAFE_MS:
            self._enter_safe()
            fault_flags = FAULT_COMMAND_TIMEOUT
        elif self.armed and age_ms >= COMMAND_STOP_MS:
            self.motor_pwm = [0, 0, 0, 0]
            self.wheel_rpm = [0.0, 0.0, 0.0, 0.0]
        # Real firmware telemetry has its own periodic sequence, independent
        # from whether a drive command was accepted.
        self.seq += 1
        response = self.telemetry()
        response["command_age_ms"] = age_ms
        response["fault_flags"] = fault_flags
        return response

    def _is_rebooting(self, now_ms: int) -> bool:
        if self._pending_reboot:
            return True
        if self.faults.reboot_after_ms is None or self._scheduled_reboot_consumed:
            return False
        return now_ms - self._start_time_ms >= self.faults.reboot_after_ms

    def _apply_reboot(self, now_ms: int) -> None:
        self._pending_reboot = False
        self._scheduled_reboot_consumed = True
        self._enter_safe()
        self.seq = 0
        self.last_drive_seq = 0
        self._last_telemetry_seq = None
        self.config_revision = 1
        self.encoder_count = [0, 0, 0, 0]
        self.servo_deg = [0.0, 0.0, 0.0, 0.0]
        self.commanded_servo_deg = [0.0, 0.0, 0.0, 0.0]
        self.processed_command_count = 0
        self.last_command_rx_ms = None
        self.reboot_count += 1
        self._start_time_ms = now_ms
        self.event_log.append({"timestamp": now_ms, "event": "reboot", "type": None})

    def _handle_drive(self, message: Mapping[str, Any]) -> list[FakeResponse]:
        try:
            steer = [float(value) for value in message.get("steer_deg", [])]
            target = [float(value) for value in message.get("drive_target", [])]
        except (TypeError, ValueError):
            return [self.fault("invalid drive value")]
        if len(steer) != 4 or len(target) != 4:
            return [self.fault("drive arrays must have 4 entries")]
        if not all(isfinite(value) for value in steer + target):
            return [self.fault("non-finite drive value")]
        if str(message.get("control", "pwm")) not in {"pwm", "rpm"}:
            return [self.fault("unsupported drive control")]

        seq = int(message.get("seq", 0))
        if seq <= self.last_drive_seq:
            return [self.fault("stale drive seq")]
        self.last_drive_seq = seq

        if not bool(message.get("armed", False)):
            self._enter_safe()
            return [self.telemetry()]

        if not (self.armed and self.state == "NORMAL"):
            return [self.telemetry()]

        return [self.apply_drive(message)]

    def apply_drive(self, message: Mapping[str, object], dt: float = 0.02) -> dict[str, object]:
        """Apply one drive command and return telemetry.

        This method remains usable directly by the legacy ``--simulate`` path.
        The protocol-faithful path should call :meth:`handle_message` instead.
        """
        steer = [float(value) for value in message.get("steer_deg", [0.0] * 4)]
        target = [float(value) for value in message.get("drive_target", [0.0] * 4)]
        control = str(message.get("control", "pwm"))
        self.commanded_servo_deg = list(steer)
        self.commanded_drive_target = list(target)
        if self.faults.servo_stuck:
            configured_servo = self._stuck_values(self.faults.servo_stuck_value)
            if configured_servo is not None:
                self.servo_deg = configured_servo
        else:
            self.servo_deg = steer
        for index, value in enumerate(target):
            if control == "rpm":
                self.motor_pwm[index] = int(max(-1023, min(1023, value * 5.0)))
                if not self.faults.rpm_stuck:
                    self.wheel_rpm[index] += (value - self.wheel_rpm[index]) * 0.2
            else:
                self.motor_pwm[index] = int(max(-1023, min(1023, value)))
                if not self.faults.rpm_stuck:
                    self.wheel_rpm[index] = copysign(abs(self.motor_pwm[index]) / 10.0, self.motor_pwm[index])
            configured_rpm = self._stuck_values(self.faults.rpm_stuck_value)
            if self.faults.rpm_stuck and configured_rpm is not None:
                self.wheel_rpm[index] = configured_rpm[index]
            if not self.faults.rpm_stuck:
                self.encoder_count[index] += int(self.wheel_rpm[index] * dt * 20.0)
        self.seq += 1
        return self.telemetry("NORMAL", bool(message.get("armed", False)))

    def node_identity(self) -> dict[str, Any]:
        return {
            "v": 1,
            "type": "node_identity",
            "node_id": self.node_id,
            "board": self.board,
            "role": self.role,
            "firmware": self.firmware,
            "fw_version": self.fw_version,
            "protocol": "mcb44-json-serial",
            "esp32_efuse_mac": f"SIM{self._last_reconnect_seq:012d}",
            "pca9685_ok": self.pca9685_ok,
            "pca9685_address": self.pca9685_address,
            "config_revision": self.config_revision,
            "capabilities": ["drive_4wis", "encoder", "pca9685", "debug", "simulation"],
        }

    def hello_ack(self) -> dict[str, Any]:
        return {
            "v": 1,
            "type": "hello_ack",
            "node_id": self.node_id,
            "board": self.board,
            "role": self.role,
            "firmware": self.firmware,
            "protocol": "mcb44-json-serial",
            "pca9685_ok": self.pca9685_ok,
            "pca9685_address": self.pca9685_address,
        }

    def arm_ack(self, ok: bool, reason: str) -> dict[str, Any]:
        return {
            "v": 1,
            "type": "arm_ack",
            "ok": bool(ok),
            "armed": self.armed,
            "state": self.state,
            "reason": reason,
        }

    @staticmethod
    def fault(reason: str, flags: int = 1) -> dict[str, Any]:
        return {"v": 1, "type": "fault", "fault_flags": flags, "reason": reason}

    def telemetry(self, state: str | None = None, armed: bool | None = None) -> dict[str, object]:
        """Return a telemetry object shaped like the ESP32 message."""
        telemetry_seq = self._next_telemetry_seq(self.seq)
        self._last_telemetry_seq = telemetry_seq
        encoder_count = (
            [2_147_483_647, -2_147_483_648, 1_000_000, 500_000]
            if self.faults.encoder_anomaly
            else list(self.encoder_count)
        )
        return {
            "v": 1,
            "type": "telemetry",
            "seq": telemetry_seq,
            "state": self.state if state is None else state,
            "armed": self.armed if armed is None else armed,
            "encoder_count": encoder_count,
            "wheel_rpm": list(self.wheel_rpm),
            "motor_pwm": list(self.motor_pwm),
            "servo_deg": list(self.servo_deg),
            "fault_flags": 0,
            "command_age_ms": (
                0 if self.last_command_rx_ms is None else max(0, self._resolve_now(None) - self.last_command_rx_ms)
            ),
        }

    @property
    def last_emitted_telemetry_seq(self) -> int | None:
        return self._last_telemetry_seq

    @staticmethod
    def _stuck_values(value: float | list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list):
            if len(value) != 4:
                raise ValueError("stuck value list must contain 4 entries")
            return [float(item) for item in value]
        return [float(value)] * 4

    def _enter_safe(self) -> None:
        self.armed = False
        self.state = "SAFE"
        self.motor_pwm = [0, 0, 0, 0]
        self.wheel_rpm = [0.0, 0.0, 0.0, 0.0]
        self.commanded_drive_target = [0.0, 0.0, 0.0, 0.0]
        self.last_drive_seq = 0
