"""Servo angle optimization and oblique-transition state handling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan2, cos, degrees, hypot, radians, sin, tan
from typing import Iterable, Sequence


class TransitionState(str, Enum):
    DRIVE = "DRIVE"
    DECELERATE = "DECELERATE"
    ALIGN = "ALIGN"
    SETTLE = "SETTLE"
    ACCELERATE = "ACCELERATE"
    BLOCKED = "BLOCKED"


PIVOT_TARGET_ANGLES_DEG = (135.0, 45.0, -135.0, -45.0)
PIVOT_MOTOR_SIGNS = (1.0, 1.0, 1.0, 1.0)
PIVOT_GLOBAL_SIGN = 1.0
COORDINATED_4WS_MAX_STEER_DEG = 45.0


def apply_wheel_direction_inversions(
    speeds: Sequence[float],
    inverted: Sequence[bool] | None,
) -> list[float]:
    """Apply an explicit per-wheel direction correction to FL/FR/RL/RR."""
    values = [float(value) for value in speeds]
    flags = [False, False, False, False] if inverted is None else list(inverted)
    if len(values) != 4 or len(flags) != 4:
        raise ValueError("wheel direction correction must have 4 entries")
    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("wheel direction correction entries must be boolean")
    return [-value if flags[index] else value for index, value in enumerate(values)]


def apply_open_loop_static_compensation(
    targets: Sequence[float],
    pwm_limit: int,
    motors: Sequence[object],
) -> list[int]:
    """Lift non-zero open-loop targets above each motor's measured breakaway PWM.

    Zero remains zero. A full-scale target remains full scale, while intermediate
    targets are linearly mapped from the direction-specific static PWM to the
    configured limit. This preserves inner/outer ordering without leaving a
    commanded wheel stalled below its usable range.
    """
    values = [float(value) for value in targets]
    if len(values) != 4 or len(motors) != 4:
        raise ValueError("open-loop compensation requires 4 targets and 4 motors")
    limit = max(0, min(1023, int(pwm_limit)))
    if limit <= 0:
        return [0, 0, 0, 0]

    compensated: list[int] = []
    for index, target in enumerate(values):
        if abs(target) < 1e-9:
            compensated.append(0)
            continue
        motor = motors[index]
        if not isinstance(motor, dict):
            raise ValueError("motor compensation entries must be objects")
        key = "ff_static_pwm_pos" if target > 0.0 else "ff_static_pwm_neg"
        static_pwm = max(0.0, min(float(limit), float(motor.get(key, 0.0))))
        ratio = min(1.0, abs(target) / float(limit))
        magnitude = static_pwm + ratio * (float(limit) - static_pwm)
        signed = magnitude if target > 0.0 else -magnitude
        compensated.append(max(-limit, min(limit, int(round(signed)))))
    return compensated


@dataclass(frozen=True)
class ServoLimit:
    min_angle_deg: float
    max_angle_deg: float
    calibrated: bool = True


@dataclass(frozen=True)
class OptimizerSettings:
    hysteresis_deg: float = 20.0
    end_margin_deg: float = 10.0
    direction_change_penalty: float = 8.0
    end_margin_penalty: float = 25.0
    realign_threshold_deg: float = 30.0
    small_error_full_speed_deg: float = 8.0


@dataclass(frozen=True)
class OptimizedWheelCommand:
    angle_deg: float
    speed: float
    representation: str
    fault: str | None = None
    switched: bool = False
    drive_direction_reversed: bool = False


@dataclass
class TransitionOutput:
    state: TransitionState
    speed_scale: float
    allow_drive: bool
    blocked_reason: str | None = None


def normalize_angle_deg(angle: float) -> float:
    """Normalize an angle to [-180, 180)."""
    normalized = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if normalized == -180.0 else normalized


def angle_delta_deg(target: float, current: float) -> float:
    """Return signed shortest angular delta from current to target."""
    return normalize_angle_deg(target - current)


def vector_angle_average_deg(angles: Iterable[float]) -> float:
    """Average circular angles using unit vectors."""
    x = 0.0
    y = 0.0
    for angle in angles:
        x += cos(radians(angle))
        y += sin(radians(angle))
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return 0.0
    return degrees(atan2(y, x))


def _candidate_angles(base_angle: float, reversed_drive: bool) -> Iterable[float]:
    offset = 180.0 if reversed_drive else 0.0
    for turns in range(-2, 3):
        yield base_angle + offset + 360.0 * turns


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _end_margin_cost(angle: float, limit: ServoLimit, settings: OptimizerSettings) -> float:
    low_margin = angle - limit.min_angle_deg
    high_margin = limit.max_angle_deg - angle
    nearest = min(low_margin, high_margin)
    if nearest >= settings.end_margin_deg:
        return 0.0
    return settings.end_margin_penalty * (settings.end_margin_deg - nearest) / settings.end_margin_deg


def coordinated_4ws_speed_factors(
    steer_input: float,
    wheelbase_m: float,
    track_width_m: float,
    max_steer_deg: float = COORDINATED_4WS_MAX_STEER_DEG,
    positive_steer_turns_right: bool = True,
) -> list[float]:
    """Return outer-limited FL/FR/RL/RR speed factors for coordinated 4WS."""
    steer_deg = abs(_clamp(steer_input, -1.0, 1.0)) * max(0.0, max_steer_deg)
    if wheelbase_m <= 0.0 or track_width_m <= 0.0 or steer_deg < 1e-6:
        return [1.0, 1.0, 1.0, 1.0]

    steer_rad = radians(min(89.0, steer_deg))
    center_radius = wheelbase_m / (2.0 * max(1e-9, tan(steer_rad)))
    turn_direction = 1.0 if steer_input >= 0.0 else -1.0
    if positive_steer_turns_right:
        turn_direction *= -1.0
    icr_y = turn_direction * center_radius

    half_wheelbase = wheelbase_m / 2.0
    half_track = track_width_m / 2.0
    positions = (
        (half_wheelbase, half_track),
        (half_wheelbase, -half_track),
        (-half_wheelbase, half_track),
        (-half_wheelbase, -half_track),
    )
    radii = [hypot(x, y - icr_y) for x, y in positions]
    outer_radius = max(radii)
    if outer_radius <= 1e-9:
        return [1.0, 1.0, 1.0, 1.0]
    return [radius / outer_radius for radius in radii]


def optimize_wheel(
    target_angle_deg: float,
    target_speed: float,
    current_angle_deg: float,
    servo_limit: ServoLimit,
    previous_representation: str | None = None,
    previous_speed_sign: int = 1,
    settings: OptimizerSettings | None = None,
    allow_reversed_drive: bool = True,
) -> OptimizedWheelCommand:
    """Pick a servo angle and motor sign that minimize steering motion."""
    settings = settings or OptimizerSettings()
    if abs(target_speed) < 1e-9:
        return OptimizedWheelCommand(current_angle_deg, 0.0, previous_representation or "hold")
    if not servo_limit.calibrated:
        return OptimizedWheelCommand(current_angle_deg, 0.0, "fault", "servo_not_calibrated")

    candidates: list[tuple[float, float, str, bool]] = []
    drive_options = (False, True) if allow_reversed_drive else (False,)
    for reversed_drive in drive_options:
        representation = "B" if reversed_drive else "A"
        signed_speed = -target_speed if reversed_drive else target_speed
        for angle in _candidate_angles(target_angle_deg, reversed_drive):
            if servo_limit.min_angle_deg <= angle <= servo_limit.max_angle_deg:
                delta = abs(angle_delta_deg(angle, current_angle_deg))
                cost = delta + _end_margin_cost(angle, servo_limit, settings)
                if (signed_speed >= 0) != (previous_speed_sign >= 0):
                    cost += settings.direction_change_penalty
                candidates.append((cost, angle, representation, reversed_drive))

    if not candidates:
        return OptimizedWheelCommand(current_angle_deg, 0.0, "fault", "no_servo_candidate")

    candidates.sort(key=lambda item: item[0])
    best_cost, best_angle, best_representation, best_reversed = candidates[0]

    if previous_representation is not None:
        current_options = [item for item in candidates if item[2] == previous_representation]
        if current_options:
            current_cost, current_angle, _, current_reversed = current_options[0]
            if best_representation != previous_representation and current_cost - best_cost < settings.hysteresis_deg:
                best_angle = current_angle
                best_representation = previous_representation
                best_reversed = current_reversed

    signed_speed = -target_speed if best_reversed else target_speed
    return OptimizedWheelCommand(
        angle_deg=best_angle,
        speed=signed_speed,
        representation=best_representation,
        switched=previous_representation is not None and best_representation != previous_representation,
        drive_direction_reversed=best_reversed,
    )


def optimize_pure_translation(
    translation_angle_deg: float,
    translation_speed: float,
    current_angles_deg: Sequence[float],
    servo_limits: Sequence[ServoLimit],
    previous_representation: str | None = None,
    previous_speed_signs: Sequence[int] | None = None,
    settings: OptimizerSettings | None = None,
) -> list[OptimizedWheelCommand]:
    """Prefer a common four-wheel representation for pure oblique translation."""
    settings = settings or OptimizerSettings()
    previous_speed_signs = previous_speed_signs or [1, 1, 1, 1]

    group_candidates: list[tuple[float, str, float, bool]] = []
    for reversed_drive in (False, True):
        representation = "B" if reversed_drive else "A"
        for angle in _candidate_angles(translation_angle_deg, reversed_drive):
            if all(limit.calibrated and limit.min_angle_deg <= angle <= limit.max_angle_deg for limit in servo_limits):
                deltas = [abs(angle_delta_deg(angle, current)) for current in current_angles_deg]
                cost = sum(deltas) + max(deltas) * 0.5
                cost += sum(_end_margin_cost(angle, limit, settings) for limit in servo_limits)
                signed_speed = -translation_speed if reversed_drive else translation_speed
                for previous_sign in previous_speed_signs:
                    if (signed_speed >= 0) != (previous_sign >= 0):
                        cost += settings.direction_change_penalty
                group_candidates.append((cost, representation, angle, reversed_drive))

    if group_candidates:
        group_candidates.sort(key=lambda item: item[0])
        _, representation, angle, reversed_drive = group_candidates[0]
        signed_speed = -translation_speed if reversed_drive else translation_speed
        return [
            OptimizedWheelCommand(
                angle,
                signed_speed,
                representation,
                switched=previous_representation is not None and representation != previous_representation,
                drive_direction_reversed=reversed_drive,
            )
            for _ in range(4)
        ]

    return [
        optimize_wheel(
            translation_angle_deg,
            translation_speed,
            current_angles_deg[index],
            servo_limits[index],
            previous_representation=previous_representation,
            previous_speed_sign=previous_speed_signs[index],
            settings=settings,
        )
        for index in range(4)
    ]


def optimize_coordinated_four_ws(
    translation_angle_deg: float | None,
    translation_speed: float,
    steer_input: float,
    current_angles_deg: Sequence[float],
    servo_limits: Sequence[ServoLimit],
    previous_representation: str | None = None,
    previous_speed_signs: Sequence[int] | None = None,
    settings: OptimizerSettings | None = None,
    max_steer_deg: float = COORDINATED_4WS_MAX_STEER_DEG,
    wheelbase_m: float | None = None,
    track_width_m: float | None = None,
    inner_outer_speed: bool = False,
    positive_steer_turns_right: bool = True,
) -> list[OptimizedWheelCommand]:
    """Use the v29 MIX posture: front pair base+steer, rear pair base-steer."""
    settings = settings or OptimizerSettings()
    previous_speed_signs = previous_speed_signs or [1, 1, 1, 1]

    if abs(translation_speed) < 1e-9:
        return [
            OptimizedWheelCommand(current_angles_deg[index], 0.0, previous_representation or "hold")
            for index in range(4)
        ]
    if any(not limit.calibrated for limit in servo_limits):
        return [
            OptimizedWheelCommand(current_angles_deg[index], 0.0, "fault", "servo_not_calibrated")
            for index in range(4)
        ]

    base_angle = 0.0 if translation_angle_deg is None else translation_angle_deg
    steer_deg = _clamp(steer_input, -1.0, 1.0) * max(0.0, max_steer_deg)
    desired_angles = (
        base_angle + steer_deg,
        base_angle + steer_deg,
        base_angle - steer_deg,
        base_angle - steer_deg,
    )
    speed_factors = [1.0, 1.0, 1.0, 1.0]
    if inner_outer_speed and wheelbase_m is not None and track_width_m is not None:
        speed_factors = coordinated_4ws_speed_factors(
            steer_input,
            wheelbase_m,
            track_width_m,
            max_steer_deg=max_steer_deg,
            positive_steer_turns_right=positive_steer_turns_right,
        )

    group_candidates: list[tuple[float, str, bool, list[float], list[float]]] = []
    for reversed_drive in (False, True):
        representation = "B" if reversed_drive else "A"
        direction = -1.0 if reversed_drive else 1.0
        signed_speeds = [translation_speed * factor * direction for factor in speed_factors]
        angles: list[float] = []
        deltas: list[float] = []
        cost = 0.0

        for index, target_angle in enumerate(desired_angles):
            limit = servo_limits[index]
            wheel_candidates: list[tuple[float, float, float]] = []
            for angle in _candidate_angles(target_angle, reversed_drive):
                if limit.min_angle_deg <= angle <= limit.max_angle_deg:
                    delta = abs(angle_delta_deg(angle, current_angles_deg[index]))
                    wheel_cost = delta + _end_margin_cost(angle, limit, settings)
                    wheel_candidates.append((wheel_cost, angle, delta))
            if not wheel_candidates:
                break
            wheel_cost, angle, delta = min(wheel_candidates, key=lambda item: item[0])
            angles.append(angle)
            deltas.append(delta)
            cost += wheel_cost
        else:
            cost += max(deltas, default=0.0) * 0.5
            for index, previous_sign in enumerate(previous_speed_signs):
                if (signed_speeds[index] >= 0.0) != (previous_sign >= 0):
                    cost += settings.direction_change_penalty
            group_candidates.append((cost, representation, reversed_drive, angles, signed_speeds))

    if not group_candidates:
        return [
            OptimizedWheelCommand(current_angles_deg[index], 0.0, "fault", "no_coordinated_4ws_candidate")
            for index in range(4)
        ]

    group_candidates.sort(key=lambda item: item[0])
    best_cost, representation, reversed_drive, angles, signed_speeds = group_candidates[0]
    if previous_representation is not None:
        current_options = [item for item in group_candidates if item[1] == previous_representation]
        if current_options:
            current_cost, current_representation, current_reversed, current_angles, current_speeds = current_options[0]
            if representation != previous_representation and current_cost - best_cost < settings.hysteresis_deg:
                representation = current_representation
                reversed_drive = current_reversed
                angles = current_angles
                signed_speeds = current_speeds

    return [
        OptimizedWheelCommand(
            angle,
            signed_speeds[index],
            representation,
            switched=previous_representation is not None and representation != previous_representation,
            drive_direction_reversed=reversed_drive,
        )
        for index, angle in enumerate(angles)
    ]


def optimize_pivot_rotation(
    turn_speed: float,
    rotate_sign: float,
    current_angles_deg: Sequence[float],
    servo_limits: Sequence[ServoLimit],
) -> tuple[list[float], list[float]]:
    """Use the v29 zero-radius PIVOT steering posture and motor signs."""
    if abs(turn_speed) < 1e-9 or abs(rotate_sign) < 1e-9:
        return list(current_angles_deg), [0.0, 0.0, 0.0, 0.0]

    base_speed = PIVOT_GLOBAL_SIGN * (1.0 if rotate_sign > 0.0 else -1.0) * abs(turn_speed)
    steer: list[float] = []
    speeds: list[float] = []

    for index, target_angle in enumerate(PIVOT_TARGET_ANGLES_DEG):
        limit = servo_limits[index]
        if not limit.calibrated:
            return list(current_angles_deg), [0.0, 0.0, 0.0, 0.0]

        candidates: list[tuple[float, float, float]] = []
        for reversed_drive in (False, True):
            representation_sign = -1.0 if reversed_drive else 1.0
            for angle in _candidate_angles(target_angle, reversed_drive):
                if limit.min_angle_deg <= angle <= limit.max_angle_deg:
                    delta = abs(angle_delta_deg(angle, current_angles_deg[index]))
                    candidates.append((delta, angle, representation_sign))

        if not candidates:
            return list(current_angles_deg), [0.0, 0.0, 0.0, 0.0]

        _, selected_angle, representation_sign = min(candidates, key=lambda item: item[0])
        steer.append(selected_angle)
        speeds.append(base_speed * PIVOT_MOTOR_SIGNS[index] * representation_sign)

    return steer, speeds


def speed_scale_for_error(error_deg: float, settings: OptimizerSettings | None = None) -> float:
    """Scale wheel speed based on steering error."""
    settings = settings or OptimizerSettings()
    error = abs(error_deg)
    if error <= settings.small_error_full_speed_deg:
        return 1.0
    if error >= settings.realign_threshold_deg:
        return 0.0
    span = settings.realign_threshold_deg - settings.small_error_full_speed_deg
    return 1.0 - 0.8 * ((error - settings.small_error_full_speed_deg) / span)


class SteeringTransitionController:
    """Small state machine for stop-align-accelerate steering transitions."""

    def __init__(
        self,
        settings: OptimizerSettings | None = None,
        decel_time_ms: int = 200,
        accel_time_ms: int = 200,
        settle_time_ms: int = 100,
        alignment_timeout_ms: int = 2000,
    ) -> None:
        self.settings = settings or OptimizerSettings()
        self.decel_time_ms = decel_time_ms
        self.accel_time_ms = accel_time_ms
        self.settle_time_ms = settle_time_ms
        self.alignment_timeout_ms = alignment_timeout_ms
        self.state = TransitionState.DRIVE
        self.state_started_ms = 0
        self.last_target_angles = [0.0, 0.0, 0.0, 0.0]

    def reset(self, now_ms: int = 0) -> None:
        """Return to DRIVE state."""
        self.state = TransitionState.DRIVE
        self.state_started_ms = now_ms

    def update(
        self,
        now_ms: int,
        target_angles: Sequence[float],
        current_angles: Sequence[float],
        motor_direction_switch_needed: bool = False,
        input_cancelled: bool = False,
    ) -> TransitionOutput:
        """Advance the transition state and return drive permission."""
        max_error = max(abs(angle_delta_deg(t, c)) for t, c in zip(target_angles, current_angles))
        self.last_target_angles = list(target_angles)

        if input_cancelled and self.state in {TransitionState.DECELERATE, TransitionState.ALIGN, TransitionState.SETTLE}:
            self.state = TransitionState.DRIVE
            self.state_started_ms = now_ms
            return TransitionOutput(self.state, 0.0, False)

        if self.state == TransitionState.DRIVE:
            if max_error >= self.settings.realign_threshold_deg or motor_direction_switch_needed:
                self.state = TransitionState.DECELERATE
                self.state_started_ms = now_ms
                return TransitionOutput(self.state, 0.0, False)
            return TransitionOutput(self.state, speed_scale_for_error(max_error, self.settings), True)

        elapsed = now_ms - self.state_started_ms
        if self.state == TransitionState.DECELERATE:
            if elapsed >= self.decel_time_ms:
                self.state = TransitionState.ALIGN
                self.state_started_ms = now_ms
            return TransitionOutput(self.state, 0.0, False)

        if self.state == TransitionState.ALIGN:
            if elapsed >= self.alignment_timeout_ms:
                self.state = TransitionState.BLOCKED
                return TransitionOutput(self.state, 0.0, False, "alignment_timeout")
            if max_error <= self.settings.realign_threshold_deg / 6.0:
                self.state = TransitionState.SETTLE
                self.state_started_ms = now_ms
            return TransitionOutput(self.state, 0.0, False)

        if self.state == TransitionState.SETTLE:
            if max_error > self.settings.realign_threshold_deg:
                self.state = TransitionState.ALIGN
                self.state_started_ms = now_ms
                return TransitionOutput(self.state, 0.0, False)
            if elapsed >= self.settle_time_ms:
                self.state = TransitionState.ACCELERATE
                self.state_started_ms = now_ms
            return TransitionOutput(self.state, 0.0, False)

        if self.state == TransitionState.ACCELERATE:
            if max_error >= self.settings.realign_threshold_deg:
                self.state = TransitionState.DECELERATE
                self.state_started_ms = now_ms
                return TransitionOutput(self.state, 0.0, False)
            if elapsed >= self.accel_time_ms:
                self.state = TransitionState.DRIVE
                self.state_started_ms = now_ms
                return TransitionOutput(self.state, 1.0, True)
            return TransitionOutput(self.state, max(0.0, min(1.0, elapsed / self.accel_time_ms)), True)

        return TransitionOutput(TransitionState.BLOCKED, 0.0, False, "blocked")


def translation_angle_and_magnitude(vx: float, vy: float, deadzone: float) -> tuple[float | None, float]:
    """Return stable translation angle; None means hold the last angle."""
    magnitude = hypot(vx, vy)
    if magnitude < deadzone:
        return None, 0.0
    return degrees(atan2(vy, vx)), magnitude
