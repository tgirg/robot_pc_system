from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "vehicle_config.json").exists() and (parent / "pc_controller").exists():
            return parent
    return here.parents[3] if len(here.parents) > 3 else here.parents[-1]


PROJECT_ROOT = _project_root_from_here()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc_controller.protocol import ProtocolError, ProtocolValidator, encode_message  # noqa: E402


@dataclass(frozen=True)
class FakeV29Result:
    success: bool
    message: str
    response_lines: list[str]


class FakeV29ESP32:
    """Small v29 ESP32 simulator for dashboard-only hardware-free checks."""

    def __init__(self) -> None:
        self.armed = False
        self.state = "DISARMED"
        self.last_seq = 0
        self.validator = ProtocolValidator()
        self.last_steer_deg = [0.0, 0.0, 0.0, 0.0]
        self.last_pwm = [0, 0, 0, 0]
        self.last_rpm = [0.0, 0.0, 0.0, 0.0]

    def reset(self) -> None:
        self.__init__()

    def process_line(self, line: str) -> FakeV29Result:
        try:
            message = json.loads(line.strip())
        except json.JSONDecodeError as exc:
            return self._fault(f"invalid json: {exc.msg}")
        if not isinstance(message, dict):
            return self._fault("message must be object")

        message_type = str(message.get("type", ""))
        if message_type == "arm":
            self.armed = True
            mode = str(message.get("mode", "normal")).upper()
            self.state = "DEBUG" if mode == "DEBUG" else "NORMAL"
            return FakeV29Result(True, "Fake ARM ACK", [self._line(self._arm_ack(True, "fake arm ok"))])
        if message_type == "disarm":
            self.armed = False
            self.state = "SAFE"
            self.last_pwm = [0, 0, 0, 0]
            self.last_rpm = [0.0, 0.0, 0.0, 0.0]
            return FakeV29Result(True, "Fake DISARM", [self._line(self._telemetry(seq=self.last_seq, control="pwm"))])
        if message_type == "config":
            revision = int(message.get("config_revision", 0)) + 1
            return FakeV29Result(
                True,
                "Fake CONFIG ACK",
                [self._line({"v": 1, "type": "config_ack", "ok": True, "reason": "fake stored", "config_revision": revision})],
            )
        if message_type == "drive":
            return self._process_drive(message)
        if message_type == "debug":
            return self._process_debug(message)
        return self._fault(f"unsupported type: {message_type or '-'}")

    def build_fault_line(self, reason: str = "fake fault") -> str:
        self.armed = False
        self.state = "FAULT"
        return self._line({"v": 1, "type": "fault", "reason": reason, "state": self.state})

    def build_arm_ack_line(self, ok: bool = True, reason: str = "fake ack") -> str:
        self.armed = bool(ok)
        self.state = "ARMED" if ok else "DISARMED"
        return self._line(self._arm_ack(ok, reason))

    def _process_drive(self, message: Mapping[str, Any]) -> FakeV29Result:
        if not self.armed or not bool(message.get("armed", False)):
            return self._fault("drive rejected while disarmed")
        try:
            self.validator.validate_drive(message)
        except (ProtocolError, ValueError, TypeError) as exc:
            return self._fault(f"drive rejected: {exc}")

        self.last_seq = int(message.get("seq", 0))
        self.last_steer_deg = [float(value) for value in message.get("steer_deg", [0.0] * 4)]
        control = str(message.get("control", "pwm"))
        targets = [float(value) for value in message.get("drive_target", [0.0] * 4)]
        if control == "rpm":
            self.last_rpm = targets
            self.last_pwm = [0, 0, 0, 0]
        else:
            self.last_pwm = [int(round(value)) for value in targets]
            self.last_rpm = [0.0, 0.0, 0.0, 0.0]
        self.state = "DRIVE" if any(abs(value) > 0 for value in targets) else "STOP"
        return FakeV29Result(True, "Fake telemetry", [self._line(self._telemetry(seq=self.last_seq, control=control))])

    def _process_debug(self, message: Mapping[str, Any]) -> FakeV29Result:
        if not self.armed or self.state != "DEBUG":
            return self._fault("debug rejected while not DEBUG armed")
        action = str(message.get("action", ""))
        wheel = int(message.get("wheel", 0))
        if wheel < 0 or wheel >= 4:
            return self._fault("debug wheel must be 0..3")
        if action == "servo_deg":
            self.last_steer_deg[wheel] = float(message.get("value", 0.0))
        elif action == "motor_stop":
            self.last_pwm = [0, 0, 0, 0]
            self.last_rpm = [0.0, 0.0, 0.0, 0.0]
        else:
            return self._fault(f"unsupported debug action: {action or '-'}")
        return FakeV29Result(True, "Fake debug telemetry", [self._line(self._telemetry(seq=self.last_seq, control="pwm"))])

    def _fault(self, reason: str) -> FakeV29Result:
        return FakeV29Result(False, reason, [self.build_fault_line(reason)])

    def _arm_ack(self, ok: bool, reason: str) -> dict[str, Any]:
        return {
            "v": 1,
            "type": "arm_ack",
            "ok": bool(ok),
            "armed": bool(ok and self.armed),
            "state": self.state,
            "reason": reason,
        }

    def _telemetry(self, *, seq: int, control: str) -> dict[str, Any]:
        message: dict[str, Any] = {
            "v": 1,
            "type": "telemetry",
            "armed": self.armed,
            "state": self.state,
            "seq": int(seq),
            "servo_deg": self.last_steer_deg,
            "fault_flags": "none",
        }
        if control == "rpm":
            message["wheel_rpm"] = self.last_rpm
            message["motor_pwm"] = self.last_pwm
        else:
            message["wheel_rpm"] = self.last_rpm
            message["motor_pwm"] = self.last_pwm
        return message

    def _line(self, message: Mapping[str, Any]) -> str:
        return encode_message(message).decode("utf-8").strip()
