from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from control import MockCommandSender, SafetyLayer, format_command, parse_command  # noqa: E402


def main() -> None:
    sender = MockCommandSender()
    safety = SafetyLayer(max_drive_speed=120, command_timeout_ms=500)
    commands = [
        "DRIVE VEL 100 100",
        "DRIVE VEL 300 -300",
        "TURN_L 80",
        "INVALID COMMAND",
        "EMERGENCY_STOP",
        "DRIVE VEL 60 60",
        "DRIVE STOP",
        "DRIVE VEL 60 60",
    ]

    print("コマンドレイヤーのテストを開始します。")
    for text in commands:
        parsed = parse_command(text)
        safety_result = safety.filter_command(parsed)
        safe_text = format_command(safety_result.command)
        print(f"\n入力: {text}")
        if safety_result.message:
            print(f"安全メッセージ: {safety_result.message}")
        if not safety_result.allowed:
            print(f"送信なし: {safe_text}")
            continue
        result = sender.send(safety_result.command)
        print(f"送信: {result.sent_text}")
        print(f"結果: {'成功' if result.success else '失敗'} / {result.message}")

    print("\nMock送信履歴:")
    for sent in sender.sent_commands:
        print(f"- {sent}")


if __name__ == "__main__":
    main()
