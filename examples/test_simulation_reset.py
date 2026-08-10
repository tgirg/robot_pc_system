from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from control import parse_command  # noqa: E402
from simulation import FieldModel, RobotSimulator  # noqa: E402


def main() -> None:
    simulator = RobotSimulator(
        field=FieldModel(width_mm=3000, height_mm=2000, grid_size_mm=100),
        robot_speed_mm_s=250,
        turn_speed_deg_s=60,
        start_x_mm=300,
        start_y_mm=300,
        start_theta_deg=15,
    )

    print("シミュレーションリセットテストを開始します。")
    print(
        f"初期位置: x={simulator.state.x_mm:.1f} mm / "
        f"y={simulator.state.y_mm:.1f} mm / θ={simulator.state.theta_deg:.1f} deg"
    )

    simulator.apply_command(parse_command("DRIVE VEL 150 150"))
    for _ in range(20):
        simulator.step(0.1)
    print(
        f"移動後: x={simulator.state.x_mm:.1f} mm / "
        f"y={simulator.state.y_mm:.1f} mm / θ={simulator.state.theta_deg:.1f} deg"
    )

    simulator.reset()
    ok = (
        abs(simulator.state.x_mm - 300) < 0.001
        and abs(simulator.state.y_mm - 300) < 0.001
        and abs(simulator.state.theta_deg - 15) < 0.001
        and not simulator.state.running
    )
    print(
        f"リセット後: x={simulator.state.x_mm:.1f} mm / "
        f"y={simulator.state.y_mm:.1f} mm / θ={simulator.state.theta_deg:.1f} deg"
    )
    print("結果: 成功" if ok else "結果: 失敗")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
