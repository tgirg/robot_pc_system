from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from control import parse_command  # noqa: E402
from simulation import FieldModel, RectObstacle, RobotSimulator, VirtualLidar  # noqa: E402


def main() -> None:
    field = FieldModel(
        width_mm=3000,
        height_mm=2000,
        grid_size_mm=100,
        obstacles=[
            RectObstacle(id="box", label="箱", x_mm=700, y_mm=0, width_mm=200, height_mm=300),
        ],
    )
    lidar = VirtualLidar(field)
    simulator = RobotSimulator(field=field, robot_speed_mm_s=300, turn_speed_deg_s=90)

    print("仮想LiDARテストを開始します。")
    first = lidar.scan(0, 0, 0)
    print(f"初期距離: 前方={first.front_mm:.0f} mm / 左={first.left_mm:.0f} mm / 右={first.right_mm:.0f} mm")

    simulator.apply_command(parse_command("DRIVE VEL 255 255"))
    for _ in range(10):
        simulator.step(0.1)
    moved = lidar.scan(simulator.state.x_mm, simulator.state.y_mm, simulator.state.theta_deg)
    print(
        f"移動後距離: 前方={moved.front_mm:.0f} mm / "
        f"位置 x={simulator.state.x_mm:.1f} mm / 状態={simulator.state.obstacle_status or '正常'}"
    )

    if moved.front_mm >= first.front_mm:
        print("結果: 失敗（障害物までの距離が減っていません）")
        raise SystemExit(1)

    for _ in range(20):
        simulator.step(0.1)
    print(
        f"接触確認: x={simulator.state.x_mm:.1f} mm / "
        f"障害物状態={simulator.state.obstacle_status or '正常'}"
    )
    if simulator.state.obstacle_status != "障害物に接触":
        print("結果: 失敗（障害物接触が検出されませんでした）")
        raise SystemExit(1)

    print("結果: 成功")


if __name__ == "__main__":
    main()
