"""NDJSON protocol helpers for the ESP32 firmware."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """Raised when a protocol message is invalid."""


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Encode one protocol message as UTF-8 NDJSON."""
    payload = dict(message)
    payload.setdefault("v", PROTOCOL_VERSION)
    return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode_line(line: bytes | str) -> dict[str, Any]:
    """Decode one NDJSON line and validate the common header."""
    try:
        text = line.decode("utf-8") if isinstance(line, bytes) else line
    except UnicodeDecodeError as exc:
        raise ProtocolError("invalid utf-8") from exc
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid json") from exc
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    if int(message.get("v", 0)) != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if not isinstance(message.get("type"), str):
        raise ProtocolError("message type required")
    return message


def _finite_numbers(values: Iterable[Any], expected_len: int, label: str) -> list[float]:
    numbers = list(values)
    if len(numbers) != expected_len:
        raise ProtocolError(f"{label} must contain {expected_len} values")
    result: list[float] = []
    for value in numbers:
        number = float(value)
        if not math.isfinite(number):
            raise ProtocolError(f"{label} contains non-finite value")
        result.append(number)
    return result


@dataclass
class ProtocolValidator:
    """Stateful protocol checks such as monotonic drive sequence numbers."""

    last_drive_seq: int = -1

    def validate_drive(self, message: Mapping[str, Any]) -> None:
        """Validate a drive command before sending or applying it."""
        if message.get("type") != "drive":
            raise ProtocolError("not a drive message")
        seq = int(message.get("seq", -1))
        if seq <= self.last_drive_seq:
            raise ProtocolError("stale drive seq")
        control = str(message.get("control", ""))
        if control not in {"pwm", "rpm"}:
            raise ProtocolError("control must be pwm or rpm")
        _finite_numbers(message.get("steer_deg", []), 4, "steer_deg")
        _finite_numbers(message.get("drive_target", []), 4, "drive_target")
        self.last_drive_seq = seq


def hello_message() -> dict[str, Any]:
    """Build the PC hello message."""
    return {"v": PROTOCOL_VERSION, "type": "hello", "client": "pc_controller"}


def who_are_you_message() -> dict[str, Any]:
    """Build a serial discovery identity request."""
    return {"v": PROTOCOL_VERSION, "type": "who_are_you", "client": "pc_controller"}


def arm_message(mode: str = "normal") -> dict[str, Any]:
    """Build an ARM request."""
    return {"v": PROTOCOL_VERSION, "type": "arm", "mode": mode}


def disarm_message() -> dict[str, Any]:
    """Build a DISARM request."""
    return {"v": PROTOCOL_VERSION, "type": "disarm"}


def drive_message(seq: int, control: str, steer_deg: list[float], drive_target: list[float], armed: bool) -> dict[str, Any]:
    """Build a drive command."""
    message = {
        "v": PROTOCOL_VERSION,
        "type": "drive",
        "seq": seq,
        "armed": armed,
        "control": control,
        "steer_deg": steer_deg,
        "drive_target": drive_target,
    }
    ProtocolValidator(seq - 1).validate_drive(message)
    return message


def debug_message(action: str, wheel: int = 0, **fields: Any) -> dict[str, Any]:
    """Build a debug command for one wheel or actuator."""
    message = {"v": PROTOCOL_VERSION, "type": "debug", "action": action, "wheel": wheel}
    message.update(fields)
    return message
