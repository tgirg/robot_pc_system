from __future__ import annotations

from dataclasses import dataclass

from .obstacle_model import RectObstacle

@dataclass
class FieldModel:
    width_mm: float = 3000.0
    height_mm: float = 2000.0
    grid_size_mm: float = 100.0
    obstacles: list[RectObstacle] | None = None

    @classmethod
    def from_config(cls, config: dict, obstacle_configs: list[dict] | None = None) -> "FieldModel":
        return cls(
            width_mm=float(config.get("width_mm", 3000)),
            height_mm=float(config.get("height_mm", 2000)),
            grid_size_mm=float(config.get("grid_size_mm", 100)),
            obstacles=[RectObstacle.from_config(item) for item in obstacle_configs or []],
        )

    def clamp_position(self, x_mm: float, y_mm: float) -> tuple[float, float, str]:
        clamped_x = max(0.0, min(self.width_mm, x_mm))
        clamped_y = max(0.0, min(self.height_mm, y_mm))
        status = "フィールド境界に到達" if (clamped_x, clamped_y) != (x_mm, y_mm) else ""
        return clamped_x, clamped_y, status

    def contains_point(self, x_mm: float, y_mm: float) -> bool:
        return 0.0 <= x_mm <= self.width_mm and 0.0 <= y_mm <= self.height_mm

    def collides_with_obstacle(self, x_mm: float, y_mm: float, margin_mm: float = 0.0) -> bool:
        return self.find_obstacle_at(x_mm, y_mm, margin_mm) is not None

    def find_obstacle_at(self, x_mm: float, y_mm: float, margin_mm: float = 0.0) -> RectObstacle | None:
        for obstacle in self.obstacles or []:
            if obstacle.contains(x_mm, y_mm, margin_mm):
                return obstacle
        return None

    def distance_to_nearest_boundary_m(self, x_mm: float, y_mm: float) -> float:
        distance_mm = min(x_mm, self.width_mm - x_mm, y_mm, self.height_mm - y_mm)
        return max(0.0, distance_mm / 1000.0)
