from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WHEEL_NAMES = ("FL", "FR", "RL", "RR")


@dataclass(frozen=True)
class WheelTelemetry:
    angles_deg: list[float]
    speeds_mps: list[float]
    rpm: list[float | None]
    pwm: list[int | None]
    source: str
    detail: str = ""


def clamp_value(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_vehicle_config(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or _project_root_from_here()
    config_path = root / "config" / "vehicle_config.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "motion": {
                "wheelbase_m": 0.327,
                "track_width_m": 0.327,
                "wheel_diameter_m": 0.055,
                "max_wheel_rpm": 520.0,
                "max_linear_speed_mps": 1.5,
                "max_angular_speed_radps": 4.0,
                "open_loop_max_pwm": 600,
            },
            "servos": [
                {"name": name, "channel": channel, "min_angle_deg": -135.0, "max_angle_deg": 135.0}
                for name, channel in zip(WHEEL_NAMES, (6, 5, 7, 4))
            ],
        }


def save_vehicle_config(config: dict[str, Any], project_root: Path | None = None) -> Path:
    path = _vehicle_config_path(project_root)
    serializable = dict(config)
    config_revision = serializable.get("config_revision")
    if isinstance(config_revision, int):
        serializable["config_revision"] = config_revision + 1
    else:
        serializable["config_revision"] = 1
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def calculate_4wis_state(
    vx_norm: float,
    vy_norm: float,
    omega_norm: float,
    config: dict[str, Any],
    last_angles_deg: list[float],
) -> WheelTelemetry:
    motion = config.get("motion", {})
    max_linear = float(motion.get("max_linear_speed_mps", 1.5) or 1.5)
    max_angular = float(motion.get("max_angular_speed_radps", 4.0) or 4.0)
    wheelbase = float(motion.get("wheelbase_m", 0.327) or 0.327)
    track_width = float(motion.get("track_width_m", 0.327) or 0.327)
    open_loop_max_pwm = int(motion.get("open_loop_max_pwm", 600) or 600)
    wheel_diameter = float(motion.get("wheel_diameter_m", 0.055) or 0.055)

    vx = clamp_value(vx_norm, -1.0, 1.0) * max_linear
    vy = clamp_value(vy_norm, -1.0, 1.0) * max_linear
    omega = clamp_value(omega_norm, -1.0, 1.0) * max_angular

    servos = config.get("servos", [])
    angles: list[float] = []
    speeds: list[float] = []
    for index, (x_pos, y_pos) in enumerate(_wheel_positions(wheelbase, track_width)):
        wheel_vx = vx - omega * y_pos
        wheel_vy = vy + omega * x_pos
        speed = math.hypot(wheel_vx, wheel_vy)
        angle = last_angles_deg[index] if speed < 1e-6 else math.degrees(math.atan2(wheel_vy, wheel_vx))
        servo = servos[index] if index < len(servos) and isinstance(servos[index], dict) else {}
        angle = clamp_value(
            angle,
            float(servo.get("min_angle_deg", -135.0) or -135.0),
            float(servo.get("max_angle_deg", 135.0) or 135.0),
        )
        angles.append(angle)
        speeds.append(speed)

    max_speed = max_wheel_speed_mps(config)
    peak = max(speeds, default=0.0)
    if max_speed > 0.0 and peak > max_speed:
        scale = max_speed / peak
        speeds = [speed * scale for speed in speeds]

    rpm = [(speed * 60.0) / (math.pi * wheel_diameter) if wheel_diameter > 0.0 else 0.0 for speed in speeds]
    pwm = [
        int(round(clamp_value(speed / max_speed if max_speed > 0.0 else 0.0, 0.0, 1.0) * open_loop_max_pwm))
        for speed in speeds
    ]
    detail = f"vx {vx:.2f} m/s / vy {vy:.2f} m/s / omega {omega:.2f} rad/s"
    return WheelTelemetry(angles, speeds, rpm, pwm, "アプリ内4WISモデル", detail)


def telemetry_from_line(
    line: str,
    source: str,
    config: dict[str, Any],
    last_angles_deg: list[float],
) -> WheelTelemetry | None:
    text = line.strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(message, dict):
            return None
        if message.get("type") == "telemetry":
            return telemetry_from_fields(
                servo_deg=message.get("servo_deg"),
                wheel_rpm=message.get("wheel_rpm"),
                motor_pwm=message.get("motor_pwm"),
                source=f"{source} telemetry",
                detail=_telemetry_detail(message),
                config=config,
                last_angles_deg=last_angles_deg,
            )
        if message.get("type") == "drive":
            return telemetry_from_fields(
                servo_deg=message.get("steer_deg"),
                wheel_rpm=message.get("drive_target") if message.get("control") == "rpm" else None,
                motor_pwm=message.get("drive_target") if message.get("control") == "pwm" else None,
                source=f"{source} drive",
                detail=f"seq {message.get('seq', '-')} / armed {message.get('armed', '-')}",
                config=config,
                last_angles_deg=last_angles_deg,
            )
        return None

    servo_match = re.search(r"servo(?:_deg)?=\[([^\]]+)\]", text)
    pwm_match = re.search(r"pwm=\[([^\]]+)\]", text)
    rpm_match = re.search(r"rpm=\[([^\]]+)\]", text)
    if servo_match:
        return telemetry_from_fields(
            servo_deg=_parse_number_csv(servo_match.group(1)),
            wheel_rpm=_parse_number_csv(rpm_match.group(1)) if rpm_match else None,
            motor_pwm=_parse_number_csv(pwm_match.group(1)) if pwm_match else None,
            source=f"{source} text",
            detail=text[:120],
            config=config,
            last_angles_deg=last_angles_deg,
        )
    return None


def telemetry_from_fields(
    servo_deg: Any,
    wheel_rpm: Any,
    motor_pwm: Any,
    source: str,
    detail: str,
    config: dict[str, Any],
    last_angles_deg: list[float],
) -> WheelTelemetry | None:
    angles = _number_list(servo_deg, 4)
    rpm = _number_list(wheel_rpm, 4)
    pwm = _int_list(motor_pwm, 4)
    if angles is None and rpm is None and pwm is None:
        return None
    if angles is None:
        angles = list(last_angles_deg)
    speeds = [0.0, 0.0, 0.0, 0.0]
    if rpm is not None:
        wheel_diameter = float(config.get("motion", {}).get("wheel_diameter_m", 0.055) or 0.055)
        speeds = [value * math.pi * wheel_diameter / 60.0 for value in rpm]
    elif pwm is not None:
        max_speed = max_wheel_speed_mps(config)
        open_loop_max_pwm = int(config.get("motion", {}).get("open_loop_max_pwm", 600) or 600)
        speeds = [value / max(open_loop_max_pwm, 1) * max_speed for value in pwm]
    return WheelTelemetry(
        angles_deg=angles,
        speeds_mps=speeds,
        rpm=rpm or [None, None, None, None],
        pwm=pwm or [None, None, None, None],
        source=source,
        detail=detail,
    )


def max_wheel_speed_mps(config: dict[str, Any]) -> float:
    motion = config.get("motion", {})
    diameter = float(motion.get("wheel_diameter_m", 0.0) or 0.0)
    max_rpm = float(motion.get("max_wheel_rpm", 0.0) or 0.0)
    explicit = float(motion.get("max_linear_speed_mps", 0.0) or 0.0)
    rpm_limit = (math.pi * diameter * max_rpm) / 60.0 if diameter > 0.0 and max_rpm > 0.0 else 0.0
    if explicit > 0.0 and rpm_limit > 0.0:
        return min(explicit, rpm_limit)
    return explicit or rpm_limit or 1.0


def _number_list(value: Any, length: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != length:
        return None
    result: list[float] = []
    try:
        for item in value:
            number = float(item)
            if not math.isfinite(number):
                return None
            result.append(number)
    except (TypeError, ValueError):
        return None
    return result


def _int_list(value: Any, length: int) -> list[int] | None:
    numbers = _number_list(value, length)
    if numbers is None:
        return None
    return [int(round(number)) for number in numbers]


def _project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "vehicle_config.json").exists() and (parent / "pc_controller").exists():
            return parent
    return here.parents[3] if len(here.parents) > 3 else here.parents[-1]


def _vehicle_config_path(project_root: Path | None = None) -> Path:
    root = project_root or _project_root_from_here()
    return root / "config" / "vehicle_config.json"


def _wheel_positions(wheelbase_m: float, track_width_m: float) -> list[tuple[float, float]]:
    half_wheelbase = wheelbase_m / 2.0
    half_track = track_width_m / 2.0
    return [
        (half_wheelbase, half_track),
        (half_wheelbase, -half_track),
        (-half_wheelbase, half_track),
        (-half_wheelbase, -half_track),
    ]


def _parse_number_csv(text: str) -> list[float] | None:
    try:
        values = [float(item.strip()) for item in text.split(",")]
    except ValueError:
        return None
    return values if len(values) == 4 else None


def _telemetry_detail(message: dict[str, Any]) -> str:
    state = message.get("state", "-")
    seq = message.get("seq", "-")
    fault = message.get("fault_flags", "-")
    return f"state {state} / seq {seq} / fault_flags {fault}"
