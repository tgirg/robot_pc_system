from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc"))

from arduino_tools.firmware_safety_scan import scan_firmware_text


def check(name: str, text: str, expected_count: int) -> bool:
    warnings = scan_firmware_text(text)
    ok = len(warnings) == expected_count
    result = "OK" if ok else "NG"
    print(f"{result}: {name} / 警告数={len(warnings)}")
    if not ok:
        for warning in warnings:
            print(f"  - {warning}")
    return ok


def main() -> int:
    cases = [
        ("安全なコード", "void setup() { Serial.begin(115200); }\nvoid loop() {}\n", 0),
        ("MOTOR_OUTPUT_ENABLED 1", "#define MOTOR_OUTPUT_ENABLED 1\n", 1),
        ("USE_REAL_IMU 1", "#define USE_REAL_IMU 1\n", 1),
        ("USE_REAL_LIDAR 1", "#define USE_REAL_LIDAR 1\n", 1),
        ("ledcWrite", "void loop(){ ledcWrite(0, 128); }\n", 1),
        ("analogWrite", "void loop(){ analogWrite(5, 128); }\n", 1),
    ]
    success = all(check(name, text, count) for name, text, count in cases)
    print("結果: 成功" if success else "結果: 失敗")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
