from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimulationState:
    running: bool = False
    last_command: str = "DRIVE STOP"
    pose_source: str = "シミュレーション"
    boundary_status: str = ""
    obstacle_status: str = ""
    left_speed: int = 0
    right_speed: int = 0
    x_mm: float = 0.0
    y_mm: float = 0.0
    theta_deg: float = 0.0
    left_encoder: int = 0
    right_encoder: int = 0
    lidar_front_mm: float = 0.0
    lidar_left_mm: float = 0.0
    lidar_right_mm: float = 0.0
    lidar_rear_mm: float = 0.0
