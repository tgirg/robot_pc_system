"""JSON configuration loading, validation, and saving."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

WHEEL_NAMES = ("FL", "FR", "RL", "RR")
CONFIG_SCHEMA_VERSION = 1
DEFAULT_MOTOR_PHYSICAL = (2, 1, 3, 0)
DEFAULT_ENCODER_PHYSICAL = (0, 1, 2, 3)
DEFAULT_SERVO_CHANNELS = (6, 5, 7, 4)
DEFAULT_SERVO_CENTER_US = (1490, 1580, 1590, 1550)
DEFAULT_SERVO_DIRECTION_INVERTED = (True, True, True, True)


@dataclass(frozen=True)
class JsonLoadResult:
    data: dict[str, Any]
    loaded: bool
    missing: bool
    error: str | None = None


def default_vehicle_config() -> dict[str, Any]:
    """Return a conservative vehicle config with normal ARM intentionally blocked."""
    motors = []
    encoders = []
    servos = []
    for index, name in enumerate(WHEEL_NAMES):
        motors.append(
            {
                "logical": index,
                "name": name,
                "physical": DEFAULT_MOTOR_PHYSICAL[index],
                "inverted": True,
                "pid_enabled": False,
                "kp": 1.0,
                "ki": 1.2,
                "kd": 0.0,
                "integral_limit": 100.0,
                "output_min": -140,
                "output_max": 140,
                "counts_per_wheel_rev": 0,
            }
        )
        encoders.append(
            {
                "logical": index,
                "name": name,
                "physical": DEFAULT_ENCODER_PHYSICAL[index],
                "inverted": False,
                "counts_per_wheel_rev": 0,
            }
        )
        servos.append(
            {
                "logical": index,
                "name": name,
                "channel": DEFAULT_SERVO_CHANNELS[index],
                "center_us": DEFAULT_SERVO_CENTER_US[index],
                "min_us": 500,
                "max_us": 2500,
                "min_angle_deg": -135.0,
                "max_angle_deg": 135.0,
                "trim_deg": 0.0,
                "direction_inverted": DEFAULT_SERVO_DIRECTION_INVERTED[index],
                "calibrated": False,
                "max_rate_deg_per_sec": 360.0,
            }
        )
    return {
        "v": 1,
        "type": "config",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "config_revision": 1,
        "pid_enabled": False,
        "pca9685_address": 64,
        "motion": {
            "wheelbase_m": 0.327,
            "track_width_m": 0.327,
            "wheel_diameter_m": 0.055,
            "max_wheel_rpm": 520.0,
            "max_linear_speed_mps": 1.5,
            "max_angular_speed_radps": 4.0,
            "pid_max_target_rpm": 80.0,
            "pid_pivot_max_target_rpm": 60.0,
            "open_loop_max_pwm": 120,
            "open_loop_static_compensation_enabled": False,
            "translation_deadzone": 0.12,
            "candidate_switch_hysteresis_deg": 20.0,
            "servo_end_margin_deg": 10.0,
            "realign_threshold_deg": 30.0,
            "alignment_servo_rate_deg_per_sec": 180.0,
            "alignment_tolerance_deg": 5.0,
            "alignment_settle_time_ms": 100,
            "alignment_timeout_ms": 2000,
            "decel_time_ms": 200,
            "accel_time_ms": 200,
            "pivot_max_pwm": 120,
            "pivot_steering_mode": "optimized",
            "pivot_direction_inverted": False,
            "mixed_omega_inverted": False,
            "mixed_steering_mode": "limited_arc",
            "mixed_arc_min_radius_m": 0.4,
            "coordinated_4ws_max_steer_deg": 45.0,
            "coordinated_4ws_inner_outer_speed": False,
            "coordinated_4ws_positive_steer_turns_right": True,
            "limit_mixed_peak_to_translation": True,
        },
        "motors": motors,
        "encoders": encoders,
        "servos": servos,
        "debug_limits": {
            "max_pwm": 102,
            "max_motor_test_ms": 1000,
            "servo_debug_rate_deg_per_sec": 60.0,
        },
    }


def default_controller_mapping() -> dict[str, Any]:
    """Return a configurable PS4-like controller mapping."""
    return {
        "axis_vx": 1,
        "axis_vy": 0,
        "axis_omega": 2,
        "logical_front": "FRONT",
        "invert_vx": True,
        "invert_vy": True,
        "invert_omega": True,
        "pivot_motor_direction_inverted": [False, False, False, False],
        "deadzone": 0.12,
        "linear_scale": 0.12,
        "angular_scale": 0.35,
        "arm_buttons": [9, 10, 0],
        "arm_hold_seconds": 1.0,
        "safe_button": 6,
        "mode_button": 8,
        "debug_select_buttons": [13, 14],
        "debug_execute_button": 1,
    }


def load_json_result(path: Path, default: Mapping[str, Any]) -> JsonLoadResult:
    """Load JSON and report whether the on-disk file was trustworthy."""
    if not path.exists():
        return JsonLoadResult(copy.deepcopy(dict(default)), loaded=False, missing=True, error="missing")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        return JsonLoadResult(copy.deepcopy(dict(default)), loaded=False, missing=False, error=str(exc))
    except json.JSONDecodeError as exc:
        return JsonLoadResult(copy.deepcopy(dict(default)), loaded=False, missing=False, error=f"invalid json: {exc.msg}")
    if not isinstance(data, dict):
        return JsonLoadResult(copy.deepcopy(dict(default)), loaded=False, missing=False, error="top-level JSON is not an object")
    return JsonLoadResult(data, loaded=True, missing=False)


def load_json(path: Path, default: Mapping[str, Any]) -> dict[str, Any]:
    """Load JSON from path, creating a deep copy of default on failure."""
    return load_json_result(path, default).data


def save_json(path: Path, data: Mapping[str, Any]) -> None:
    """Save JSON with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def ensure_config_files(config_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load or create vehicle and controller configuration files."""
    vehicle_path = config_dir / "vehicle_config.json"
    mapping_path = config_dir / "controller_mapping.json"
    vehicle_result = load_json_result(vehicle_path, default_vehicle_config())
    mapping_result = load_json_result(mapping_path, default_controller_mapping())
    if not vehicle_result.loaded and not vehicle_result.missing:
        raise ValueError(f"invalid vehicle config file {vehicle_path}: {vehicle_result.error}")
    if not mapping_result.loaded and not mapping_result.missing:
        raise ValueError(f"invalid controller mapping file {mapping_path}: {mapping_result.error}")
    if vehicle_result.missing:
        save_json(vehicle_path, vehicle_result.data)
    if mapping_result.missing:
        save_json(mapping_path, mapping_result.data)
    return vehicle_result.data, mapping_result.data


def _require_unique(values: list[int], limit: int, label: str) -> None:
    if len(values) != 4:
        raise ValueError(f"{label} must have 4 entries")
    if any(value < 0 or value >= limit for value in values):
        raise ValueError(f"{label} contains out-of-range value")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicates")


def validate_vehicle_config(config: Mapping[str, Any], require_armable: bool = False) -> None:
    """Validate mapping, numeric ranges, and optional ARM prerequisites."""
    if int(config.get("schema_version", 0)) != CONFIG_SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if int(config.get("pca9685_address", 0)) in (0,):
        raise ValueError("pca9685_address must not be 0")

    motors = list(config.get("motors", []))
    encoders = list(config.get("encoders", []))
    servos = list(config.get("servos", []))
    if len(motors) != 4 or len(encoders) != 4 or len(servos) != 4:
        raise ValueError("motors, encoders, and servos must each contain 4 entries")

    _require_unique([int(item.get("physical", -1)) for item in motors], 4, "motor physical mapping")
    _require_unique([int(item.get("physical", -1)) for item in encoders], 4, "encoder physical mapping")
    _require_unique([int(item.get("channel", -1)) for item in servos], 16, "servo channel mapping")

    for servo in servos:
        min_us = int(servo.get("min_us", 0))
        center_us = int(servo.get("center_us", 0))
        max_us = int(servo.get("max_us", 0))
        if not (min_us < center_us < max_us):
            raise ValueError("servo pulse range must satisfy min < center < max")
        if float(servo.get("min_angle_deg", 0.0)) >= 0.0 or float(servo.get("max_angle_deg", 0.0)) <= 0.0:
            raise ValueError("servo angle range must cross 0 degrees")

    if require_armable:
        motion = config.get("motion", {})
        for key in ("wheelbase_m", "track_width_m", "wheel_diameter_m", "max_wheel_rpm"):
            if float(motion.get(key, 0.0)) <= 0.0:
                raise ValueError(f"{key} must be set before NORMAL ARM")
        if any(not bool(servo.get("calibrated", False)) for servo in servos):
            raise ValueError("all servos must be calibrated before NORMAL ARM")
        if bool(config.get("pid_enabled", False)):
            for encoder in encoders:
                if int(encoder.get("counts_per_wheel_rev", 0)) <= 0:
                    raise ValueError("counts_per_wheel_rev is required before PID ARM")
