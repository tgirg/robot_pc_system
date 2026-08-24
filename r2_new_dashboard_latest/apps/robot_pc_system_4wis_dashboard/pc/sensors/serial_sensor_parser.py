from __future__ import annotations

from typing import Any

try:
    from .sensor_state import normalize_status, sanitize_number
except ImportError:
    from sensor_state import normalize_status, sanitize_number


def _parse_value_list(text: str, expected: int) -> list[float] | None:
    values = [part.strip() for part in str(text or "").split("/")]
    if len(values) != expected:
        return None
    return [sanitize_number(value, min_value=-100000.0, max_value=100000.0) for value in values]


def _parse_lsb_field(parts: list[str], name: str, expected: int) -> list[float] | None:
    prefix = f"{name.lower()}="
    for part in parts:
        text = part.strip()
        if text.lower().startswith(prefix):
            return _parse_value_list(text[len(prefix):], expected)
    return None


def _parse_lsb_line(parts: list[str]) -> dict[str, Any] | None:
    if len(parts) < 2:
        return None
    subtype = parts[1].upper()
    if subtype == "PONG":
        return {
            "type": "LSB_PONG",
            "uptime_ms": int(sanitize_number(parts[2], min_value=0.0)) if len(parts) >= 3 else 0,
        }
    if subtype == "ID" and len(parts) >= 3:
        return {
            "type": "LSB_ID",
            "board": parts[2],
            "version": parts[3] if len(parts) >= 4 else "",
        }
    if subtype == "STATUS" and len(parts) >= 3:
        return {
            "type": "LSB_STATUS",
            "name": parts[2],
            "status": normalize_status(parts[3]) if len(parts) >= 4 else "OK",
        }
    if subtype == "ERR" and len(parts) >= 3:
        return {
            "type": "LSB_ERR",
            "code": parts[2],
            "detail": ",".join(parts[3:]) if len(parts) >= 4 else "",
        }
    if subtype == "I2C" and len(parts) >= 3:
        return {
            "type": "LSB_I2C",
            "items": parts[2:],
        }
    if subtype == "RATE" and len(parts) >= 3:
        return {
            "type": "LSB_RATE",
            "interval_ms": int(sanitize_number(parts[2], min_value=0.0, max_value=100000.0)),
        }
    if subtype == "TOF" and len(parts) >= 4:
        values: dict[str, str] = {}
        for part in parts[4:]:
            if "=" in part:
                key, value = part.split("=", 1)
                values[key.strip().lower()] = value.strip()
        return {
            "type": "LSB_TOF",
            "address": parts[2],
            "status": parts[3],
            "tof_type": values.get("type", ""),
            "ready": values.get("ready", ""),
            "distance_mm": int(sanitize_number(values.get("dist_mm", 0), min_value=0.0, max_value=10000.0)),
            "raw": values,
        }
    if subtype == "SENS" and len(parts) >= 3:
        tof = _parse_lsb_field(parts[3:], "tof", 4)
        ultrasonic = _parse_lsb_field(parts[3:], "us", 8)
        imu = _parse_lsb_field(parts[3:], "imu", 3)
        return {
            "type": "LSB_SENS",
            "seq": int(sanitize_number(parts[2], min_value=0.0)),
            "tof": tof or [0.0, 0.0, 0.0, 0.0],
            "ultrasonic": ultrasonic or [0.0] * 8,
            "imu": imu,
        }
    return None


def parse_serial_sensor_line(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None

    parts = [part.strip() for part in text.split(",")]
    kind = parts[0].upper()
    gpio_diag_names = {
        "GPIO13_DIAG": ("FL", "GPIO13"),
        "GPIO14_DIAG": ("FR", "GPIO14"),
        "GPIO27_DIAG": ("RR", "GPIO27"),
        "GPIO26_DIAG": ("BR", "GPIO26"),
        "GPIO25_DIAG": ("BL", "GPIO25"),
        "GPIO33_DIAG": ("LB", "GPIO33"),
        "GPIO32_DIAG": ("LF", "GPIO32"),
        "GPIO35_DIAG": ("US1", "GPIO35"),
        "GPIO23_DIAG": ("US2", "GPIO23"),
    }

    try:
        if kind in gpio_diag_names and len(parts) >= 3:
            values = {
                parts[index].upper(): parts[index + 1]
                for index in range(1, len(parts) - 1, 2)
            }
            name, gpio = gpio_diag_names[kind]
            if "GROVE_ULTRASONIC_MM" in values:
                return {
                    "type": "CUSTOM_SENSOR",
                    "name": name,
                    "gpio": gpio,
                    "metric": "GROVE_ULTRASONIC_MM",
                    "value": int(sanitize_number(values["GROVE_ULTRASONIC_MM"], min_value=0.0, max_value=100000.0)),
                }
            return {
                "type": "CUSTOM_SENSOR",
                "name": name,
                "gpio": gpio,
                "metric": "RAW",
                "value": int(sanitize_number(values.get("RAW", 0), min_value=0.0, max_value=100000.0)),
            }
        if kind == "LSB":
            return _parse_lsb_line(parts)
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
        if kind == "SENSOR" and len(parts) >= 5:
            metric = parts[3].upper()
            return {
                "type": "CUSTOM_SENSOR",
                "name": parts[1].upper(),
                "gpio": parts[2].upper(),
                "metric": metric,
                "value": int(sanitize_number(parts[4], min_value=0.0, max_value=100000.0)),
            }
        if kind == "ULTRASONIC" and len(parts) >= 5:
            return {
                "type": "CUSTOM_ULTRASONIC",
                "name": parts[1].upper(),
                "gpio": parts[2].upper(),
                "metric": parts[3].upper(),
                "value": int(sanitize_number(parts[4], min_value=0.0, max_value=100000.0)),
            }
        if kind.endswith("_RAW") and len(parts) >= 2:
            return {
                "type": "CUSTOM_SENSOR",
                "name": kind[:-4].upper(),
                "gpio": "",
                "metric": "RAW",
                "value": int(sanitize_number(parts[1], min_value=0.0, max_value=100000.0)),
            }
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
