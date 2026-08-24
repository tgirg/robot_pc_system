from __future__ import annotations

from dataclasses import dataclass

try:
    from .mock_sensors import SensorData
except ImportError:
    from mock_sensors import SensorData


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


class SensorFusion:
    def __init__(self) -> None:
        self.pose = Pose()

    def update(self, data: SensorData) -> Pose:
        # Ver.1 keeps the fusion layer simple and replaceable.
        self.pose.x = data.pose_x
        self.pose.y = data.pose_y
        self.pose.theta = data.pose_theta
        return self.pose
