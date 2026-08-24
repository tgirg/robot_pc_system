from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_CATEGORIES = {"DRIVE", "ARM", "TOOL", "SYSTEM"}


@dataclass(frozen=True)
class RobotCommand:
    category: str
    action: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    raw_text: str = ""
    valid: bool = True
    legacy: bool = False


def parse_command(text: str) -> RobotCommand:
    clean = text.strip()
    if not clean:
        return RobotCommand("SYSTEM", "INVALID", raw_text=text, valid=False)

    parts = clean.split()
    upper = [part.upper() for part in parts]

    if upper[0] == "DRIVE":
        if len(upper) >= 2 and upper[1] == "VEL" and len(parts) >= 4:
            try:
                return create_drive_velocity(int(parts[2]), int(parts[3]), raw_text=clean)
            except ValueError:
                return RobotCommand("DRIVE", "VEL", raw_text=clean, valid=False)
        if len(upper) >= 2 and upper[1] == "STOP":
            return create_drive_stop(raw_text=clean)
        return RobotCommand("DRIVE", "INVALID", raw_text=clean, valid=False)

    if upper[0] == "EMERGENCY_STOP":
        return create_emergency_stop(raw_text=clean)

    if upper[0] == "STOP":
        return create_drive_stop(raw_text=clean, legacy=True)

    if upper[0] in {"FWD", "TURN_L", "TURN_R"} and len(parts) >= 2:
        try:
            power = int(parts[1])
        except ValueError:
            return RobotCommand("DRIVE", upper[0], raw_text=clean, valid=False, legacy=True)
        if upper[0] == "FWD":
            return create_drive_velocity(power, power, raw_text=clean, legacy=True)
        if upper[0] == "TURN_L":
            return create_drive_velocity(-power, power, raw_text=clean, legacy=True)
        return create_drive_velocity(power, -power, raw_text=clean, legacy=True)

    category = upper[0]
    if category in VALID_CATEGORIES:
        action = upper[1] if len(upper) > 1 else ""
        return RobotCommand(category, action, tuple(parts[2:]), raw_text=clean)

    return RobotCommand("SYSTEM", "INVALID", raw_text=clean, valid=False)


def format_command(command: RobotCommand) -> str:
    if command.category == "DRIVE" and command.action == "VEL" and len(command.args) >= 2:
        return f"DRIVE VEL {int(command.args[0])} {int(command.args[1])}"
    if command.category == "DRIVE" and command.action == "STOP":
        return "DRIVE STOP"
    if command.category == "SYSTEM" and command.action == "EMERGENCY_STOP":
        return "EMERGENCY_STOP"
    if command.args:
        return " ".join([command.category, command.action, *(str(arg) for arg in command.args)]).strip()
    return " ".join([command.category, command.action]).strip()


def create_drive_velocity(left: int, right: int, raw_text: str = "", legacy: bool = False) -> RobotCommand:
    return RobotCommand("DRIVE", "VEL", (int(left), int(right)), raw_text=raw_text, legacy=legacy)


def create_drive_stop(raw_text: str = "", legacy: bool = False) -> RobotCommand:
    return RobotCommand("DRIVE", "STOP", raw_text=raw_text, legacy=legacy)


def create_emergency_stop(raw_text: str = "") -> RobotCommand:
    return RobotCommand("SYSTEM", "EMERGENCY_STOP", raw_text=raw_text)
