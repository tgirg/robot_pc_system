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


STARTUP_SIGNALS = (
    "BOOT,DRIVE_CONTROLLER_READY",
    "STATUS,OK",
    "IMU,",
    "GYRO,",
    "ENC,",
)


def print_detection(line: str) -> None:
    if line.startswith("BOOT,DRIVE_CONTROLLER_READY"):
        print("BOOT detected: drive_controller 起動を確認しました。")
    elif line.startswith("STATUS,OK"):
        print("STATUS detected: STATUS,OK を確認しました。")
    elif line.startswith("IMU,"):
        print("IMU detected: IMU行を確認しました。")
    elif line.startswith("GYRO,"):
        print("GYRO detected: GYRO行を確認しました。")
    elif line.startswith("ENC,"):
        print("ENC detected: ENC行を確認しました。")
    elif line.startswith("RX,DRIVE VEL 50 50"):
        print("command echo detected: DRIVE VEL 50 50 のエコーを確認しました。")
    elif line.startswith("DRIVE,50,50"):
        print("drive response detected: DRIVE,50,50 を確認しました。")


def wait_for_line(connection: SerialConnection, timeout_s: float, prefixes: tuple[str, ...]) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for line in connection.read_lines(max_lines=30):
            print(f"受信: {line}")
            print_detection(line)
            if line.startswith(prefixes):
                return line
        time.sleep(0.05)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32 drive_controller の初回接続確認を行います。")
    parser.add_argument("port", help="COMポート例: COM10")
    parser.add_argument("--baudrate", type=int, default=115200, help="通信速度。既定値: 115200")
    args = parser.parse_args()

    connection = SerialConnection(timeout=0.05)
    print(f"ESP32へ接続します: {args.port} / {args.baudrate} bps")
    result = connection.connect(args.port, args.baudrate)
    print(result.message)
    if not result.success:
        print("失敗: COMポートを開けません。Arduino IDEのシリアルモニタを閉じてください。")
        raise SystemExit(1)

    try:
        print("BOOT または STATUS,OK を最大5秒待ちます。")
        startup_line = wait_for_line(connection, 5.0, STARTUP_SIGNALS)
        if not startup_line:
            print("失敗: ESP32から起動信号またはSTATUSを受信できませんでした。")
            raise SystemExit(1)
        print(f"起動確認OK: {startup_line}")

        print("低速走行テスト指令を送信します: DRIVE VEL 50 50")
        send_result = connection.send_line("DRIVE VEL 50 50")
        print(send_result.message)
        response = wait_for_line(connection, 2.0, ("RX,DRIVE VEL 50 50", "DRIVE,50,50"))
        if not response:
            print("失敗: DRIVE VEL 50 50 の応答を受信できませんでした。")
            raise SystemExit(1)
        print(f"走行指令応答OK: {response}")

        print("停止指令を送信します: DRIVE STOP")
        connection.send_line("DRIVE STOP")
        stop_response = wait_for_line(connection, 2.0, ("RX,DRIVE STOP", "DRIVE,0,0"))
        if not stop_response:
            print("失敗: DRIVE STOP の応答を受信できませんでした。")
            raise SystemExit(1)
        print(f"停止応答OK: {stop_response}")
        print("結果: 初回接続テスト成功")
    finally:
        connection.send_line("DRIVE STOP")
        connection.disconnect()
        print("シリアル接続を閉じました。")


if __name__ == "__main__":
    main()
