from __future__ import annotations

import argparse
import time

import serial


COMMANDS = [
    "DRIVE VEL 100 100",
    "DRIVE VEL 0 0",
    "DRIVE VEL -80 80",
    "DRIVE VEL 80 -80",
    "EMERGENCY_STOP",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32へ走行テストコマンドを送信します。")
    parser.add_argument("port", help="COMポート例: COM10")
    parser.add_argument("--baudrate", type=int, default=115200, help="ボーレート。既定値: 115200")
    parser.add_argument("--interval", type=float, default=0.8, help="送信間隔秒。既定値: 0.8")
    args = parser.parse_args()

    print(f"ESP32へ接続します: {args.port} / {args.baudrate} bps")
    try:
        with serial.Serial(args.port, args.baudrate, timeout=1.0) as conn:
            for command in COMMANDS:
                print(f"送信: {command}")
                conn.write((command + "\n").encode("utf-8"))
                conn.flush()
                time.sleep(args.interval)
    except serial.SerialException as exc:
        print(f"エラー: シリアルポートを開けませんでした: {exc}")
        raise SystemExit(1) from exc

    print("送信完了")


if __name__ == "__main__":
    main()
