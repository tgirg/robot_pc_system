from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import copysign, hypot
from pathlib import Path
from typing import Any

from four_wheel_steer_model import WHEEL_NAMES, WheelTelemetry, clamp_value, load_vehicle_config


def _project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "vehicle_config.json").exists() and (parent / "pc_controller").exists():
            return parent
    return here.parents[3] if len(here.parents) > 3 else here.parents[-1]


PROJECT_ROOT = _project_root_from_here()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc_controller.kinematics import calculate_wheel_vectors, max_wheel_speed_mps, wheel_speed_mps_to_rpm  # noqa: E402
from pc_controller.protocol import arm_message, disarm_message, drive_message, encode_message  # noqa: E402
from pc_controller.steering_optimizer import (  # noqa: E402
    OptimizedWheelCommand,
    OptimizerSettings,
    ServoLimit,
    apply_wheel_direction_inversions,
    apply_open_loop_static_compensation,
    optimize_coordinated_four_ws,
    optimize_pivot_rotation,
    optimize_pure_translation,
    optimize_wheel,
    translation_angle_and_magnitude,
)


@dataclass(frozen=True)
class V29DriveOutput:
    message: dict[str, Any]
    line: str
    telemetry: WheelTelemetry


def load_controller_mapping(project_root: Path | None = None) -> dict[str, Any]:
    path = (project_root or PROJECT_ROOT) / "config" / "controller_mapping.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"linear_scale": 0.12, "angular_scale": 0.35}
    return data if isinstance(data, dict) else {"linear_scale": 0.12, "angular_scale": 0.35}


def encode_v29_line(message: Mapping[str, Any]) -> str:
    return encode_message(message).decode("utf-8").strip()


FIRMWARE_MOTION_KEYS = (
    "wheelbase_m",
    "track_width_m",
    "wheel_diameter_m",
    "max_wheel_rpm",
    "max_linear_speed_mps",
    "max_angular_speed_radps",
    "translation_deadzone",
    "candidate_switch_hysteresis_deg",
    "servo_end_margin_deg",
    "realign_threshold_deg",
    "alignment_servo_rate_deg_per_sec",
    "alignment_tolerance_deg",
    "alignment_settle_time_ms",
    "alignment_timeout_ms",
    "decel_time_ms",
    "accel_time_ms",
)

FIRMWARE_MOTOR_BASE_KEYS = (
    "physical",
    "inverted",
    "pid_enabled",
    "counts_per_wheel_rev",
)

FIRMWARE_MOTOR_PID_KEYS = (
    "kp",
    "ki",
    "kd",
    "integral_limit",
    "ff_static_pwm_pos",
    "ff_static_pwm_neg",
    "ff_pwm_per_rpm_pos",
    "ff_pwm_per_rpm_neg",
    "output_min",
    "output_max",
)

FIRMWARE_ENCODER_KEYS = (
    "physical",
    "inverted",
    "counts_per_wheel_rev",
)

FIRMWARE_SERVO_KEYS = (
    "channel",
    "center_us",
    "min_us",
    "max_us",
    "min_angle_deg",
    "max_angle_deg",
    "trim_deg",
    "direction_inverted",
    "calibrated",
    "max_rate_deg_per_sec",
)


def firmware_config_message(vehicle_config: Mapping[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {
        "v": 1,
        "type": "config",
        "schema_version": int(vehicle_config.get("schema_version", 1)),
        "config_revision": int(vehicle_config.get("config_revision", 1)),
        "pid_enabled": bool(vehicle_config.get("pid_enabled", False)),
        "pca9685_address": int(vehicle_config.get("pca9685_address", 64)),
    }
    motion = vehicle_config.get("motion")
    if isinstance(motion, Mapping):
        message["motion"] = {key: motion[key] for key in FIRMWARE_MOTION_KEYS if key in motion}
    motor_keys = FIRMWARE_MOTOR_BASE_KEYS
    motors = vehicle_config.get("motors")
    if bool(vehicle_config.get("pid_enabled", False)) or _any_motor_pid_enabled(motors):
        motor_keys = FIRMWARE_MOTOR_BASE_KEYS + FIRMWARE_MOTOR_PID_KEYS
    message["motors"] = _firmware_config_items(motors, motor_keys)
    message["encoders"] = _firmware_config_items(vehicle_config.get("encoders"), FIRMWARE_ENCODER_KEYS)
    message["servos"] = _firmware_config_items(vehicle_config.get("servos"), FIRMWARE_SERVO_KEYS)
    return message


def build_config_line(vehicle_config: Mapping[str, Any]) -> str:
    return encode_v29_line(firmware_config_message(vehicle_config))


def _firmware_config_items(value: Any, keys: Sequence[str]) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            items.append({key: item[key] for key in keys if key in item})
    return items


def _any_motor_pid_enabled(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    return any(isinstance(item, Mapping) and bool(item.get("pid_enabled", False)) for item in value)


def build_arm_line(mode: str = "normal") -> str:
    return encode_v29_line(arm_message(mode))


def build_disarm_line() -> str:
    return encode_v29_line(disarm_message())


class V29DriveAdapter:
    def __init__(
        self,
        vehicle_config: dict[str, Any] | None = None,
        controller_mapping: dict[str, Any] | None = None,
    ) -> None:
        self.config = vehicle_config or load_vehicle_config(PROJECT_ROOT)
        self.mapping = controller_mapping or load_controller_mapping(PROJECT_ROOT)
        self.last_angles = [0.0, 0.0, 0.0, 0.0]
        self.previous_representation: str | None = None
        self.previous_speed_signs = [1, 1, 1, 1]
        self.settings = self._optimizer_settings()

    def reset(self, last_angles: Sequence[float] | None = None) -> None:
        self.last_angles = list(last_angles or [0.0, 0.0, 0.0, 0.0])[:4]
        while len(self.last_angles) < 4:
            self.last_angles.append(0.0)
        self.previous_representation = None
        self.previous_speed_signs = [1, 1, 1, 1]

    def build_drive(
        self,
        seq: int,
        vx_norm: float,
        vy_norm: float,
        omega_norm: float,
        *,
        armed: bool,
        max_pwm: int | None = None,
    ) -> V29DriveOutput:
        self._validate_motion_config()
        motion = self._motion()
        max_linear = float(motion.get("max_linear_speed_mps", 0.0))
        max_angular = float(motion.get("max_angular_speed_radps", 0.0))
        vx = clamp_value(vx_norm, -1.0, 1.0) * max_linear * self._mapping_scale("linear_scale", 0.12)
        vy = clamp_value(vy_norm, -1.0, 1.0) * max_linear * self._mapping_scale("linear_scale", 0.12)
        omega = clamp_value(omega_norm, -1.0, 1.0) * max_angular * self._mapping_scale("angular_scale", 0.35)

        steer, speeds, pure_rotation, detail_prefix = self._resolve_steer_and_speeds(vx, vy, omega, omega_norm)
        control = "rpm" if bool(self.config.get("pid_enabled", False)) else "pwm"
        if control == "rpm":
            targets = [wheel_speed_mps_to_rpm(speed, self.config) for speed in speeds]
            rpm_limit = self._pid_target_rpm_limit(pure_rotation)
            if rpm_limit > 0.0:
                targets = [max(-rpm_limit, min(rpm_limit, target)) for target in targets]
            rpm = [float(target) for target in targets]
            pwm = [None, None, None, None]
        else:
            targets = [
                float(value)
                for value in self._open_loop_pwm_targets(
                    speeds,
                    pure_rotation,
                    apply_compensation=max_pwm is None,
                )
            ]
            if max_pwm is not None and max_pwm > 0:
                limit = abs(int(max_pwm))
                peak = max((abs(target) for target in targets), default=0.0)
                if peak > limit > 0:
                    scale = limit / peak
                    targets = [target * scale for target in targets]
                targets = [float(max(-limit, min(limit, int(round(target))))) for target in targets]
                if bool(motion.get("open_loop_static_compensation_enabled", False)):
                    targets = [
                        float(value)
                        for value in apply_open_loop_static_compensation(
                            targets,
                            limit,
                            self.config.get("motors", []),
                        )
                    ]
            pwm = [int(round(target)) for target in targets]
            rpm = [None, None, None, None]

        message = drive_message(int(seq), control, [float(angle) for angle in steer], targets, bool(armed))
        line = encode_v29_line(message)
        self.last_angles = [float(angle) for angle in steer]
        self.previous_speed_signs = [1 if speed >= 0.0 else -1 for speed in speeds]
        telemetry = WheelTelemetry(
            angles_deg=[float(angle) for angle in steer],
            speeds_mps=[float(speed) for speed in speeds],
            rpm=rpm,
            pwm=pwm,
            source="v29 drive TX",
            detail=f"{detail_prefix} / control {control} / seq {seq} / armed {armed}",
        )
        return V29DriveOutput(message, line, telemetry)

    def build_stop(self, seq: int, *, armed: bool) -> V29DriveOutput:
        steer = list(self.last_angles)
        control = "rpm" if bool(self.config.get("pid_enabled", False)) else "pwm"
        targets = [0.0, 0.0, 0.0, 0.0]
        message = drive_message(int(seq), control, steer, targets, bool(armed))
        line = encode_v29_line(message)
        telemetry = WheelTelemetry(
            angles_deg=steer,
            speeds_mps=[0.0, 0.0, 0.0, 0.0],
            rpm=targets if control == "rpm" else [None, None, None, None],
            pwm=[0, 0, 0, 0] if control == "pwm" else [None, None, None, None],
            source="v29 stop TX",
            detail=f"zero drive / control {control} / seq {seq} / armed {armed}",
        )
        return V29DriveOutput(message, line, telemetry)

    def _resolve_steer_and_speeds(self, vx: float, vy: float, omega: float, _omega_norm: float) -> tuple[list[float], list[float], bool, str]:
        motion = self._motion()
        servo_limits = self._servo_limits()
        translation_deadzone = self._translation_deadzone_mps()
        angle, magnitude = translation_angle_and_magnitude(vx, vy, translation_deadzone)
        pure_rotation = magnitude < translation_deadzone and abs(omega) >= 0.05
        mixed_motion = angle is not None and abs(omega) >= 0.05
        mixed_omega_inverted = mixed_motion and bool(motion.get("mixed_omega_inverted", False))
        effective_omega = -omega if mixed_omega_inverted else omega
        effective_omega_norm = -_omega_norm if mixed_omega_inverted else _omega_norm
        mixed_mode = str(motion.get("mixed_steering_mode", "limited_arc")).lower()
        coordinated_mixed = mixed_motion and mixed_mode in {"coordinated_4ws", "coordinated", "v29"}
        arc_motion = (
            mixed_motion
            and not coordinated_mixed
            and self._is_limited_arc_motion(mixed_mode, vx, vy, effective_omega, translation_deadzone)
        )
        resolved_omega = self._limit_manual_arc_omega(vx, vy, effective_omega, motion) if arc_motion else effective_omega
        vectors = calculate_wheel_vectors(vx, vy, resolved_omega, self.config, self.last_angles)

        if pure_rotation:
            turn_speed = max((vector.speed_mps for vector in vectors), default=0.0)
            pivot_omega = resolved_omega * self._pivot_direction_sign(motion)
            pivot_mode = self._pivot_steering_mode(motion)
            if pivot_mode == "straight_tank":
                steer, speeds = self._straight_tank_pivot(turn_speed, pivot_omega)
            elif pivot_mode == "diagonal_parallel":
                steer, speeds = self._diagonal_parallel_pivot(turn_speed, pivot_omega, motion)
            else:
                steer, speeds = optimize_pivot_rotation(turn_speed, pivot_omega, self.last_angles, servo_limits)
            speeds = apply_wheel_direction_inversions(
                speeds,
                self.mapping.get("pivot_motor_direction_inverted", [False, False, False, False]),
            )
            detail = "PIVOT"
        elif angle is not None and abs(omega) < 0.05:
            optimized = optimize_pure_translation(
                angle,
                magnitude,
                self.last_angles,
                servo_limits,
                previous_representation=self.previous_representation,
                previous_speed_signs=self.previous_speed_signs,
                settings=self.settings,
            )
            self._remember_group_representation(optimized)
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]
            detail = "TRANSLATE"
        elif coordinated_mixed:
            optimized = optimize_coordinated_four_ws(
                angle,
                magnitude,
                clamp_value(effective_omega_norm, -1.0, 1.0),
                self.last_angles,
                servo_limits,
                previous_representation=self.previous_representation,
                previous_speed_signs=self.previous_speed_signs,
                settings=self.settings,
                max_steer_deg=float(motion.get("coordinated_4ws_max_steer_deg", 45.0)),
                wheelbase_m=float(motion.get("wheelbase_m", 0.0)),
                track_width_m=float(motion.get("track_width_m", 0.0)),
                inner_outer_speed=bool(motion.get("coordinated_4ws_inner_outer_speed", False)),
                positive_steer_turns_right=bool(motion.get("coordinated_4ws_positive_steer_turns_right", True)),
            )
            self._remember_group_representation(optimized)
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]
            detail = "MIX"
        else:
            if arc_motion or mixed_motion:
                optimized = self._optimize_arc_vectors(vectors, servo_limits)
            else:
                optimized = [
                    optimize_wheel(
                        vectors[index].angle_deg,
                        vectors[index].speed_mps,
                        self.last_angles[index],
                        servo_limits[index],
                        previous_speed_sign=self.previous_speed_signs[index],
                        settings=self.settings,
                    )
                    for index in range(4)
                ]
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]
            detail = "ARC" if arc_motion else "MIX" if mixed_motion else "VECTOR"

        if mixed_motion and bool(motion.get("limit_mixed_peak_to_translation", True)):
            peak_speed = max((abs(speed) for speed in speeds), default=0.0)
            if peak_speed > magnitude > 1e-9:
                scale = magnitude / peak_speed
                speeds = [speed * scale for speed in speeds]
        return steer, speeds, pure_rotation, detail

    def _pivot_steering_mode(self, motion: Mapping[str, Any]) -> str:
        mode = str(motion.get("pivot_steering_mode", "optimized")).lower()
        if mode in {"straight_tank", "tank", "straight", "no_x"}:
            return "straight_tank"
        if mode in {"diagonal_parallel", "parallel_x", "x_parallel", "pivot_x"}:
            return "diagonal_parallel"
        return "optimized"

    def _straight_tank_pivot(self, turn_speed: float, rotate_sign: float) -> tuple[list[float], list[float]]:
        if abs(turn_speed) < 1e-9 or abs(rotate_sign) < 1e-9:
            return [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]
        signed = (1.0 if rotate_sign > 0.0 else -1.0) * abs(turn_speed)
        return [0.0, 0.0, 0.0, 0.0], [-signed, signed, -signed, signed]

    def _pivot_direction_sign(self, motion: Mapping[str, Any]) -> float:
        return -1.0 if bool(motion.get("pivot_direction_inverted", False)) else 1.0

    def _diagonal_parallel_pivot(self, turn_speed: float, rotate_sign: float, motion: Mapping[str, Any]) -> tuple[list[float], list[float]]:
        if abs(turn_speed) < 1e-9 or abs(rotate_sign) < 1e-9:
            return [135.0, 45.0, -135.0, -45.0], [0.0, 0.0, 0.0, 0.0]
        signed = (1.0 if rotate_sign > 0.0 else -1.0) * abs(turn_speed)
        return [135.0, 45.0, -135.0, -45.0], [signed, signed, signed, signed]

    def _optimize_arc_vectors(self, vectors: Sequence[Any], servo_limits: Sequence[ServoLimit]) -> list[OptimizedWheelCommand]:
        direct = [
            optimize_wheel(
                vectors[index].angle_deg,
                vectors[index].speed_mps,
                self.last_angles[index],
                servo_limits[index],
                previous_speed_sign=self.previous_speed_signs[index],
                settings=self.settings,
                allow_reversed_drive=False,
            )
            for index in range(4)
        ]
        if all(command.fault is None for command in direct):
            return direct
        return [
            optimize_wheel(
                vectors[index].angle_deg,
                vectors[index].speed_mps,
                self.last_angles[index],
                servo_limits[index],
                previous_speed_sign=self.previous_speed_signs[index],
                settings=self.settings,
            )
            for index in range(4)
        ]

    def _is_limited_arc_motion(self, mode: str, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if mode in {"forward_arc", "forward", "forward_only_arc", "ackermann"}:
            return self._is_forward_arc_motion(vx, vy, omega, translation_deadzone)
        if mode in {"arc", "manual_arc", "body_velocity_arc", "limited_arc", "translation_arc", "mixed_arc"}:
            return self._is_manual_arc_motion(vx, vy, omega, translation_deadzone)
        return False

    def _is_forward_arc_motion(self, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if abs(omega) < 0.05:
            return False
        lateral_limit = max(translation_deadzone, abs(vx) * 0.20)
        return abs(vx) >= translation_deadzone and abs(vy) <= lateral_limit

    def _is_manual_arc_motion(self, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if abs(omega) < 0.05:
            return False
        forward_arc = self._is_forward_arc_motion(vx, vy, omega, translation_deadzone)
        forward_limit = max(translation_deadzone, abs(vy) * 0.20)
        strafe_arc = abs(vy) >= translation_deadzone and abs(vx) <= forward_limit
        return forward_arc or strafe_arc

    def _limit_manual_arc_omega(self, vx: float, vy: float, omega: float, motion: Mapping[str, Any]) -> float:
        translation_speed = max(abs(vx), abs(vy))
        if translation_speed < 1e-9 or abs(omega) < 1e-9:
            return omega
        wheelbase = float(motion.get("wheelbase_m", 0.0))
        track_width = float(motion.get("track_width_m", 0.0))
        configured = float(
            motion.get(
                "mixed_arc_min_radius_m",
                motion.get("manual_arc_min_radius_m", motion.get("forward_arc_min_radius_m", 0.0)),
            )
            or 0.0
        )
        min_radius = max(configured, wheelbase, track_width, 1e-6)
        max_omega = translation_speed / min_radius
        if abs(omega) <= max_omega:
            return omega
        return copysign(max_omega, omega)

    def _remember_group_representation(self, commands: list[OptimizedWheelCommand]) -> None:
        representations = {command.representation for command in commands}
        if len(representations) == 1:
            representation = representations.pop()
            if representation in {"A", "B"}:
                self.previous_representation = representation

    def _servo_limits(self) -> list[ServoLimit]:
        limits: list[ServoLimit] = []
        for item in self.config.get("servos", []):
            if isinstance(item, Mapping):
                limits.append(
                    ServoLimit(
                        float(item.get("min_angle_deg", -135.0)),
                        float(item.get("max_angle_deg", 135.0)),
                        bool(item.get("calibrated", True)),
                    )
                )
        while len(limits) < len(WHEEL_NAMES):
            limits.append(ServoLimit(-135.0, 135.0, True))
        return limits[:4]

    def _optimizer_settings(self) -> OptimizerSettings:
        motion = self._motion()
        return OptimizerSettings(
            hysteresis_deg=float(motion.get("candidate_switch_hysteresis_deg", 20.0)),
            end_margin_deg=float(motion.get("servo_end_margin_deg", 10.0)),
            realign_threshold_deg=float(motion.get("realign_threshold_deg", 30.0)),
            small_error_full_speed_deg=float(motion.get("alignment_tolerance_deg", 8.0)),
        )

    def _open_loop_pwm_targets(
        self,
        speeds: list[float],
        pure_rotation: bool,
        apply_compensation: bool = True,
    ) -> list[int]:
        motion = self._motion()
        full_scale_speed = self._open_loop_full_scale_speed_mps(pure_rotation)
        if full_scale_speed <= 1e-9:
            full_scale_speed = max_wheel_speed_mps(self.config) or max((abs(speed) for speed in speeds), default=0.0) or 1.0
        pwm_limit = self._pwm_limit("open_loop_max_pwm", 120) or 1023
        if pure_rotation:
            pivot_limit = self._pwm_limit("pivot_max_pwm", pwm_limit)
            if pivot_limit > 0:
                pwm_limit = pivot_limit
        targets = [int(pwm_limit * speed / full_scale_speed) for speed in speeds]
        if apply_compensation and bool(motion.get("open_loop_static_compensation_enabled", False)):
            targets = apply_open_loop_static_compensation(targets, pwm_limit, self.config.get("motors", []))
        return [max(-pwm_limit, min(pwm_limit, target)) for target in targets]

    def _open_loop_full_scale_speed_mps(self, pure_rotation: bool) -> float:
        motion = self._motion()
        configured_limit = max_wheel_speed_mps(self.config)
        if pure_rotation:
            wheelbase = float(motion.get("wheelbase_m", 0.0))
            track_width = float(motion.get("track_width_m", 0.0))
            max_angular = float(motion.get("max_angular_speed_radps", 0.0))
            radius = hypot(wheelbase / 2.0, track_width / 2.0)
            full_scale_speed = radius * max_angular * self._mapping_scale("angular_scale", 0.35)
        else:
            max_linear = float(motion.get("max_linear_speed_mps", 0.0))
            full_scale_speed = max_linear * self._mapping_scale("linear_scale", 0.12)
        if configured_limit > 0.0 and full_scale_speed > configured_limit:
            return configured_limit
        return full_scale_speed

    def _pid_target_rpm_limit(self, pure_rotation: bool) -> float:
        motion = self._motion()
        max_wheel_rpm = float(motion.get("max_wheel_rpm", 0.0))
        limit = float(motion.get("pid_max_target_rpm", max_wheel_rpm))
        if pure_rotation:
            pivot_limit = float(motion.get("pid_pivot_max_target_rpm", limit))
            if pivot_limit > 0.0:
                limit = min(limit, pivot_limit) if limit > 0.0 else pivot_limit
        if max_wheel_rpm > 0.0:
            limit = min(limit, max_wheel_rpm) if limit > 0.0 else max_wheel_rpm
        return max(0.0, limit)

    def _translation_deadzone_mps(self) -> float:
        motion = self._motion()
        raw = max(0.0, float(motion.get("translation_deadzone", 0.12)))
        explicit = motion.get("translation_deadzone_mps")
        if explicit is not None:
            return max(0.0, float(explicit))
        if raw <= 1.0:
            max_linear = float(motion.get("max_linear_speed_mps", 0.0))
            full_scale_speed = max_linear * self._mapping_scale("linear_scale", 0.12)
            if full_scale_speed > 0.0:
                return raw * full_scale_speed
        return raw

    def _mapping_scale(self, key: str, default: float) -> float:
        return max(0.0, min(1.0, float(self.mapping.get(key, default))))

    def _pwm_limit(self, key: str, default: int) -> int:
        try:
            return max(0, abs(int(self._motion().get(key, default))))
        except (TypeError, ValueError):
            return max(0, abs(int(default)))

    def _motion(self) -> dict[str, Any]:
        motion = self.config.get("motion", {})
        return motion if isinstance(motion, dict) else {}

    def _validate_motion_config(self) -> None:
        motion = self._motion()
        required = ("wheelbase_m", "track_width_m", "wheel_diameter_m", "max_wheel_rpm")
        missing = [key for key in required if float(motion.get(key, 0.0)) <= 0.0]
        if missing:
            raise ValueError(f"v29 4WIS config missing: {', '.join(missing)}")
