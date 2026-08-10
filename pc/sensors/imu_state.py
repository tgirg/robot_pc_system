from __future__ import annotations

import time
from dataclasses import dataclass

try:
    from ..mock_sensors import SensorData
except ImportError:
    from mock_sensors import SensorData

try:
    from .sensor_state import (
        NO_DATA,
        is_sensor_active,
        normalize_status,
        sanitize_angle,
        sanitize_count,
        sanitize_distance,
        sanitize_number,
        source_label_for_status,
    )
except ImportError:
    from sensor_state import (
        NO_DATA,
        is_sensor_active,
        normalize_status,
        sanitize_angle,
        sanitize_count,
        sanitize_distance,
        sanitize_number,
        source_label_for_status,
    )


@dataclass
class ImuState:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    accel_x_g: float = 0.0
    accel_y_g: float = 0.0
    accel_z_g: float = 0.0
    encoder_left: int = 0
    encoder_right: int = 0
    odom_dx: float = 0.0
    odom_dy: float = 0.0
    odom_theta: float = 0.0
    distance_sensor_mm: int = 0
    line_value: float = 0.0
    color_name: str = "未接続"
    status: str = ""
    imu_status: str = NO_DATA
    lidar_status: str = NO_DATA
    encoder_status: str = NO_DATA
    odom_status: str = NO_DATA
    distance_status: str = NO_DATA
    line_status: str = NO_DATA
    color_status: str = NO_DATA
    imu_source: str = "未接続"
    lidar_source: str = "未接続"
    front_distance_mm: int = 0
    left_distance_mm: int = 0
    right_distance_mm: int = 0
    rear_distance_mm: int = 0
    source: str = "Real"
    connected: bool = False
    last_update_time: float = 0.0
    last_imu_update_time: float = 0.0
    last_lidar_update_time: float = 0.0
    last_encoder_update_time: float = 0.0
    last_odom_update_time: float = 0.0
    last_distance_update_time: float = 0.0
    last_line_update_time: float = 0.0
    last_color_update_time: float = 0.0

    def update_from_message(self, message: dict) -> None:
        message_type = message.get("type")
        now = time.monotonic()

        if message_type == "IMU":
            if self.imu_status == NO_DATA:
                self._set_imu_status("OK", now)
            self.yaw = sanitize_angle(message.get("yaw"), self.imu_status)
            self.pitch = sanitize_angle(message.get("pitch"), self.imu_status)
            self.roll = sanitize_angle(message.get("roll"), self.imu_status)
            self._touch(now)
            self.last_imu_update_time = now
        elif message_type == "GYRO":
            if self.imu_status == NO_DATA:
                self._set_imu_status("OK", now)
            self.gyro_x = sanitize_angle(message.get("x"), self.imu_status)
            self.gyro_y = sanitize_angle(message.get("y"), self.imu_status)
            self.gyro_z = sanitize_angle(message.get("z"), self.imu_status)
            self._touch(now)
            self.last_imu_update_time = now
        elif message_type == "ACCEL":
            if self.imu_status == NO_DATA:
                self._set_imu_status("OK", now)
            if is_sensor_active(self.imu_status):
                self.accel_x_g = sanitize_number(message.get("x_g"), min_value=-16.0, max_value=16.0)
                self.accel_y_g = sanitize_number(message.get("y_g"), min_value=-16.0, max_value=16.0)
                self.accel_z_g = sanitize_number(message.get("z_g"), min_value=-16.0, max_value=16.0)
            else:
                self.accel_x_g = 0.0
                self.accel_y_g = 0.0
                self.accel_z_g = 0.0
            self._touch(now)
            self.last_imu_update_time = now
        elif message_type == "ENC":
            if self.encoder_status == NO_DATA:
                self.encoder_status = "OK"
            self.encoder_left = sanitize_count(message.get("left"), self.encoder_status)
            self.encoder_right = sanitize_count(message.get("right"), self.encoder_status)
            self._touch(now)
            self.last_encoder_update_time = now
        elif message_type == "ODOM":
            if self.odom_status == NO_DATA:
                self.odom_status = "OK"
            self.odom_dx = sanitize_number(message.get("x")) if is_sensor_active(self.odom_status) else 0.0
            self.odom_dy = sanitize_number(message.get("y")) if is_sensor_active(self.odom_status) else 0.0
            self.odom_theta = sanitize_angle(message.get("theta"), self.odom_status)
            self._touch(now)
            self.last_odom_update_time = now
        elif message_type == "OPTICAL":
            if self.odom_status == NO_DATA:
                self.odom_status = "OK"
            self.odom_dx = sanitize_number(message.get("dx")) if is_sensor_active(self.odom_status) else 0.0
            self.odom_dy = sanitize_number(message.get("dy")) if is_sensor_active(self.odom_status) else 0.0
            self._touch(now)
            self.last_odom_update_time = now
        elif message_type == "DIST":
            if self.distance_status == NO_DATA:
                self.distance_status = "OK"
            self.distance_sensor_mm = int(sanitize_distance(message.get("value"), self.distance_status))
            self._touch(now)
            self.last_distance_update_time = now
        elif message_type == "LINE":
            if self.line_status == NO_DATA:
                self.line_status = "OK"
            self.line_value = sanitize_number(message.get("value"), min_value=0.0, max_value=1000.0) if is_sensor_active(self.line_status) else 0.0
            self._touch(now)
            self.last_line_update_time = now
        elif message_type == "COLOR":
            if self.color_status == NO_DATA:
                self.color_status = "OK"
            self.color_name = str(message.get("name", "unknown")) if is_sensor_active(self.color_status) else "未接続"
            self._touch(now)
        elif message_type == "STATUS":
            self.status = str(message.get("status", ""))
            self._touch(now)
        elif message_type == "IMU_STATUS":
            self._set_imu_status(message.get("status"), now)
        elif message_type == "LIDAR_STATUS":
            self._set_lidar_status(message.get("status"), now)
        elif message_type == "ENC_STATUS":
            self.encoder_status = normalize_status(message.get("status"))
            if not is_sensor_active(self.encoder_status):
                self.encoder_left = 0
                self.encoder_right = 0
            self._touch(now)
            self.last_encoder_update_time = now
        elif message_type in {"ODOM_STATUS", "OPTICAL_STATUS"}:
            self.odom_status = normalize_status(message.get("status"))
            if not is_sensor_active(self.odom_status):
                self.odom_dx = 0.0
                self.odom_dy = 0.0
                self.odom_theta = 0.0
            self._touch(now)
            self.last_odom_update_time = now
        elif message_type == "DIST_STATUS":
            self.distance_status = normalize_status(message.get("status"))
            if not is_sensor_active(self.distance_status):
                self.distance_sensor_mm = 0
            self._touch(now)
            self.last_distance_update_time = now
        elif message_type == "LINE_STATUS":
            self.line_status = normalize_status(message.get("status"))
            if not is_sensor_active(self.line_status):
                self.line_value = 0.0
            self._touch(now)
            self.last_line_update_time = now
        elif message_type == "COLOR_STATUS":
            self.color_status = normalize_status(message.get("status"))
            if not is_sensor_active(self.color_status):
                self.color_name = "未接続"
            self._touch(now)
        elif message_type == "LIDAR":
            if is_sensor_active(self.lidar_status):
                self.front_distance_mm = int(sanitize_distance(message.get("front_mm"), self.lidar_status))
                self.left_distance_mm = int(sanitize_distance(message.get("left_mm"), self.lidar_status))
                self.right_distance_mm = int(sanitize_distance(message.get("right_mm"), self.lidar_status))
                self.rear_distance_mm = int(sanitize_distance(message.get("rear_mm"), self.lidar_status))
            else:
                self._clear_lidar_values()
            self._touch(now)
            self.last_lidar_update_time = now

    def has_recent_data(self, timeout_s: float = 2.0) -> bool:
        return self.connected and (time.monotonic() - self.last_update_time) <= timeout_s

    def has_recent_lidar(self, timeout_s: float = 2.0) -> bool:
        return is_sensor_active(self.lidar_status) and self.last_lidar_update_time > 0 and (time.monotonic() - self.last_lidar_update_time) <= timeout_s

    def to_sensor_data(self) -> SensorData:
        recent_data = self.has_recent_data()
        imu_status = self.imu_status if recent_data else NO_DATA
        encoder_status = self.encoder_status if recent_data else NO_DATA
        odom_status = self.odom_status if recent_data else NO_DATA
        distance_status = self.distance_status if recent_data else NO_DATA
        line_status = self.line_status if recent_data else NO_DATA
        color_status = self.color_status if recent_data else NO_DATA
        if not recent_data:
            lidar_status = NO_DATA
        elif is_sensor_active(self.lidar_status):
            lidar_status = self.lidar_status if self.has_recent_lidar() else NO_DATA
        else:
            lidar_status = self.lidar_status

        return SensorData(
            lidar_distance=float(self.front_distance_mm) / 1000.0 if is_sensor_active(lidar_status) else 0.0,
            imu_yaw=sanitize_angle(self.yaw, imu_status),
            imu_pitch=sanitize_angle(self.pitch, imu_status),
            imu_roll=sanitize_angle(self.roll, imu_status),
            odom_dx=self.odom_dx if is_sensor_active(odom_status) else 0.0,
            odom_dy=self.odom_dy if is_sensor_active(odom_status) else 0.0,
            encoder_left=sanitize_count(self.encoder_left, encoder_status),
            encoder_right=sanitize_count(self.encoder_right, encoder_status),
            pose_x=0.0,
            pose_y=0.0,
            pose_theta=sanitize_angle(self.yaw, imu_status) if is_sensor_active(imu_status) else sanitize_angle(self.odom_theta, odom_status),
            source=self.source,
            connected=recent_data,
            lidar_front_mm=sanitize_distance(self.front_distance_mm, lidar_status),
            lidar_left_mm=sanitize_distance(self.left_distance_mm, lidar_status),
            lidar_right_mm=sanitize_distance(self.right_distance_mm, lidar_status),
            lidar_rear_mm=sanitize_distance(self.rear_distance_mm, lidar_status),
            gyro_x=sanitize_angle(self.gyro_x, imu_status),
            gyro_y=sanitize_angle(self.gyro_y, imu_status),
            gyro_z=sanitize_angle(self.gyro_z, imu_status),
            accel_x_g=self.accel_x_g if is_sensor_active(imu_status) else 0.0,
            accel_y_g=self.accel_y_g if is_sensor_active(imu_status) else 0.0,
            accel_z_g=self.accel_z_g if is_sensor_active(imu_status) else 0.0,
            imu_status=imu_status,
            imu_source=source_label_for_status(imu_status, "実IMU", "ESP32ダミー出力"),
            lidar_status=lidar_status,
            lidar_source=source_label_for_status(lidar_status, "実データ", "ESP32ダミー出力"),
            encoder_status=encoder_status,
            odom_status=odom_status,
            distance_status=distance_status,
            line_status=line_status,
            color_status=color_status,
            distance_sensor_mm=sanitize_distance(self.distance_sensor_mm, distance_status),
            line_value=sanitize_number(self.line_value, min_value=0.0, max_value=1000.0) if is_sensor_active(line_status) else 0.0,
            sensor_age_text=self.sensor_age_text(),
            color_name=self.color_name if is_sensor_active(color_status) else "未接続",
        )

    def _set_imu_status(self, status: object, now: float) -> None:
        self.imu_status = normalize_status(status)
        self.imu_source = source_label_for_status(self.imu_status, "実IMU", "ESP32ダミー出力")
        if not is_sensor_active(self.imu_status):
            self.yaw = 0.0
            self.pitch = 0.0
            self.roll = 0.0
            self.gyro_x = 0.0
            self.gyro_y = 0.0
            self.gyro_z = 0.0
            self.accel_x_g = 0.0
            self.accel_y_g = 0.0
            self.accel_z_g = 0.0
        self._touch(now)
        self.last_imu_update_time = now

    def _set_lidar_status(self, status: object, now: float) -> None:
        self.lidar_status = normalize_status(status)
        self.lidar_source = source_label_for_status(self.lidar_status, "実データ", "ESP32ダミー出力")
        if not is_sensor_active(self.lidar_status):
            self._clear_lidar_values()
        self._touch(now)
        self.last_lidar_update_time = now

    def sensor_age_text(self) -> str:
        line_color_time = max(self.last_line_update_time, self.last_color_update_time)
        line_color_status = self.line_status if self.last_line_update_time >= self.last_color_update_time else self.color_status
        items = [
            ("IMU", self.imu_status, self.last_imu_update_time),
            ("LiDAR", self.lidar_status, self.last_lidar_update_time),
            ("エンコーダ", self.encoder_status, self.last_encoder_update_time),
            ("光学式", self.odom_status, self.last_odom_update_time),
            ("距離", self.distance_status, self.last_distance_update_time),
            ("ライン/カラー", line_color_status, line_color_time),
        ]
        return " / ".join(self._format_age(name, status, timestamp) for name, status, timestamp in items)

    def _format_age(self, name: str, status: str, timestamp: float) -> str:
        normalized = normalize_status(status)
        if normalized == "OK":
            label = "OK"
        elif normalized == "DUMMY":
            label = "DUMMY"
        elif normalized == "ERROR":
            label = "ERROR"
        else:
            label = "未受信"
        if timestamp <= 0:
            return f"{name}: {label} 未受信"
        age = max(0.0, time.monotonic() - timestamp)
        return f"{name}: {label} {age:.1f}秒前"

    def _clear_lidar_values(self) -> None:
        self.front_distance_mm = 0
        self.left_distance_mm = 0
        self.right_distance_mm = 0
        self.rear_distance_mm = 0

    def _touch(self, now: float) -> None:
        self.connected = True
        self.last_update_time = now
