from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from connection import SerialConnection  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32とのシリアル接続を確認します。")
    parser.add_argument("port", help="COMポート例: COM10")
    parser.add_argument("--baudrate", type=int, default=115200, help="通信速度。既定値: 115200")
    args = parser.parse_args()

    connection = SerialConnection(timeout=0.05)
    print(f"接続します: {args.port} / {args.baudrate}")
    result = connection.connect(args.port, args.baudrate)
    print(result.message)
    if not result.success:
        raise SystemExit(1)

    try:
        print("STATUS? を送信します。5秒間受信を確認します。")
        connection.send_line("STATUS?")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            for line in connection.read_lines(max_lines=20):
                print(f"受信: {line}")
            time.sleep(0.1)
    finally:
        connection.disconnect()
        print("切断しました。")


if __name__ == "__main__":
    main()
