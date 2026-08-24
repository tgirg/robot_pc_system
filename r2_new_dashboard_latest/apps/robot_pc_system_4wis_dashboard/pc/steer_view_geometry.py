from __future__ import annotations

import math


def robot_angle_to_screen_vector(angle_deg: float) -> tuple[float, float]:
    heading = math.radians(angle_deg)
    return -math.sin(heading), -math.cos(heading)


def robot_angle_to_qt_rotation(angle_deg: float) -> float:
    return -angle_deg
