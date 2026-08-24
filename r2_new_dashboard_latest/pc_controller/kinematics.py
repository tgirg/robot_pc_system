"""Four wheel independent steering kinematics."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, pi
from typing import Mapping, Sequence

WHEEL_NAMES = ("FL", "FR", "RL", "RR")


@dataclass(frozen=True)
class WheelVector:
    """Ground-frame target vector for one wheel."""

    name: str
    vx: float
    vy: float
    speed_mps: float
    angle_deg: float


def wheel_positions(wheelbase_m: float, track_width_m: float) -> list[tuple[float, float]]:
    """Return wheel positions in body coordinates."""
    half_wheelbase = wheelbase_m / 2.0
    half_track = track_width_m / 2.0
    return [
        (half_wheelbase, half_track),
        (half_wheelbase, -half_track),
        (-half_wheelbase, half_track),
        (-half_wheelbase, -half_track),
    ]


def max_wheel_speed_mps(config: Mapping[str, object]) -> float:
    """Calculate the configured maximum wheel surface speed."""
    motion = config.get("motion", {}) if isinstance(config.get("motion", {}), Mapping) else {}
    diameter = float(motion.get("wheel_diameter_m", 0.0))
    max_rpm = float(motion.get("max_wheel_rpm", 0.0))
    explicit = float(motion.get("max_linear_speed_mps", 0.0))
    rpm_limit = (pi * diameter * max_rpm) / 60.0 if diameter > 0.0 and max_rpm > 0.0 else 0.0
    if explicit > 0.0 and rpm_limit > 0.0:
        return min(explicit, rpm_limit)
    return explicit or rpm_limit


def calculate_wheel_vectors(
    vx: float,
    vy: float,
    omega: float,
    config: Mapping[str, object],
    last_angles_deg: Sequence[float] | None = None,
) -> list[WheelVector]:
    """Calculate per-wheel speed vectors from body velocity commands."""
    motion = config.get("motion", {}) if isinstance(config.get("motion", {}), Mapping) else {}
    wheelbase = float(motion.get("wheelbase_m", 0.0))
    track_width = float(motion.get("track_width_m", 0.0))
    if wheelbase <= 0.0 or track_width <= 0.0:
        raise ValueError("wheelbase_m and track_width_m must be set")

    vectors: list[WheelVector] = []
    positions = wheel_positions(wheelbase, track_width)
    last = list(last_angles_deg or [0.0, 0.0, 0.0, 0.0])
    for index, (x_i, y_i) in enumerate(positions):
        wheel_vx = vx - omega * y_i
        wheel_vy = vy + omega * x_i
        speed = hypot(wheel_vx, wheel_vy)
        angle = last[index] if speed < 1e-9 else degrees(atan2(wheel_vy, wheel_vx))
        vectors.append(WheelVector(WHEEL_NAMES[index], wheel_vx, wheel_vy, speed, angle))

    limit = max_wheel_speed_mps(config)
    peak = max((vector.speed_mps for vector in vectors), default=0.0)
    if limit > 0.0 and peak > limit:
        scale = limit / peak
        vectors = [
            WheelVector(vector.name, vector.vx * scale, vector.vy * scale, vector.speed_mps * scale, vector.angle_deg)
            for vector in vectors
        ]
    return vectors


def wheel_speed_mps_to_rpm(speed_mps: float, config: Mapping[str, object]) -> float:
    """Convert wheel surface speed in m/s to wheel RPM."""
    motion = config.get("motion", {}) if isinstance(config.get("motion", {}), Mapping) else {}
    diameter = float(motion.get("wheel_diameter_m", 0.0))
    if diameter <= 0.0:
        raise ValueError("wheel_diameter_m must be set")
    return (speed_mps * 60.0) / (pi * diameter)
