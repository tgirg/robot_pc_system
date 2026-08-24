from __future__ import annotations

import math

try:
    from ..control.robot_command import RobotCommand, format_command
    from ..mock_sensors import SensorData
except ImportError:
    from control.robot_command import RobotCommand, format_command
    from mock_sensors import SensorData

from .field_model import FieldModel
from .simulation_state import SimulationState
from .virtual_lidar import VirtualLidar


class RobotSimulator:
    def __init__(
        self,
        field: FieldModel | None = None,
        robot_speed_mm_s: float = 200.0,
        turn_speed_deg_s: float = 60.0,
        start_x_mm: float = 0.0,
        start_y_mm: float = 0.0,
        start_theta_deg: float = 0.0,
    ) -> None:
        self.field = field or FieldModel()
        self.robot_speed_mm_s = float(robot_speed_mm_s)
        self.turn_speed_deg_s = float(turn_speed_deg_s)
        self.start_x_mm = float(start_x_mm)
        self.start_y_mm = float(start_y_mm)
        self.start_theta_deg = float(start_theta_deg)
        self.lidar = VirtualLidar(self.field)
        self.state = SimulationState()
        self._last_odom_dx_mm = 0.0
        self._last_odom_dy_mm = 0.0
        self.reset()

    @classmethod
    def from_config(cls, field_config: dict, simulation_config: dict) -> "RobotSimulator":
        return cls(
            field=FieldModel.from_config(field_config, simulation_config.get("obstacles", [])),
            robot_speed_mm_s=float(simulation_config.get("robot_speed_mm_s", 200)),
            turn_speed_deg_s=float(simulation_config.get("turn_speed_deg_s", 60)),
            start_x_mm=float(simulation_config.get("start_x_mm", 0)),
            start_y_mm=float(simulation_config.get("start_y_mm", 0)),
            start_theta_deg=float(simulation_config.get("start_theta_deg", 0)),
        )

    def apply_command(self, command: RobotCommand) -> str:
        text = format_command(command)
        self.state.last_command = text

        if command.category == "DRIVE" and command.action == "VEL" and len(command.args) >= 2:
            self.state.drive_mode = "legacy"
            self.state.vx_norm = 0.0
            self.state.vy_norm = 0.0
            self.state.omega_norm = 0.0
            self.state.left_speed = int(command.args[0])
            self.state.right_speed = int(command.args[1])
            self.state.running = self.state.left_speed != 0 or self.state.right_speed != 0
            if self.state.running:
                self.state.boundary_status = ""
                self.state.obstacle_status = ""
            if not self.state.running:
                return "シミュレーション停止"
            return f"シミュレーション指令: {text}"

        if command.category == "DRIVE" and command.action == "STOP":
            self.stop("DRIVE STOP")
            return "シミュレーション停止"

        if command.category == "SYSTEM" and command.action == "EMERGENCY_STOP":
            self.stop("EMERGENCY_STOP")
            return "シミュレーション停止"

        return f"シミュレーション未対応指令: {text}"

    def apply_controller_input(self, vx: float, vy: float, omega: float, label: str = "SIM CONTROLLER") -> None:
        vx = max(-1.0, min(1.0, float(vx)))
        vy = max(-1.0, min(1.0, float(vy)))
        omega = max(-1.0, min(1.0, float(omega)))
        self.state.drive_mode = "4wis"
        self.state.vx_norm = vx
        self.state.vy_norm = vy
        self.state.omega_norm = omega
        self.state.left_speed = int(round(max(-1.0, min(1.0, vx - omega)) * 255.0))
        self.state.right_speed = int(round(max(-1.0, min(1.0, vx + omega)) * 255.0))
        self.state.running = abs(vx) > 0.001 or abs(vy) > 0.001 or abs(omega) > 0.001
        self.state.last_command = f"{label} vx={vx:+.2f} vy={vy:+.2f} omega={omega:+.2f}" if self.state.running else "DRIVE STOP"
        if self.state.running:
            self.state.boundary_status = ""
            self.state.obstacle_status = ""

    def stop(self, command_text: str = "DRIVE STOP") -> None:
        self.state.left_speed = 0
        self.state.right_speed = 0
        self.state.vx_norm = 0.0
        self.state.vy_norm = 0.0
        self.state.omega_norm = 0.0
        self.state.running = False
        self.state.last_command = command_text

    def reset(self) -> None:
        x_mm, y_mm, boundary_status = self.field.clamp_position(self.start_x_mm, self.start_y_mm)
        self.state = SimulationState(
            running=False,
            last_command="DRIVE STOP",
            boundary_status=boundary_status,
            obstacle_status="",
            left_speed=0,
            right_speed=0,
            x_mm=x_mm,
            y_mm=y_mm,
            theta_deg=self.start_theta_deg % 360.0,
            left_encoder=0,
            right_encoder=0,
        )
        self._last_odom_dx_mm = 0.0
        self._last_odom_dy_mm = 0.0

    def reset_pose_to_start(self) -> None:
        x_mm, y_mm, boundary_status = self.field.clamp_position(self.start_x_mm, self.start_y_mm)
        self.stop("DRIVE STOP")
        self.state.x_mm = x_mm
        self.state.y_mm = y_mm
        self.state.theta_deg = self.start_theta_deg % 360.0
        self.state.boundary_status = boundary_status
        self.state.obstacle_status = ""
        self._last_odom_dx_mm = 0.0
        self._last_odom_dy_mm = 0.0

    def step(self, dt: float) -> SensorData:
        dt = max(0.0, float(dt))
        if self.state.drive_mode == "4wis":
            left_norm = self.state.left_speed / 255.0
            right_norm = self.state.right_speed / 255.0
            forward_mm_s = self.state.vx_norm * self.robot_speed_mm_s
            lateral_mm_s = self.state.vy_norm * self.robot_speed_mm_s
            turn_deg_s = self.state.omega_norm * self.turn_speed_deg_s
            theta_rad = math.radians(self.state.theta_deg)
            dx_mm = (forward_mm_s * math.cos(theta_rad) - lateral_mm_s * math.sin(theta_rad)) * dt
            dy_mm = (forward_mm_s * math.sin(theta_rad) + lateral_mm_s * math.cos(theta_rad)) * dt
            self.state.theta_deg = (self.state.theta_deg + turn_deg_s * dt) % 360.0
        else:
            left_norm = self.state.left_speed / 255.0
            right_norm = self.state.right_speed / 255.0
            forward_mm_s = ((left_norm + right_norm) / 2.0) * self.robot_speed_mm_s
            turn_deg_s = (right_norm - left_norm) * self.turn_speed_deg_s
            self.state.theta_deg = (self.state.theta_deg + turn_deg_s * dt) % 360.0
            theta_rad = math.radians(self.state.theta_deg)
            dx_mm = forward_mm_s * math.cos(theta_rad) * dt
            dy_mm = forward_mm_s * math.sin(theta_rad) * dt

        next_x, next_y, boundary_status = self.field.clamp_position(
            self.state.x_mm + dx_mm,
            self.state.y_mm + dy_mm,
        )
        obstacle_status = ""
        if not boundary_status and self.field.collides_with_obstacle(next_x, next_y):
            next_x = self.state.x_mm
            next_y = self.state.y_mm
            dx_mm = 0.0
            dy_mm = 0.0
            obstacle_status = "障害物に接触"
            self.stop(self.state.last_command)

        if boundary_status:
            dx_mm = next_x - self.state.x_mm
            dy_mm = next_y - self.state.y_mm
            self.stop(self.state.last_command)

        self.state.x_mm = next_x
        self.state.y_mm = next_y
        if boundary_status:
            self.state.boundary_status = boundary_status
        elif obstacle_status:
            self.state.boundary_status = ""
            self.state.obstacle_status = obstacle_status
        elif self.state.running:
            self.state.boundary_status = ""
            self.state.obstacle_status = ""
        self._last_odom_dx_mm = dx_mm
        self._last_odom_dy_mm = dy_mm

        self.state.left_encoder += int(abs(left_norm) * 40 * dt)
        self.state.right_encoder += int(abs(right_norm) * 40 * dt)
        reading = self.lidar.scan(self.state.x_mm, self.state.y_mm, self.state.theta_deg)
        self.state.lidar_front_mm = reading.front_mm
        self.state.lidar_left_mm = reading.left_mm
        self.state.lidar_right_mm = reading.right_mm
        self.state.lidar_rear_mm = reading.rear_mm
        return self.to_sensor_data()

    def to_sensor_data(self) -> SensorData:
        return SensorData(
            lidar_distance=self.state.lidar_front_mm / 1000.0,
            imu_yaw=self.state.theta_deg,
            imu_pitch=0.0,
            imu_roll=0.0,
            odom_dx=self._last_odom_dx_mm / 1000.0,
            odom_dy=self._last_odom_dy_mm / 1000.0,
            encoder_left=self.state.left_encoder,
            encoder_right=self.state.right_encoder,
            pose_x=self.state.x_mm / 1000.0,
            pose_y=self.state.y_mm / 1000.0,
            pose_theta=self.state.theta_deg,
            source="Simulation",
            connected=False,
            lidar_front_mm=self.state.lidar_front_mm,
            lidar_left_mm=self.state.lidar_left_mm,
            lidar_right_mm=self.state.lidar_right_mm,
            lidar_rear_mm=self.state.lidar_rear_mm,
            gyro_x=0.0,
            gyro_y=0.0,
            gyro_z=(self.state.right_speed - self.state.left_speed) / 255.0 * self.turn_speed_deg_s,
            imu_status="OK",
            imu_source="シミュレーション",
            lidar_status="OK",
            lidar_source="シミュレーション",
            encoder_status="OK",
            odom_status="OK",
            distance_status="未接続",
            line_status="未接続",
            color_status="未接続",
        )
