from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectObstacle:
    id: str
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    label: str = ""

    @classmethod
    def from_config(cls, config: dict) -> "RectObstacle":
        obstacle_id = str(config.get("id", "obstacle"))
        return cls(
            id=obstacle_id,
            label=str(config.get("label", obstacle_id)),
            x_mm=float(config.get("x_mm", 0)),
            y_mm=float(config.get("y_mm", 0)),
            width_mm=float(config.get("width_mm", 100)),
            height_mm=float(config.get("height_mm", 100)),
        )

    @property
    def left(self) -> float:
        return self.x_mm - self.width_mm / 2.0

    @property
    def right(self) -> float:
        return self.x_mm + self.width_mm / 2.0

    @property
    def bottom(self) -> float:
        return self.y_mm - self.height_mm / 2.0

    @property
    def top(self) -> float:
        return self.y_mm + self.height_mm / 2.0

    def contains(self, x_mm: float, y_mm: float, margin_mm: float = 0.0) -> bool:
        return (
            self.left - margin_mm <= x_mm <= self.right + margin_mm
            and self.bottom - margin_mm <= y_mm <= self.top + margin_mm
        )
