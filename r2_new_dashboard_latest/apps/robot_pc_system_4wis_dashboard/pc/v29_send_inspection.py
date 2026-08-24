from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class V29SendInspection:
    label: str
    status: str
    summary: str
    text: str


def inspect_v29_send_line(label: str, line: str, *, status: str = "TX", max_pwm: int | None = None) -> V29SendInspection:
    text = line.strip()
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        summary = f"{label}: {status} / invalid json"
        return V29SendInspection(label, status, summary, f"{summary}\nraw={text}")
    if not isinstance(message, dict):
        summary = f"{label}: {status} / non-object json"
        return V29SendInspection(label, status, summary, f"{summary}\nraw={text}")

    message_type = str(message.get("type", "-"))
    fields = [f"type={message_type}"]
    if "seq" in message:
        fields.append(f"seq={message.get('seq')}")
    if "armed" in message:
        fields.append(f"armed={message.get('armed')}")
    if "control" in message:
        fields.append(f"control={message.get('control')}")
    if max_pwm is not None:
        fields.append(f"max_pwm={int(max_pwm)}")
    summary = f"{label}: {status} / " + " / ".join(fields)

    lines = [summary]
    if message_type == "drive":
        lines.append(f"steer_deg={_format_float_list(message.get('steer_deg'))}")
        lines.append(f"drive_target={_format_float_list(message.get('drive_target'))}")
    elif message_type == "config":
        lines.append(f"config_revision={message.get('config_revision', '-')}")
        lines.append(f"servo_direction_inverted={_format_bool_list(_servo_field(message, 'direction_inverted'))}")
        motion = message.get("motion")
        if isinstance(motion, dict):
            lines.append(f"pivot_steering_mode={motion.get('pivot_steering_mode', '-')}")
            lines.append(f"pivot_direction_inverted={motion.get('pivot_direction_inverted', '-')}")
    elif message_type in {"arm", "disarm"}:
        if "mode" in message:
            lines.append(f"mode={message.get('mode')}")
    else:
        lines.append(f"payload_keys={','.join(sorted(str(key) for key in message.keys()))}")
    lines.append("json=" + json.dumps(message, ensure_ascii=False, separators=(",", ":")))
    return V29SendInspection(label, status, summary, "\n".join(lines))


def _servo_field(message: dict[str, Any], key: str) -> list[Any] | None:
    servos = message.get("servos")
    if not isinstance(servos, list):
        return None
    values: list[Any] = []
    for servo in servos:
        if not isinstance(servo, dict):
            return None
        values.append(servo.get(key))
    return values


def _format_bool_list(value: list[Any] | None) -> str:
    if value is None:
        return "-"
    return "[" + ", ".join("true" if bool(item) else "false" for item in value) + "]"


def _format_float_list(value: Any) -> str:
    if not isinstance(value, list):
        return "-"
    formatted: list[str] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            formatted.append(str(item))
            continue
        if abs(number - round(number)) < 1e-9:
            formatted.append(f"{int(round(number)):+d}")
        else:
            formatted.append(f"{number:+.1f}")
    return "[" + ", ".join(formatted) + "]"
