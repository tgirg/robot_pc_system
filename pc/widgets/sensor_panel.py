from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

try:
    from ..mock_sensors import SensorData
    from ..sensors import is_sensor_active, status_label
except ImportError:
    from mock_sensors import SensorData
    from sensors import is_sensor_active, status_label


class SensorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, QLabel] = {}
        layout = QFormLayout(self)
        self.labels = {
            "LiDAR status": "LiDAR状態",
            "LiDAR distance": "LiDAR距離",
            "IMU status": "IMU状態",
            "IMU yaw/pitch/roll": "IMU角度 yaw / pitch / roll",
            "Gyro x/y/z": "ジャイロ x / y / z",
            "Optical odometry dx/dy": "光学式オドメトリ dx / dy",
            "Encoder left/right": "エンコーダ 左 / 右",
            "Distance sensor": "距離センサ",
            "Line color sensor": "ライン/カラー",
            "Current command": "現在の指令",
        }
        for key, text in self.labels.items():
            label = QLabel("-")
            label.setObjectName("metricValue")
            label.setWordWrap(True)
            layout.addRow(text, label)
            self.values[key] = label

    def update_values(
        self,
        data: SensorData,
        current_command: str,
        source: str = "Mock",
        show_values: bool = True,
        label_values: bool = True,
    ) -> None:
        if not show_values:
            self._show_no_data(current_command)
            return

        imu_status = status_label(data.imu_status)
        lidar_status = status_label(data.lidar_status)
        encoder_status = status_label(getattr(data, "encoder_status", "未接続"))
        odom_status = status_label(getattr(data, "odom_status", "未接続"))
        distance_status = status_label(getattr(data, "distance_status", "未接続"))
        line_status = status_label(getattr(data, "line_status", "未接続"))
        color_status = status_label(getattr(data, "color_status", "未接続"))

        lidar_values = self._lidar_values(data) if is_sensor_active(data.lidar_status) else (0.0, 0.0, 0.0, 0.0)
        imu_values = (data.imu_yaw, data.imu_pitch, data.imu_roll) if is_sensor_active(data.imu_status) else (0.0, 0.0, 0.0)
        gyro_values = (data.gyro_x, data.gyro_y, data.gyro_z) if is_sensor_active(data.imu_status) else (0.0, 0.0, 0.0)
        odom_values = (data.odom_dx, data.odom_dy) if is_sensor_active(getattr(data, "odom_status", "未接続")) else (0.0, 0.0)
        encoder_values = (data.encoder_left, data.encoder_right) if is_sensor_active(getattr(data, "encoder_status", "未接続")) else (0, 0)

        self.values["LiDAR status"].setText(self._status_text("LiDAR", lidar_status, data.lidar_source))
        self.values["LiDAR distance"].setText(
            f"前: {lidar_values[0]:.0f} mm / 左: {lidar_values[1]:.0f} mm / "
            f"右: {lidar_values[2]:.0f} mm / 後: {lidar_values[3]:.0f} mm"
        )
        self.values["IMU status"].setText(self._status_text("IMU", imu_status, data.imu_source))
        self.values["IMU yaw/pitch/roll"].setText(f"yaw {imu_values[0]:.1f} / pitch {imu_values[1]:.1f} / roll {imu_values[2]:.1f} deg")
        self.values["Gyro x/y/z"].setText(f"x {gyro_values[0]:.2f} / y {gyro_values[1]:.2f} / z {gyro_values[2]:.2f}")
        self.values["Optical odometry dx/dy"].setText(f"状態: {odom_status} / dx {odom_values[0]:.1f} mm / dy {odom_values[1]:.1f} mm")
        self.values["Encoder left/right"].setText(f"状態: {encoder_status} / 左 {encoder_values[0]} / 右 {encoder_values[1]}")
        self.values["Distance sensor"].setText(f"状態: {distance_status} / 値 {getattr(data, 'distance_sensor_mm', 0.0) if distance_status == 'OK' else 0:.0f} mm")
        self.values["Line color sensor"].setText(
            f"ライン: {line_status} / 値 {getattr(data, 'line_value', 0.0) if line_status == 'OK' else 0:.0f} / "
            f"カラー: {color_status} / {getattr(data, 'color_name', '未接続') if color_status == 'OK' else '未接続'}"
        )
        self.values["Current command"].setText(current_command)

    def _show_no_data(self, current_command: str) -> None:
        zero_rows = {
            "LiDAR status": "LiDAR: 未接続",
            "LiDAR distance": "前: 0 mm / 左: 0 mm / 右: 0 mm / 後: 0 mm",
            "IMU status": "IMU: 未接続",
            "IMU yaw/pitch/roll": "yaw 0.0 / pitch 0.0 / roll 0.0 deg",
            "Gyro x/y/z": "x 0.00 / y 0.00 / z 0.00",
            "Optical odometry dx/dy": "状態: 未接続 / dx 0.0 mm / dy 0.0 mm",
            "Encoder left/right": "状態: 未接続 / 左 0 / 右 0",
            "Distance sensor": "状態: 未接続 / 値 0 mm",
            "Line color sensor": "ライン: 未接続 / 値 0 / カラー: 未接続",
        }
        for key, text in zero_rows.items():
            self.values[key].setText(text)
        self.values["Current command"].setText(current_command)

    @staticmethod
    def _lidar_values(data: SensorData) -> tuple[float, float, float, float]:
        return (
            float(data.lidar_front_mm or 0.0),
            float(data.lidar_left_mm or 0.0),
            float(data.lidar_right_mm or 0.0),
            float(data.lidar_rear_mm or 0.0),
        )

    @staticmethod
    def _status_text(name: str, status: str, source: str) -> str:
        if status == "DUMMY":
            return f"{name}: DUMMY（ダミーテスト受信中・値は0表示）"
        if status == "OK":
            return f"{name}: OK（{source or '実データ'}）"
        if status == "ERROR":
            return f"{name}: ERROR（値は0表示）"
        return f"{name}: 未接続"
