from __future__ import annotations

import time
from dataclasses import dataclass

from .robot_command import RobotCommand, create_drive_stop, create_drive_velocity, format_command


@dataclass(frozen=True)
class SafetyResult:
    command: RobotCommand
    allowed: bool
    message: str = ""
    changed: bool = False


class SafetyLayer:
    def __init__(self, max_drive_speed: int = 255, command_timeout_ms: int = 500) -> None:
        self.max_drive_speed = abs(int(max_drive_speed))
        self.command_timeout_ms = int(command_timeout_ms)
        self.emergency_stop_active = False
        self.last_command_time = time.monotonic()

    def filter_command(self, command: RobotCommand) -> SafetyResult:
        if not command.valid:
            stop = create_drive_stop(raw_text=command.raw_text)
            return SafetyResult(stop, True, "不正な指令のため停止指令に変換しました", True)

        if command.category == "SYSTEM" and command.action == "EMERGENCY_STOP":
            self.emergency_stop_active = True
            self.last_command_time = time.monotonic()
            return SafetyResult(command, True, "緊急停止を実行します")

        if self.emergency_stop_active and command.category == "DRIVE" and command.action != "STOP":
            return SafetyResult(command, False, "緊急停止中のため指令を送信しません")

        if command.category == "DRIVE" and command.action == "STOP":
            self.emergency_stop_active = False
            self.last_command_time = time.monotonic()
            return SafetyResult(command, True, "")

        if command.category == "DRIVE" and command.action == "VEL":
            left, right = int(command.args[0]), int(command.args[1])
            clamped_left = self._clamp(left)
            clamped_right = self._clamp(right)
            self.last_command_time = time.monotonic()
            if (left, right) != (clamped_left, clamped_right):
                return SafetyResult(
                    create_drive_velocity(clamped_left, clamped_right, raw_text=format_command(command)),
                    True,
                    "速度上限を超えたため制限しました",
                    True,
                )
            return SafetyResult(command, True, "")

        self.last_command_time = time.monotonic()
        return SafetyResult(command, True, "")

    def stale_command_stop_needed(self) -> bool:
        elapsed_ms = (time.monotonic() - self.last_command_time) * 1000.0
        return elapsed_ms > self.command_timeout_ms

    def clear_emergency_stop(self) -> None:
        self.emergency_stop_active = False

    def _clamp(self, value: int) -> int:
        return max(-self.max_drive_speed, min(self.max_drive_speed, int(value)))
