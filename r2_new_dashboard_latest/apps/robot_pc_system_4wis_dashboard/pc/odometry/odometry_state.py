from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OdometryState:
    source: str = "データなし"
    x_mm: float = 0.0
    y_mm: float = 0.0
    theta_deg: float = 0.0
    total_distance_mm: float = 0.0
    start_x_mm: float = 0.0
    start_y_mm: float = 0.0
    last_x_mm: float = 0.0
    last_y_mm: float = 0.0
    updated_at: float = 0.0
    has_data: bool = False
    warning: str = ""
