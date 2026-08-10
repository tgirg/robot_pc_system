from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .sensor_state import NO_DATA, normalize_status, sanitize_number


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "optical_odometry.yaml"


@dataclass
class OpticalOdometryConfig:
    enabled: bool = True
    i2c_address: str = "0x17"
    scale_x_mm_per_count: float = 0.30517578125
    scale_y_mm_per_count: float = 0.30517578125
    invert_x: bool = False
    invert_y: bool = False
    swap_xy: bool = False
    deadband_counts: float = 0.0
    max_delta_counts: float = 500.0
    stale_timeout_ms: int = 1000
    coordinate_mode: str = "robot_relative"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "OpticalOdometryConfig":
        yaml_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        if not yaml_path.exists():
            return cls()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            i2c_address=str(data.get("i2c_address", "0x17")),
            scale_x_mm_per_count=float(data.get("scale_x_mm_per_count", 0.30517578125)),
            scale_y_mm_per_count=float(data.get("scale_y_mm_per_count", 0.30517578125)),
            invert_x=bool(data.get("invert_x", False)),
            invert_y=bool(data.get("invert_y", False)),
            swap_xy=bool(data.get("swap_xy", False)),
            deadband_counts=float(data.get("deadband_counts", 0.0)),
            max_delta_counts=float(data.get("max_delta_counts", 500.0)),
            stale_timeout_ms=int(data.get("stale_timeout_ms", 1000)),
            coordinate_mode=str(data.get("coordinate_mode", "robot_relative")),
        )

    def save(self, path: str | Path | None = None) -> None:
        yaml_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "enabled": self.enabled,
            "i2c_address": self.i2c_address,
            "scale_x_mm_per_count": float(self.scale_x_mm_per_count),
            "scale_y_mm_per_count": float(self.scale_y_mm_per_count),
            "invert_x": self.invert_x,
            "invert_y": self.invert_y,
            "swap_xy": self.swap_xy,
            "deadband_counts": float(self.deadband_counts),
            "max_delta_counts": float(self.max_delta_counts),
            "stale_timeout_ms": int(self.stale_timeout_ms),
            "coordinate_mode": self.coordinate_mode,
            "source_note": "SparkFun Qwiic Optical Tracking Odometry Sensor / PAA5160E1 register 0x20 position count. 10000 mm / 32768 count.",
        }
        yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@dataclass
class OpticalOdometryState:
    config: OpticalOdometryConfig
    status: str = NO_DATA
    raw_dx: float = 0.0
    raw_dy: float = 0.0
    delta_x_mm: float = 0.0
    delta_y_mm: float = 0.0
    total_x_count: float = 0.0
    total_y_count: float = 0.0
    total_x_mm: float = 0.0
    total_y_mm: float = 0.0
    last_received_time: float = 0.0
    source: str = "NONE"
    last_applied_time: float = 0.0
    apply_enabled: bool = True
    last_reject_reason: str = "未受信"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "OpticalOdometryState":
        return cls(config=OpticalOdometryConfig.load(path))

    def update_status(self, status: object, source: str = "REAL") -> None:
        self.status = normalize_status(status)
        self.source = source
        self.last_received_time = time.monotonic()
        if self.status != "OK":
            self.raw_dx = 0.0
            self.raw_dy = 0.0
            self.delta_x_mm = 0.0
            self.delta_y_mm = 0.0

    def update_delta(self, raw_dx: object, raw_dy: object, source: str = "REAL") -> tuple[float, float] | None:
        self.source = source
        self.last_received_time = time.monotonic()
        self.raw_dx = sanitize_number(raw_dx)
        self.raw_dy = sanitize_number(raw_dy)
        if not self.can_apply():
            self.delta_x_mm = 0.0
            self.delta_y_mm = 0.0
            return None

        dx = self.raw_dx
        dy = self.raw_dy
        if self.config.swap_xy:
            dx, dy = dy, dx
        if self.config.invert_x:
            dx = -dx
        if self.config.invert_y:
            dy = -dy

        if abs(dx) <= self.config.deadband_counts:
            dx = 0.0
        if abs(dy) <= self.config.deadband_counts:
            dy = 0.0
        if abs(dx) > self.config.max_delta_counts or abs(dy) > self.config.max_delta_counts:
            self.last_reject_reason = "異常に大きい差分"
            self.delta_x_mm = 0.0
            self.delta_y_mm = 0.0
            return None

        self.total_x_count += dx
        self.total_y_count += dy
        self.delta_x_mm = dx * self.config.scale_x_mm_per_count
        self.delta_y_mm = dy * self.config.scale_y_mm_per_count
        self.total_x_mm += self.delta_x_mm
        self.total_y_mm += self.delta_y_mm
        self.last_reject_reason = ""
        return self.delta_x_mm, self.delta_y_mm

    def transform_robot_delta_to_field(self, dx_mm: float, dy_mm: float, theta_deg: float) -> tuple[float, float]:
        if self.config.coordinate_mode == "field_relative":
            return dx_mm, dy_mm
        theta_rad = math.radians(theta_deg)
        field_dx = dx_mm * math.cos(theta_rad) - dy_mm * math.sin(theta_rad)
        field_dy = dx_mm * math.sin(theta_rad) + dy_mm * math.cos(theta_rad)
        return field_dx, field_dy

    def can_apply(self) -> bool:
        if not self.config.enabled:
            self.last_reject_reason = "無効"
            return False
        if not self.apply_enabled:
            self.last_reject_reason = "反映停止中"
            return False
        if self.status != "OK":
            self.last_reject_reason = "OK以外"
            return False
        if self.source != "REAL":
            self.last_reject_reason = "実データ以外"
            return False
        if self.is_stale():
            self.last_reject_reason = "未受信"
            return False
        return True

    def is_stale(self) -> bool:
        if self.last_received_time <= 0:
            return True
        timeout_s = max(0.001, self.config.stale_timeout_ms / 1000.0)
        return (time.monotonic() - self.last_received_time) > timeout_s

    def zero(self) -> None:
        self.raw_dx = 0.0
        self.raw_dy = 0.0
        self.delta_x_mm = 0.0
        self.delta_y_mm = 0.0
        self.total_x_count = 0.0
        self.total_y_count = 0.0
        self.total_x_mm = 0.0
        self.total_y_mm = 0.0
        self.last_applied_time = 0.0

    def summary(self) -> dict[str, Any]:
        active = self.can_apply()
        return {
            "status": self.status if not self.is_stale() else NO_DATA,
            "source": self.source,
            "raw_dx": self.raw_dx if active else 0.0,
            "raw_dy": self.raw_dy if active else 0.0,
            "delta_x_mm": self.delta_x_mm if active else 0.0,
            "delta_y_mm": self.delta_y_mm if active else 0.0,
            "total_x_count": self.total_x_count,
            "total_y_count": self.total_y_count,
            "total_x_mm": self.total_x_mm,
            "total_y_mm": self.total_y_mm,
            "apply_enabled": self.apply_enabled,
            "applying": active,
            "last_received_time": self.last_received_time,
            "last_reject_reason": "" if active else self.last_reject_reason,
            "coordinate_mode": self.config.coordinate_mode,
        }
