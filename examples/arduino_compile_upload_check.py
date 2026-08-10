from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from arduino_tools import (  # noqa: E402
    compile_drive_controller,
    find_arduino_cli,
    run_arduino_version,
    run_board_list,
    run_core_list,
    upload_drive_controller,
)


def print_result(title: str, result) -> int:
    print(f"=== {title} ===")
    print(f"結果: {'成功' if result.success else '失敗'}")
    print(f"コマンド: {' '.join(result.command)}")
    print(f"戻り値: {result.return_code}")
    print("--- stdout ---")
    print(result.stdout.strip() or "(なし)")
    print("--- stderr ---")
    print(result.stderr.strip() or "(なし)")
    return 0 if result.success else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Arduino CLI確認ツール")
    parser.add_argument("--compile", action="store_true", help="ESP32スケッチをコンパイルします。")
    parser.add_argument("--upload", metavar="PORT", help="指定COMポートへ書き込みます。")
    parser.add_argument("--board-list", action="store_true", help="接続ボード一覧を表示します。")
    parser.add_argument("--check", action="store_true", help="Arduino CLIとESP32 coreを確認します。")
    parser.add_argument("--fqbn", default="esp32:esp32:esp32", help="使用するFQBN")
    args = parser.parse_args()

    cli = find_arduino_cli()
    print(f"使用Arduino CLI: {cli or '未検出'}")
    if cli is None:
        return 1

    exit_code = 0
    if args.check:
        exit_code |= print_result("Arduino CLI version", run_arduino_version())
        core_result = run_core_list()
        exit_code |= print_result("Arduino core list", core_result)
        print(f"ESP32 core: {'OK' if 'esp32:esp32' in core_result.stdout else 'NG'}")
    if args.board_list:
        exit_code |= print_result("Arduino board list", run_board_list())
    if args.compile:
        exit_code |= print_result("ESP32 compile", compile_drive_controller(args.fqbn))
    if args.upload:
        print("注意: これからESP32へ書き込みます。モータ出力はファームウェア既定で無効です。")
        exit_code |= print_result("ESP32 upload", upload_drive_controller(args.upload, args.fqbn))
    if not any([args.check, args.board_list, args.compile, args.upload]):
        parser.print_help()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
