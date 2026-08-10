from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from sensors import ImuInertialEstimator


def main() -> None:
    estimator = ImuInertialEstimator()
    estimator.reset(2100.0, 2100.0)
    estimator.update(
        accel_x_g=0.0,
        accel_y_g=0.0,
        yaw_deg=0.0,
        timestamp_s=0.0,
        field_width_mm=4500.0,
        field_height_mm=2400.0,
    )
    pose = estimator.update(
        accel_x_g=0.2,
        accel_y_g=0.0,
        yaw_deg=0.0,
        timestamp_s=0.05,
        field_width_mm=4500.0,
        field_height_mm=2400.0,
    )
    if pose.x_mm <= 2100.0:
        raise SystemExit("失敗: IMU加速度でX位置が増えていません")
    if pose.y_mm != 2100.0:
        raise SystemExit("失敗: Y方向が不要に変化しています")
    print("imu inertial estimator test ok")


if __name__ == "__main__":
    main()
