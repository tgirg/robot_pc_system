from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from mock_sensors import MockSensors  # noqa: E402


def main() -> None:
    sensors = MockSensors()
    last = time.monotonic()
    print("Mockセンサ値を表示します。終了するには Ctrl+C を押してください。")
    try:
        while True:
            now = time.monotonic()
            data = sensors.read(max(0.001, now - last), source="Mock", connected=False)
            last = now
            print(
                "Mock | "
                f"LiDAR={data.lidar_distance:.2f} m | "
                f"IMU={data.imu_yaw:.1f}/{data.imu_pitch:.1f}/{data.imu_roll:.1f} deg | "
                f"Odometry={data.odom_dx:.3f}/{data.odom_dy:.3f} m | "
                f"Encoder={data.encoder_left}/{data.encoder_right} | "
                f"Pose=({data.pose_x:.2f}, {data.pose_y:.2f}, {data.pose_theta:.1f} deg)"
            )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n終了しました。")


if __name__ == "__main__":
    main()
