from __future__ import annotations

import argparse

import serial


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32のシリアル出力を表示します。")
    parser.add_argument("port", help="COMポート例: COM10")
    parser.add_argument("--baudrate", type=int, default=115200, help="ボーレート。既定値: 115200")
    args = parser.parse_args()

    print(f"ESP32シリアル出力を読み取ります: {args.port} / {args.baudrate} bps")
    print("終了するには Ctrl+C を押してください。")
    try:
        with serial.Serial(args.port, args.baudrate, timeout=1.0) as conn:
            while True:
                raw = conn.readline()
                if not raw:
                    continue
                print(raw.decode("utf-8", errors="replace").rstrip())
    except serial.SerialException as exc:
        print(f"エラー: シリアルポートを開けませんでした: {exc}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("\n終了しました。")


if __name__ == "__main__":
    main()
