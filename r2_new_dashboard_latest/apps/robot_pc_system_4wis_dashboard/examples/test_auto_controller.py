from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from control import AutoController, format_command  # noqa: E402


def check(name: str, front: float, left: float, right: float, expected: str) -> None:
    controller = AutoController(
        forward_speed=100,
        turn_speed=80,
        front_stop_distance_mm=400,
        side_preference_margin_mm=100,
    )
    decision = controller.decide(front, left, right)
    command_text = format_command(decision.command)
    print(f"{name}: 判断={decision.action} / 指令={command_text} / 理由={decision.reason}")
    if decision.action != expected:
        raise SystemExit(f"失敗: {name} は {expected} の想定ですが {decision.action} でした")


def main() -> None:
    print("自動走行コントローラのテストを開始します。")
    check("前方クリア", front=1200, left=800, right=800, expected="前進")
    check("前方ブロック・左が広い", front=250, left=1000, right=300, expected="左旋回")
    check("前方ブロック・右が広い", front=250, left=300, right=1000, expected="右旋回")
    check("全方向ブロック", front=200, left=250, right=260, expected="停止")

    controller = AutoController()
    missing = controller.decide(None, None, None)
    print(f"LiDARなし: 判断={missing.action} / 指令={format_command(missing.command)} / 理由={missing.reason}")
    if missing.action != "停止":
        raise SystemExit("失敗: LiDARなしでは停止する必要があります")
    print("結果: 成功")


if __name__ == "__main__":
    main()
