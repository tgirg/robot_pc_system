from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from control import parse_command  # noqa: E402
from simulation import FieldModel, RobotSimulator  # noqa: E402


def step_and_print(simulator: RobotSimulator, seconds: float, dt: float = 0.1) -> None:
    steps = int(seconds / dt)
    for _ in range(steps):
        data = simulator.step(dt)
    state = simulator.state
    print(
        f"位置: x={state.x_mm:.1f} mm / y={state.y_mm:.1f} mm / θ={state.theta_deg:.1f} deg | "
        f"Encoder={state.left_encoder}/{state.right_encoder} | "
        f"状態={state.boundary_status or '通常'} | "
        f"LiDAR={data.lidar_distance:.2f} m"
    )


def main() -> None:
    field = FieldModel(width_mm=1000, height_mm=800, grid_size_mm=100)
    simulator = RobotSimulator(field=field, robot_speed_mm_s=300, turn_speed_deg_s=90)

    print("シミュレーションテストを開始します。")
    for text in ["DRIVE VEL 120 120", "DRIVE VEL -80 80", "DRIVE STOP"]:
        command = parse_command(text)
        print(f"\n適用: {text}")
        print(simulator.apply_command(command))
        step_and_print(simulator, 1.0)

    print("\n境界クランプの確認")
    simulator.state.x_mm = 480
    simulator.state.y_mm = 0
    command = parse_command("DRIVE VEL 255 255")
    print(simulator.apply_command(command))
    step_and_print(simulator, 2.0)

    print("\n緊急停止の確認")
    command = parse_command("EMERGENCY_STOP")
    print(simulator.apply_command(command))
    step_and_print(simulator, 0.5)


if __name__ == "__main__":
    main()
