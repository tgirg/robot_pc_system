from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class InertialPose:
    x_mm: float
    y_mm: float
    theta_deg: float
    vx_mm_s: float
    vy_mm_s: float


class ImuInertialEstimator:
    """Short-time field pose estimate from IMU acceleration.

    IMU-only position estimation drifts quickly. This class is intentionally
    conservative: it thresholds small acceleration, damps velocity, and should
    be corrected later by optical odometry, encoder, or field landmarks.
    """

    G_MM_S2 = 9806.65

    def __init__(self) -> None:
        self.x_mm = 0.0
        self.y_mm = 0.0
        self.vx_mm_s = 0.0
        self.vy_mm_s = 0.0
        self.last_time_s: float | None = None
        self.enabled = False

    def reset(self, x_mm: float, y_mm: float) -> None:
        self.x_mm = float(x_mm)
        self.y_mm = float(y_mm)
        self.vx_mm_s = 0.0
        self.vy_mm_s = 0.0
        self.last_time_s = None

    def update(
        self,
        *,
        accel_x_g: float,
        accel_y_g: float,
        yaw_deg: float,
        timestamp_s: float,
        field_width_mm: float,
        field_height_mm: float,
    ) -> InertialPose:
        if self.last_time_s is None:
            self.last_time_s = timestamp_s
            return self.pose(yaw_deg)

        dt = max(0.001, min(0.08, timestamp_s - self.last_time_s))
        self.last_time_s = timestamp_s

        ax_g = self._deadband(float(accel_x_g), 0.035)
        ay_g = self._deadband(float(accel_y_g), 0.035)

        yaw_rad = math.radians(float(yaw_deg))
        body_ax = ax_g * self.G_MM_S2
        body_ay = ay_g * self.G_MM_S2
        field_ax = body_ax * math.cos(yaw_rad) - body_ay * math.sin(yaw_rad)
        field_ay = body_ax * math.sin(yaw_rad) + body_ay * math.cos(yaw_rad)

        self.vx_mm_s += field_ax * dt
        self.vy_mm_s += field_ay * dt

        # Strong damping keeps stationary sensor noise from becoming runaway drift.
        damping = 0.88 ** (dt / 0.02)
        self.vx_mm_s *= damping
        self.vy_mm_s *= damping

        if ax_g == 0.0 and ay_g == 0.0 and math.hypot(self.vx_mm_s, self.vy_mm_s) < 20.0:
            self.vx_mm_s = 0.0
            self.vy_mm_s = 0.0

        self.x_mm = max(0.0, min(float(field_width_mm), self.x_mm + self.vx_mm_s * dt))
        self.y_mm = max(0.0, min(float(field_height_mm), self.y_mm + self.vy_mm_s * dt))
        return self.pose(yaw_deg)

    def pose(self, yaw_deg: float) -> InertialPose:
        return InertialPose(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            theta_deg=float(yaw_deg) % 360.0,
            vx_mm_s=self.vx_mm_s,
            vy_mm_s=self.vy_mm_s,
        )

    @staticmethod
    def _deadband(value: float, threshold: float) -> float:
        return 0.0 if abs(value) < threshold else value
