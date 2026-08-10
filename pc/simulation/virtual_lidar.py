from __future__ import annotations

import math
from dataclasses import dataclass

from .field_model import FieldModel


@dataclass(frozen=True)
class VirtualLidarReading:
    front_mm: float
    left_mm: float
    right_mm: float
    rear_mm: float


class VirtualLidar:
    def __init__(self, field: FieldModel, max_distance_mm: float | None = None, step_mm: float = 10.0) -> None:
        self.field = field
        self.max_distance_mm = max_distance_mm or max(field.width_mm, field.height_mm)
        self.step_mm = max(1.0, step_mm)

    def scan(self, x_mm: float, y_mm: float, theta_deg: float) -> VirtualLidarReading:
        return VirtualLidarReading(
            front_mm=self.cast_ray(x_mm, y_mm, theta_deg),
            left_mm=self.cast_ray(x_mm, y_mm, theta_deg + 90.0),
            right_mm=self.cast_ray(x_mm, y_mm, theta_deg - 90.0),
            rear_mm=self.cast_ray(x_mm, y_mm, theta_deg + 180.0),
        )

    def cast_ray(self, x_mm: float, y_mm: float, theta_deg: float) -> float:
        theta = math.radians(theta_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        distance = 0.0
        while distance <= self.max_distance_mm:
            px = x_mm + cos_t * distance
            py = y_mm + sin_t * distance
            if not self.field.contains_point(px, py) or self.field.collides_with_obstacle(px, py):
                return distance
            distance += self.step_mm
        return self.max_distance_mm
