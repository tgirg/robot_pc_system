from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from four_wheel_steer_model import WHEEL_NAMES, load_vehicle_config
from v29_drive_adapter import V29DriveAdapter, load_controller_mapping
from pc_controller.steering_optimizer import apply_wheel_direction_inversions


@dataclass(frozen=True)
class MotionPatternCase:
    name: str
    vx_percent: int
    vy_percent: int
    omega_percent: int
    expected_mode: str
    validator: Callable[["MotionPatternResult"], list[str]]


@dataclass(frozen=True)
class MotionPatternResult:
    name: str
    inputs: tuple[int, int, int]
    mode: str
    angles_deg: list[float]
    speeds_mps: list[float]
    pwm: list[int]
    line: str
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class MotionCheckReport:
    results: list[MotionPatternResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)


def run_4wis_motion_checks(
    vehicle_config: Mapping[str, Any] | None = None,
    controller_mapping: Mapping[str, Any] | None = None,
    *,
    max_pwm: int = 120,
) -> MotionCheckReport:
    config = dict(vehicle_config or load_vehicle_config())
    mapping = dict(controller_mapping or load_controller_mapping())
    adapter = V29DriveAdapter(config, mapping)
    results: list[MotionPatternResult] = []
    for seq, case in enumerate(_motion_cases(mapping), start=1):
        adapter.reset([0.0, 0.0, 0.0, 0.0])
        output = adapter.build_drive(
            seq,
            case.vx_percent / 100.0,
            case.vy_percent / 100.0,
            case.omega_percent / 100.0,
            armed=True,
            max_pwm=max_pwm,
        )
        message = json.loads(output.line)
        angles = [float(value) for value in message.get("steer_deg", [])]
        pwm = [int(round(float(value))) for value in message.get("drive_target", [])]
        speeds = [float(value) for value in output.telemetry.speeds_mps]
        mode = (output.telemetry.detail or "").split(" / ", 1)[0]
        result = MotionPatternResult(
            name=case.name,
            inputs=(case.vx_percent, case.vy_percent, case.omega_percent),
            mode=mode,
            angles_deg=angles,
            speeds_mps=speeds,
            pwm=pwm,
            line=output.line,
            failures=[],
        )
        failures = _common_failures(result, config, max_pwm)
        if mode != case.expected_mode:
            failures.append(f"mode expected {case.expected_mode}, got {mode or '-'}")
        failures.extend(case.validator(result))
        results.append(
            MotionPatternResult(
                name=result.name,
                inputs=result.inputs,
                mode=result.mode,
                angles_deg=result.angles_deg,
                speeds_mps=result.speeds_mps,
                pwm=result.pwm,
                line=result.line,
                failures=failures,
            )
        )
    return MotionCheckReport(results)


def format_4wis_motion_check_report(report: MotionCheckReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"4WIS動作パターンチェック: {status} ({report.passed_count}/{len(report.results)})",
        "実機なしのv29送信値生成チェックです。サーボ実角、モーター配線、接地状態は実機で確認してください。",
        "",
    ]
    for result in report.results:
        mark = "OK" if result.passed else "NG"
        vx, vy, omega = result.inputs
        lines.append(
            f"{mark} {result.name}: vx={vx:+d} vy={vy:+d} omega={omega:+d} / {result.mode}"
        )
        lines.append(
            "  angle="
            + _format_numbers(result.angles_deg, precision=1)
            + " / pwm="
            + _format_numbers(result.pwm, precision=0)
        )
        for failure in result.failures:
            lines.append(f"  - {failure}")
    return "\n".join(lines)


def _motion_cases(mapping: Mapping[str, Any]) -> list[MotionPatternCase]:
    pivot_flags = mapping.get("pivot_motor_direction_inverted", [False, False, False, False])
    pivot_left_signs = [int(value) for value in apply_wheel_direction_inversions([-1, 1, -1, 1], pivot_flags)]
    pivot_right_signs = [int(value) for value in apply_wheel_direction_inversions([1, -1, 1, -1], pivot_flags)]
    return [
        MotionPatternCase("前進", 60, 0, 0, "TRANSLATE", _validate_forward),
        MotionPatternCase("後退", -60, 0, 0, "TRANSLATE", _validate_backward),
        MotionPatternCase("左平行移動", 0, 60, 0, "TRANSLATE", _validate_strafe_left),
        MotionPatternCase("右平行移動", 0, -60, 0, "TRANSLATE", _validate_strafe_right),
        MotionPatternCase(
            "左その場旋回",
            0,
            0,
            60,
            "PIVOT",
            lambda result: _validate_pivot(result, pivot_left_signs),
        ),
        MotionPatternCase(
            "右その場旋回",
            0,
            0,
            -60,
            "PIVOT",
            lambda result: _validate_pivot(result, pivot_right_signs),
        ),
        MotionPatternCase("前進+左旋回", 60, 0, 60, "ARC", _validate_forward_left_arc),
        MotionPatternCase("前進+右旋回", 60, 0, -60, "ARC", _validate_forward_right_arc),
        MotionPatternCase("右移動+左旋回", 0, -60, 60, "ARC", _validate_right_strafe_left_arc),
        MotionPatternCase("右移動+右旋回", 0, -60, -60, "ARC", _validate_right_strafe_right_arc),
        MotionPatternCase("斜め+旋回", 30, 60, -60, "MIX", _validate_multi_axis_vector),
    ]


def _common_failures(result: MotionPatternResult, config: Mapping[str, Any], max_pwm: int) -> list[str]:
    failures: list[str] = []
    if len(result.angles_deg) != 4:
        failures.append(f"steer_deg length expected 4, got {len(result.angles_deg)}")
    if len(result.pwm) != 4:
        failures.append(f"drive_target length expected 4, got {len(result.pwm)}")
    if len(result.speeds_mps) != 4:
        failures.append(f"speeds length expected 4, got {len(result.speeds_mps)}")
    if any(not math.isfinite(value) for value in result.angles_deg + result.speeds_mps):
        failures.append("non-finite angle or speed")
    if any(abs(value) > max_pwm for value in result.pwm):
        failures.append(f"PWM exceeds max {max_pwm}")

    servos = config.get("servos", [])
    for index, angle in enumerate(result.angles_deg):
        servo = servos[index] if index < len(servos) and isinstance(servos[index], Mapping) else {}
        lower = float(servo.get("min_angle_deg", -135.0))
        upper = float(servo.get("max_angle_deg", 135.0))
        if angle < lower - 1e-6 or angle > upper + 1e-6:
            failures.append(f"{WHEEL_NAMES[index]} angle {angle:.1f} outside {lower:.1f}..{upper:.1f}")
    return failures


def _effective_vectors(result: MotionPatternResult) -> list[tuple[float, float]]:
    vectors: list[tuple[float, float]] = []
    for angle, speed in zip(result.angles_deg, result.speeds_mps):
        rad = math.radians(angle)
        vectors.append((math.cos(rad) * speed, math.sin(rad) * speed))
    return vectors


def _validate_forward(result: MotionPatternResult) -> list[str]:
    return _check_angles(result, [0.0, 0.0, 0.0, 0.0]) + _check_pwm_signs(result, [1, 1, 1, 1])


def _validate_backward(result: MotionPatternResult) -> list[str]:
    return _check_angles(result, [0.0, 0.0, 0.0, 0.0]) + _check_pwm_signs(result, [-1, -1, -1, -1])


def _validate_strafe_left(result: MotionPatternResult) -> list[str]:
    return _check_angles(result, [90.0, 90.0, 90.0, 90.0]) + _check_pwm_signs(result, [1, 1, 1, 1])


def _validate_strafe_right(result: MotionPatternResult) -> list[str]:
    return _check_angles(result, [-90.0, -90.0, -90.0, -90.0]) + _check_pwm_signs(result, [1, 1, 1, 1])


def _validate_pivot(result: MotionPatternResult, signs: Sequence[int]) -> list[str]:
    failures = _check_angles(result, [-45.0, 45.0, 45.0, -45.0])
    failures.extend(_check_pwm_signs(result, signs))
    failures.extend(_check_abs_pwm_equal(result))
    return failures


def _validate_forward_left_arc(result: MotionPatternResult) -> list[str]:
    failures = _check_pwm_signs(result, [1, 1, 1, 1])
    failures.extend(_check_angles(result, [-16.2, -34.7, 16.2, 34.7]))
    failures.extend(_check_pwm_ratio(result, [(1, 0), (3, 2)]))
    return failures


def _validate_forward_right_arc(result: MotionPatternResult) -> list[str]:
    failures = _check_pwm_signs(result, [1, 1, 1, 1])
    failures.extend(_check_angles(result, [34.7, 16.2, -34.7, -16.2]))
    failures.extend(_check_pwm_ratio(result, [(0, 1), (2, 3)]))
    return failures


def _validate_right_strafe_left_arc(result: MotionPatternResult) -> list[str]:
    failures = _check_pwm_signs(result, [1, 1, 1, 1])
    failures.extend(_check_angles(result, [-73.8, -106.2, -55.3, -124.7]))
    failures.extend(_check_pwm_ratio(result, [(2, 0), (3, 1)]))
    return failures


def _validate_right_strafe_right_arc(result: MotionPatternResult) -> list[str]:
    failures = _check_pwm_signs(result, [1, 1, 1, 1])
    failures.extend(_check_angles(result, [-124.7, -55.3, -106.2, -73.8]))
    failures.extend(_check_pwm_ratio(result, [(0, 2), (1, 3)]))
    return failures


def _validate_multi_axis_vector(result: MotionPatternResult) -> list[str]:
    failures = _check_angles(result, [-71.2, 52.0, 19.4, -8.7])
    failures.extend(_check_pwm_signs(result, [-1, 1, -1, 1]))
    return failures


def _check_angles(result: MotionPatternResult, expected: Sequence[float], tolerance: float = 0.2) -> list[str]:
    failures: list[str] = []
    for index, (actual, target) in enumerate(zip(result.angles_deg, expected)):
        if abs(actual - target) > tolerance:
            failures.append(f"{WHEEL_NAMES[index]} angle expected {target:+.1f}, got {actual:+.1f}")
    return failures


def _check_pwm_signs(result: MotionPatternResult, signs: Sequence[int]) -> list[str]:
    failures: list[str] = []
    for index, (value, sign) in enumerate(zip(result.pwm, signs)):
        if sign > 0 and value <= 0:
            failures.append(f"{WHEEL_NAMES[index]} PWM expected positive, got {value:+d}")
        elif sign < 0 and value >= 0:
            failures.append(f"{WHEEL_NAMES[index]} PWM expected negative, got {value:+d}")
    return failures


def _check_effective_signs(result: MotionPatternResult, signs: Sequence[tuple[int, int]]) -> list[str]:
    failures: list[str] = []
    for index, ((vx, vy), (sx, sy)) in enumerate(zip(_effective_vectors(result), signs)):
        if sx > 0 and vx <= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective vx expected positive")
        elif sx < 0 and vx >= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective vx expected negative")
        if sy > 0 and vy <= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective vy expected positive")
        elif sy < 0 and vy >= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective vy expected negative")
    return failures


def _check_effective_vx_positive(result: MotionPatternResult) -> list[str]:
    return [f"{WHEEL_NAMES[index]} effective vx expected forward" for index, (vx, _) in enumerate(_effective_vectors(result)) if vx <= 0.0]


def _check_effective_vy_negative(result: MotionPatternResult) -> list[str]:
    return [f"{WHEEL_NAMES[index]} effective vy expected right" for index, (_, vy) in enumerate(_effective_vectors(result)) if vy >= 0.0]


def _check_effective_vx_signs(result: MotionPatternResult, signs: Sequence[int]) -> list[str]:
    return _check_effective_axis_signs(result, axis=0, signs=signs)


def _check_effective_vy_signs(result: MotionPatternResult, signs: Sequence[int]) -> list[str]:
    return _check_effective_axis_signs(result, axis=1, signs=signs)


def _check_effective_axis_signs(result: MotionPatternResult, axis: int, signs: Sequence[int]) -> list[str]:
    failures: list[str] = []
    axis_name = "vx" if axis == 0 else "vy"
    for index, vector in enumerate(_effective_vectors(result)):
        value = vector[axis]
        sign = signs[index]
        if sign > 0 and value <= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective {axis_name} expected positive")
        elif sign < 0 and value >= 0.0:
            failures.append(f"{WHEEL_NAMES[index]} effective {axis_name} expected negative")
    return failures


def _check_abs_pwm_equal(result: MotionPatternResult, tolerance: int = 1) -> list[str]:
    values = [abs(value) for value in result.pwm]
    if not values:
        return ["PWM missing"]
    return [] if max(values) - min(values) <= tolerance else [f"abs PWM should be equal, got {values}"]


def _check_pwm_ratio(result: MotionPatternResult, less_pairs: Sequence[tuple[int, int]]) -> list[str]:
    failures: list[str] = []
    for low, high in less_pairs:
        if abs(result.pwm[low]) >= abs(result.pwm[high]):
            failures.append(
                f"{WHEEL_NAMES[low]} PWM abs should be lower than {WHEEL_NAMES[high]} ({result.pwm[low]} vs {result.pwm[high]})"
            )
    return failures


def _format_numbers(values: Sequence[float | int], *, precision: int) -> str:
    if precision <= 0:
        return "[" + ", ".join(f"{int(round(float(value))):+d}" for value in values) + "]"
    return "[" + ", ".join(f"{float(value):+.{precision}f}" for value in values) + "]"


if __name__ == "__main__":
    print(format_4wis_motion_check_report(run_4wis_motion_checks()))
