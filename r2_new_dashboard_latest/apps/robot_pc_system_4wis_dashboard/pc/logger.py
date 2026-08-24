from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

try:
    from .config_loader import PROJECT_ROOT
    from .mock_sensors import SensorData
    from .serial_comm import SerialStatus
    from .sensor_fusion import Pose
except ImportError:
    from config_loader import PROJECT_ROOT
    from mock_sensors import SensorData
    from serial_comm import SerialStatus
    from sensor_fusion import Pose


CSV_FIELDS = [
    "timestamp",
    "x",
    "y",
    "theta",
    "lidar_distance",
    "imu_yaw",
    "imu_pitch",
    "imu_roll",
    "odom_dx",
    "odom_dy",
    "encoder_left",
    "encoder_right",
    "current_command",
    "esp32_status",
]


class CsvLogger:
    def __init__(self, directory: str = "logs") -> None:
        self.directory = PROJECT_ROOT / directory
        self.file = None
        self.writer: csv.DictWriter | None = None
        self.path: Path | None = None

    @property
    def active(self) -> bool:
        return self.writer is not None

    def start(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.directory / f"r2_dashboard_{timestamp}.csv"
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=CSV_FIELDS)
        self.writer.writeheader()
        return self.path

    def stop(self) -> None:
        if self.file is not None:
            self.file.close()
        self.file = None
        self.writer = None

    def write(self, pose: Pose, data: SensorData, current_command: str, esp32_status: SerialStatus) -> None:
        if self.writer is None:
            return
        self.writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "x": f"{pose.x:.4f}",
                "y": f"{pose.y:.4f}",
                "theta": f"{pose.theta:.2f}",
                "lidar_distance": f"{data.lidar_distance:.3f}",
                "imu_yaw": f"{data.imu_yaw:.2f}",
                "imu_pitch": f"{data.imu_pitch:.2f}",
                "imu_roll": f"{data.imu_roll:.2f}",
                "odom_dx": f"{data.odom_dx:.4f}",
                "odom_dy": f"{data.odom_dy:.4f}",
                "encoder_left": data.encoder_left,
                "encoder_right": data.encoder_right,
                "current_command": current_command,
                "esp32_status": "MOCK" if esp32_status.mock else ("OK" if esp32_status.connected else "NG"),
            }
        )
        if self.file is not None:
            self.file.flush()
