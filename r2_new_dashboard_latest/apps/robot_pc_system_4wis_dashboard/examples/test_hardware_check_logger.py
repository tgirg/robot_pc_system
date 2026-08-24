from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from hardware_check import HardwareCheckLogger, HardwareCheckResult  # noqa: E402


def main() -> int:
    result = HardwareCheckResult(
        timestamp="2026-07-03 15:30:12",
        selected_com_port="COM_TEST",
        baudrate=115200,
        esp32_connected=True,
        status_received=True,
        imu_received=True,
        imu_status="dummy",
        lidar_received=True,
        lidar_status="dummy",
        encoder_received=True,
        motor_dummy_received=True,
        test_command_sent=True,
        test_response_received=True,
        stop_sent=True,
        stop_response_received=True,
        final_result="success",
        raw_lines=[
            "STATUS,OK",
            "IMU_STATUS,DUMMY",
            "LIDAR_STATUS,DUMMY",
            "ENC,0,0",
            "MOTOR_DUMMY,50,50",
            "MOTOR_DUMMY,0,0",
        ],
    )
    json_path, txt_path = HardwareCheckLogger(PROJECT_ROOT).save(result)
    ok = json_path.exists() and txt_path.exists()
    print(f"JSON保存: {json_path}")
    print(f"TXT保存: {txt_path}")
    print("結果: OK" if ok else "結果: NG")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
