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
from hardware_check import HardwareCheckLogger, HardwareCheckResult  # noqa: E402
from hardware_profile import load_hardware_profile  # noqa: E402


ALIVE_PREFIXES = (
    "BOOT,DRIVE_CONTROLLER_READY",
    "STATUS,OK",
    "IMU_STATUS,DUMMY",
    "IMU_STATUS,OK",
    "LIDAR_STATUS,DUMMY",
    "LIDAR_STATUS,OK",
    "IMU,",
    "GYRO,",
    "ENC,",
    "LIDAR,",
)


class QuickHardwareCheck:
    def __init__(self, port: str, baudrate: int) -> None:
        self.port = port
        self.baudrate = baudrate
        self.raw_lines: list[str] = []
        self.esp32_connected = False
        self.status_received = False
        self.imu_received = False
        self.imu_status = "no_data"
        self.lidar_received = False
        self.lidar_status = "no_data"
        self.encoder_received = False
        self.motor_dummy_received = False
        self.test_command_sent = False
        self.test_response_received = False
        self.stop_sent = False
        self.stop_response_received = False
        self.error_message = ""

    def update_from_line(self, line: str) -> None:
        print(f"受信: {line}")
        self.raw_lines.append(line)
        if line.startswith("STATUS,OK") or line.startswith("BOOT,DRIVE_CONTROLLER_READY"):
            self.status_received = True
        elif line.startswith("IMU_STATUS,DUMMY"):
            self.imu_received = True
            self.imu_status = "dummy"
        elif line.startswith("IMU_STATUS,OK") or line.startswith("IMU,"):
            self.imu_received = True
            self.imu_status = "ok"
        elif line.startswith("IMU_STATUS,ERROR"):
            self.imu_received = True
            self.imu_status = "error"
        elif line.startswith("LIDAR_STATUS,DUMMY"):
            self.lidar_received = True
            self.lidar_status = "dummy"
        elif line.startswith("LIDAR_STATUS,OK") or line.startswith("LIDAR,"):
            self.lidar_received = True
            self.lidar_status = "ok"
        elif line.startswith("LIDAR_STATUS,ERROR"):
            self.lidar_received = True
            self.lidar_status = "error"
        elif line.startswith("ENC,"):
            self.encoder_received = True

        if line.startswith("MOTOR_DUMMY,"):
            self.motor_dummy_received = True
            if line.startswith("MOTOR_DUMMY,50,50"):
                self.test_response_received = True
            elif line.startswith("MOTOR_DUMMY,0,0"):
                self.stop_response_received = True
        if line.startswith("RX,DRIVE VEL 50 50") or line.startswith("DRIVE,50,50"):
            self.test_response_received = True
            self.motor_dummy_received = True
        if line.startswith("RX,DRIVE STOP") or line.startswith("DRIVE,0,0"):
            self.stop_response_received = True
            self.motor_dummy_received = True

    def alive_received(self) -> bool:
        return any(line.startswith(ALIVE_PREFIXES) for line in self.raw_lines)

    def final_result(self) -> str:
        required = [
            self.esp32_connected,
            self.status_received,
            self.imu_received,
            self.lidar_received,
            self.encoder_received,
            self.motor_dummy_received,
            self.test_command_sent,
            self.test_response_received,
            self.stop_sent,
            self.stop_response_received,
        ]
        if all(required):
            return "success"
        if self.esp32_connected and self.stop_sent:
            return "partial_failure"
        return "failure"

    def to_result(self) -> HardwareCheckResult:
        return HardwareCheckResult(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            selected_com_port=self.port,
            baudrate=self.baudrate,
            esp32_connected=self.esp32_connected,
            status_received=self.status_received,
            imu_received=self.imu_received,
            imu_status=self.imu_status,
            lidar_received=self.lidar_received,
            lidar_status=self.lidar_status,
            encoder_received=self.encoder_received,
            motor_dummy_received=self.motor_dummy_received,
            test_command_sent=self.test_command_sent,
            test_response_received=self.test_response_received,
            stop_sent=self.stop_sent,
            stop_response_received=self.stop_response_received,
            final_result=self.final_result(),
            error_message=self.error_message,
            raw_lines=self.raw_lines,
            hardware_profile_summary=load_hardware_profile().to_summary_text(),
            motor_output_enabled="0",
            use_real_imu="0",
            use_real_lidar="0",
        )

    def print_summary(self) -> None:
        result = self.to_result()
        print("")
        print(result.to_text())


def wait_until(connection: SerialConnection, seconds: float, check: QuickHardwareCheck, predicate) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for line in connection.read_lines(max_lines=50):
            check.update_from_line(line)
            if predicate():
                return True
        time.sleep(0.05)
    return predicate()


def read_for(connection: SerialConnection, seconds: float, check: QuickHardwareCheck) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for line in connection.read_lines(max_lines=50):
            check.update_from_line(line)
        time.sleep(0.05)


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32実機クイック確認を実行します。")
    parser.add_argument("port", help="COMポート例: COM10")
    parser.add_argument("--baudrate", type=int, default=115200, help="通信速度。既定値: 115200")
    parser.add_argument("--save", action="store_true", help="結果を logs\\hardware_checks に保存します。")
    parser.add_argument("--duration", type=float, default=5.0, help="生存信号を待つ秒数。既定値: 5")
    args = parser.parse_args()

    check = QuickHardwareCheck(args.port, args.baudrate)
    connection = SerialConnection(timeout=0.05)
    print(f"ESP32へ接続します: {args.port} / {args.baudrate} bps")
    connect_result = connection.connect(args.port, args.baudrate)
    print(connect_result.message)
    if not connect_result.success:
        check.error_message = "COMポートを開けませんでした"
        check.print_summary()
        if args.save:
            save_result(check)
        return 1
    check.esp32_connected = True

    try:
        print(f"生存信号を最大{args.duration:.1f}秒待ちます。")
        wait_until(connection, args.duration, check, check.alive_received)
        read_for(connection, 1.0, check)
        if not check.alive_received():
            check.error_message = "ESP32から生存信号を受信できませんでした"
            print(check.error_message)

        print("テスト送信: DRIVE VEL 50 50")
        send_result = connection.send_line("DRIVE VEL 50 50")
        print(send_result.message)
        check.test_command_sent = send_result.success
        wait_until(connection, 2.0, check, lambda: check.test_response_received)

        print("STOP送信: DRIVE STOP")
        stop_result = connection.send_line("DRIVE STOP")
        print(stop_result.message)
        check.stop_sent = stop_result.success
        wait_until(connection, 2.0, check, lambda: check.stop_response_received)

        if check.final_result() != "success" and not check.error_message:
            check.error_message = "一部の項目を確認できませんでした"
        check.print_summary()
        if args.save:
            save_result(check)
        return 0 if check.final_result() == "success" else 2
    finally:
        connection.send_line("DRIVE STOP")
        connection.disconnect()
        print("安全のため DRIVE STOP を送信して接続を閉じました。")


def save_result(check: QuickHardwareCheck) -> None:
    json_path, txt_path = HardwareCheckLogger(PROJECT_ROOT).save(check.to_result())
    print(f"JSON保存: {json_path}")
    print(f"TXT保存: {txt_path}")


if __name__ == "__main__":
    raise SystemExit(main())
