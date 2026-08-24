from __future__ import annotations

import re


PATTERNS: list[tuple[str, str]] = [
    (r"^\s*#\s*define\s+MOTOR_OUTPUT_ENABLED\s+1\b", "MOTOR_OUTPUT_ENABLED 1 が含まれています。実モータ接続時はモータが動く可能性があります。"),
    (r"^\s*#\s*define\s+USE_REAL_IMU\s+1\b", "USE_REAL_IMU 1 が含まれています。実IMUを使う設定です。"),
    (r"^\s*#\s*define\s+USE_REAL_LIDAR\s+1\b", "USE_REAL_LIDAR 1 が含まれています。実LiDARを使う設定です。"),
    (r"\banalogWrite\s*\(", "analogWrite() が含まれています。PWM出力を行う可能性があります。"),
    (r"\bledcWrite\s*\(", "ledcWrite() が含まれています。ESP32 PWM出力を行う可能性があります。"),
    (r"\bdigitalWrite\s*\(", "digitalWrite() が含まれています。GPIO出力を変更する可能性があります。"),
    (r"\bpinMode\s*\(", "pinMode() が含まれています。GPIOモードを変更する可能性があります。"),
]


def scan_firmware_text(text: str) -> list[str]:
    warnings: list[str] = []
    for pattern, message in PATTERNS:
        if re.search(pattern, text, flags=re.MULTILINE):
            warnings.append(message)
    return warnings
