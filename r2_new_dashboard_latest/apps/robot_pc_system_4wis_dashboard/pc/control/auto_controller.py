from __future__ import annotations

from dataclasses import dataclass

from .robot_command import RobotCommand, create_drive_stop, create_drive_velocity


@dataclass(frozen=True)
class AutoDriveDecision:
    command: RobotCommand
    action: str
    reason: str


class AutoController:
    def __init__(
        self,
        forward_speed: int = 100,
        turn_speed: int = 80,
        front_stop_distance_mm: float = 400.0,
        side_preference_margin_mm: float = 100.0,
    ) -> None:
        self.forward_speed = abs(int(forward_speed))
        self.turn_speed = abs(int(turn_speed))
        self.front_stop_distance_mm = float(front_stop_distance_mm)
        self.side_preference_margin_mm = float(side_preference_margin_mm)

    @classmethod
    def from_config(cls, config: dict) -> "AutoController":
        return cls(
            forward_speed=int(config.get("forward_speed", 100)),
            turn_speed=int(config.get("turn_speed", 80)),
            front_stop_distance_mm=float(config.get("front_stop_distance_mm", 400)),
            side_preference_margin_mm=float(config.get("side_preference_margin_mm", 100)),
        )

    def decide(
        self,
        front_distance_mm: float | None,
        left_distance_mm: float | None,
        right_distance_mm: float | None,
        pose: object | None = None,
    ) -> AutoDriveDecision:
        if not self._has_lidar(front_distance_mm, left_distance_mm, right_distance_mm):
            return AutoDriveDecision(create_drive_stop(), "停止", "LiDARデータなし")

        front = float(front_distance_mm)
        left = float(left_distance_mm)
        right = float(right_distance_mm)

        if front >= self.front_stop_distance_mm:
            speed = self.forward_speed
            return AutoDriveDecision(create_drive_velocity(speed, speed), "前進", "前方が空いています")

        side_margin = abs(left - right)
        side_blocked_limit = self.front_stop_distance_mm
        if left < side_blocked_limit and right < side_blocked_limit:
            return AutoDriveDecision(create_drive_stop(), "停止", "左右も狭いため停止します")

        speed = self.turn_speed
        if left >= right + self.side_preference_margin_mm:
            return AutoDriveDecision(create_drive_velocity(-speed, speed), "左旋回", "左側の空きが大きいです")
        if right >= left + self.side_preference_margin_mm:
            return AutoDriveDecision(create_drive_velocity(speed, -speed), "右旋回", "右側の空きが大きいです")
        if side_margin < self.side_preference_margin_mm:
            return AutoDriveDecision(create_drive_velocity(-speed, speed), "左旋回", "左右差が小さいため左旋回します")
        if left > right:
            return AutoDriveDecision(create_drive_velocity(-speed, speed), "左旋回", "左側の空きが大きいです")
        return AutoDriveDecision(create_drive_velocity(speed, -speed), "右旋回", "右側の空きが大きいです")

    @staticmethod
    def _has_lidar(*values: float | None) -> bool:
        for value in values:
            if value is None:
                return False
            try:
                if float(value) <= 0:
                    return False
            except (TypeError, ValueError):
                return False
        return True
