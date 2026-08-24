from __future__ import annotations

import math
from typing import Any


NO_DATA = "未接続"
VALID_STATUSES = {"OK", "DUMMY", "ERROR", NO_DATA}


def normalize_status(status: Any) -> str:
    text = str(status or "").strip().upper()
    if text in {"OK", "DUMMY", "ERROR"}:
        return text
    if text in {"NO_DATA", "NONE", "UNCONNECTED", "DISCONNECTED", "未接続", "未受信", ""}:
        return NO_DATA
    return NO_DATA


def is_sensor_active(status: Any) -> bool:
    return normalize_status(status) == "OK"


def is_sensor_dummy(status: Any) -> bool:
    return normalize_status(status) == "DUMMY"


def status_label(status: Any) -> str:
    normalized = normalize_status(status)
    if normalized == "OK":
        return "OK"
    if normalized == "DUMMY":
        return "DUMMY"
    if normalized == "ERROR":
        return "ERROR"
    return "未接続"


def sanitize_number(value: Any, default: float = 0.0, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(number) or math.isinf(number):
        return float(default)
    if min_value is not None and number < min_value:
        return float(default)
    if max_value is not None and number > max_value:
        return float(default)
    return number


def sanitize_distance(value: Any, status: Any, default: float = 0.0, max_mm: float = 10000.0) -> float:
    if not is_sensor_active(status):
        return float(default)
    return sanitize_number(value, default=default, min_value=0.0, max_value=max_mm)


def sanitize_angle(value: Any, status: Any, default: float = 0.0) -> float:
    if not is_sensor_active(status):
        return float(default)
    return sanitize_number(value, default=default)


def sanitize_count(value: Any, status: Any, default: int = 0) -> int:
    if not is_sensor_active(status):
        return int(default)
    return int(round(sanitize_number(value, default=default)))


def source_label_for_status(status: Any, ok_label: str, dummy_label: str) -> str:
    normalized = normalize_status(status)
    if normalized == "OK":
        return ok_label
    if normalized == "DUMMY":
        return dummy_label
    if normalized == "ERROR":
        return "エラー"
    return "未接続"
