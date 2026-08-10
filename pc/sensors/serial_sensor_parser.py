from __future__ import annotations

from typing import Any

try:
    from .sensor_state import normalize_status, sanitize_number
except ImportError:
    from sensor_state import normalize_status, sanitize_number


def parse_serial_sensor_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None

    parts = [part.strip() for part in text.split(",")]
    kind = parts[0].upper()

    try:
        if kind == "IMU" and len(parts) >= 4:
            return {
                "type": "IMU",
                "yaw": sanitize_number(parts[1]),
                "pitch": sanitize_number(parts[2]),
                "roll": sanitize_number(parts[3]),
            }
        if kind == "GYRO" and len(parts) >= 4:
            return {
                "type": "GYRO",
                "x": sanitize_number(parts[1]),
                "y": sanitize_number(parts[2]),
                "z": sanitize_number(parts[3]),
            }
        if kind in {"ACC", "ACCEL"} and len(parts) >= 4:
            return {
                "type": "ACCEL",
                "x_g": sanitize_number(parts[1]),
                "y_g": sanitize_number(parts[2]),
                "z_g": sanitize_number(parts[3]),
            }
        if kind == "STATUS" and len(parts) >= 2:
            return {"type": "STATUS", "status": parts[1]}
        if kind == "FW" and len(parts) >= 3:
            return {"type": "FW", "name": parts[1], "version": parts[2]}
        if kind == "IMU_STATUS" and len(parts) >= 2:
            return {"type": "IMU_STATUS", "status": normalize_status(parts[1])}
        if kind == "IMU_TYPE" and len(parts) >= 2:
            return {"type": "IMU_TYPE", "name": parts[1]}
        if kind == "IMU_ADDR" and len(parts) >= 2:
            return {"type": "IMU_ADDR", "address": parts[1]}
        if kind == "LIDAR_STATUS" and len(parts) >= 2:
            return {"type": "LIDAR_STATUS", "status": normalize_status(parts[1])}
        if kind in {"ENC_STATUS", "ODOM_STATUS", "OPTICAL_STATUS", "DIST_STATUS", "LINE_STATUS", "COLOR_STATUS"} and len(parts) >= 2:
            return {"type": kind, "status": normalize_status(parts[1])}
        if kind == "LIDAR" and len(parts) >= 5:
            return {
                "type": "LIDAR",
                "front_mm": int(sanitize_number(parts[1], min_value=0.0, max_value=10000.0)),
                "left_mm": int(sanitize_number(parts[2], min_value=0.0, max_value=10000.0)),
                "right_mm": int(sanitize_number(parts[3], min_value=0.0, max_value=10000.0)),
                "rear_mm": int(sanitize_number(parts[4], min_value=0.0, max_value=10000.0)),
            }
        if kind == "ENC" and len(parts) >= 3:
            return {"type": "ENC", "left": int(sanitize_number(parts[1])), "right": int(sanitize_number(parts[2]))}
        if kind == "ODOM" and len(parts) >= 4:
            return {
                "type": "ODOM",
                "x": sanitize_number(parts[1]),
                "y": sanitize_number(parts[2]),
                "theta": sanitize_number(parts[3]),
            }
        if kind == "OPTICAL" and len(parts) >= 3:
            return {"type": "OPTICAL", "dx": sanitize_number(parts[1]), "dy": sanitize_number(parts[2])}
        if kind == "DIST" and len(parts) >= 3:
            return {"type": "DIST", "direction": parts[1].lower(), "value": int(sanitize_number(parts[2], min_value=0.0, max_value=10000.0))}
        if kind == "LINE" and len(parts) >= 3:
            return {"type": "LINE", "name": parts[1].lower(), "value": sanitize_number(parts[2], min_value=0.0, max_value=1000.0)}
        if kind == "COLOR" and len(parts) >= 2:
            return {"type": "COLOR", "name": parts[1]}
        if kind == "DRIVE" and len(parts) >= 3:
            return {"type": "DRIVE", "left": int(float(parts[1])), "right": int(float(parts[2]))}
    except ValueError:
        return None

    return None
