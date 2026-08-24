from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class SensorData:
    lidar_distance: float
    imu_yaw: float
    imu_pitch: float
    imu_roll: float
    odom_dx: float
    odom_dy: float
    encoder_left: int
    encoder_right: int
    pose_x: float
    pose_y: float
    pose_theta: float
    source: str = "Mock"
    connected: bool = False
    lidar_front_mm: float = 0.0
    lidar_left_mm: float = 0.0
    lidar_right_mm: float = 0.0
    lidar_rear_mm: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    accel_x_g: float = 0.0
    accel_y_g: float = 0.0
    accel_z_g: float = 0.0
    imu_status: str = "未接続"
    imu_source: str = "未接続"
    lidar_status: str = "未接続"
    lidar_source: str = "未接続"
    encoder_status: str = "未接続"
    odom_status: str = "未接続"
    distance_status: str = "未接続"
    line_status: str = "未接続"
    color_status: str = "未接続"
    distance_sensor_mm: float = 0.0
    line_value: float = 0.0
    sensor_age_text: str = ""
    color_name: str = "未接続"
    lsb_status: str = "未接続"
    lsb_board_id: str = "未接続"
    lsb_fw_version: str = ""
    lsb_seq: int = 0
    lsb_i2c_summary: str = "未受信"
    lsb_error: str = ""
    lsb_tof_front_mm: float = 0.0
    lsb_tof_right_mm: float = 0.0
    lsb_tof_rear_mm: float = 0.0
    lsb_tof_left_mm: float = 0.0
    lsb_us_front_l_mm: float = 0.0
    lsb_us_front_r_mm: float = 0.0
    lsb_us_right_f_mm: float = 0.0
    lsb_us_right_r_mm: float = 0.0
    lsb_us_rear_r_mm: float = 0.0
    lsb_us_rear_l_mm: float = 0.0
    lsb_us_left_r_mm: float = 0.0
    lsb_us_left_f_mm: float = 0.0


class MockSensors:
    def __init__(self, lidar_min_m: float = 0.35, lidar_max_m: float = 3.0) -> None:
        self.start_time = time.monotonic()
        self.encoder_left = 0
        self.encoder_right = 0
        self.pose_x = 0.0
        self.pose_y = 0.0
        self.pose_theta = 0.0
        self.lidar_min_m = lidar_min_m
        self.lidar_max_m = lidar_max_m

    def read(self, dt: float = 0.1, source: str = "Mock", connected: bool = False) -> SensorData:
        t = time.monotonic() - self.start_time
        speed = 0.16 + 0.04 * math.sin(t * 0.8)
        turn_rate = 0.45 * math.sin(t * 0.35)
        self.pose_theta += turn_rate * dt
        odom_dx = speed * math.cos(self.pose_theta) * dt
        odom_dy = speed * math.sin(self.pose_theta) * dt
        self.pose_x += odom_dx
        self.pose_y += odom_dy

        tick_step_l = int(8 + 3 * math.sin(t))
        tick_step_r = int(8 + 3 * math.cos(t * 0.7))
        self.encoder_left += max(0, tick_step_l)
        self.encoder_right += max(0, tick_step_r)

        if source == "Simulation":
            imu_status = "OK"
            lidar_status = "OK"
            encoder_status = "OK"
            odom_status = "OK"
            label = "シミュレーション"
            lidar_span = self.lidar_max_m - self.lidar_min_m
            lidar_distance = self.lidar_min_m + lidar_span * (0.5 + 0.5 * math.sin(t * 0.9))
            lidar_front_mm = lidar_distance * 1000.0
        elif source == "Mock":
            imu_status = "DUMMY"
            lidar_status = "DUMMY"
            encoder_status = "DUMMY"
            odom_status = "DUMMY"
            label = "Mockデータ"
            lidar_distance = 0.0
            lidar_front_mm = 0.0
        else:
            imu_status = "未接続"
            lidar_status = "未接続"
            encoder_status = "未接続"
            odom_status = "未接続"
            label = "未接続"
            lidar_distance = 0.0
            lidar_front_mm = 0.0

        return SensorData(
            lidar_distance=lidar_distance,
            imu_yaw=math.degrees(self.pose_theta) % 360.0 if imu_status == "OK" else 0.0,
            imu_pitch=4.0 * math.sin(t * 0.6) if imu_status == "OK" else 0.0,
            imu_roll=3.0 * math.cos(t * 0.5) if imu_status == "OK" else 0.0,
            odom_dx=odom_dx if odom_status == "OK" else 0.0,
            odom_dy=odom_dy if odom_status == "OK" else 0.0,
            encoder_left=self.encoder_left if encoder_status == "OK" else 0,
            encoder_right=self.encoder_right if encoder_status == "OK" else 0,
            pose_x=self.pose_x,
            pose_y=self.pose_y,
            pose_theta=math.degrees(self.pose_theta),
            source=source,
            connected=connected,
            lidar_front_mm=lidar_front_mm,
            lidar_left_mm=0.0,
            lidar_right_mm=0.0,
            lidar_rear_mm=0.0,
            gyro_x=0.0,
            gyro_y=0.0,
            gyro_z=turn_rate if imu_status == "OK" else 0.0,
            imu_status=imu_status,
            imu_source=label,
            lidar_status=lidar_status,
            lidar_source=label,
            encoder_status=encoder_status,
            odom_status=odom_status,
            distance_status="未接続",
            line_status="未接続",
            color_status="未接続",
        )
