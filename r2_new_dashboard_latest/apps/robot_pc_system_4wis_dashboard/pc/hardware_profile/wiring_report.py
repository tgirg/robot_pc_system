from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .hardware_profile import HardwareProfile, load_hardware_profile


def generate_wiring_report(profile: HardwareProfile | None = None) -> dict[str, Any]:
    profile = profile or load_hardware_profile()
    data = profile.data
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "timestamp": timestamp,
        "title": "ロボットPC ハードウェア配線表",
        "safety": {
            "motor_output_enabled": "0",
            "use_real_imu": "0",
            "use_real_lidar": "0",
            "note": "この配線表は構成メモです。実モータ出力や実センサ読み取りを有効化しません。",
        },
        "board": data.get("board", {}),
        "wiring_table": _build_wiring_rows(data),
        "check_sheet": _build_check_sheet(data),
        "profile_summary": profile.to_summary_text(),
    }


def save_wiring_report(project_root: Path, profile: HardwareProfile | None = None) -> tuple[Path, Path, dict[str, Any]]:
    report = generate_wiring_report(profile)
    output_dir = project_root / "logs" / "wiring_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"wiring_report_{stamp}.json"
    txt_path = output_dir / f"wiring_report_{stamp}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(format_wiring_report_text(report), encoding="utf-8")
    (output_dir / "latest_wiring_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest_wiring_report.txt").write_text(format_wiring_report_text(report), encoding="utf-8")
    return txt_path, json_path, report


def format_wiring_report_text(report: dict[str, Any]) -> str:
    lines = [
        report.get("title", "ロボットPC ハードウェア配線表"),
        f"作成時刻: {report.get('timestamp', '-')}",
        "",
        "安全設定:",
    ]
    safety = report.get("safety", {})
    lines.extend(
        [
            f"- MOTOR_OUTPUT_ENABLED: {safety.get('motor_output_enabled', '0')}",
            f"- USE_REAL_IMU: {safety.get('use_real_imu', '0')}",
            f"- USE_REAL_LIDAR: {safety.get('use_real_lidar', '0')}",
            f"- 注意: {safety.get('note', '')}",
            "",
            "ボード:",
        ]
    )
    board = report.get("board", {})
    for key in ["name", "fqbn", "port", "baudrate"]:
        lines.append(f"- {key}: {board.get(key, '-')}")
    lines.extend(["", "配線表:"])
    for row in report.get("wiring_table", []):
        lines.append(
            f"- {row.get('device', '-')} / {row.get('signal', '-')} / "
            f"ESP32ピン: {row.get('esp32_pin', '-')} / 電圧: {row.get('voltage', '-')} / "
            f"メモ: {row.get('notes', '-')}"
        )
    lines.extend(["", "接続チェックシート:"])
    for item in report.get("check_sheet", []):
        lines.append(f"[ ] {item}")
    lines.extend(["", "構成サマリー:", report.get("profile_summary", "")])
    return "\n".join(lines) + "\n"


def _build_wiring_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    imu = data.get("imu", {})
    rows.extend(
        [
            _row("IMU", "SDA", imu.get("sda_pin"), imu.get("voltage"), imu.get("notes")),
            _row("IMU", "SCL", imu.get("scl_pin"), imu.get("voltage"), imu.get("notes")),
        ]
    )
    lidar = data.get("lidar", {})
    rows.extend(
        [
            _row("LiDAR", "UART RX", lidar.get("uart_rx_pin"), lidar.get("voltage"), lidar.get("notes")),
            _row("LiDAR", "UART TX", lidar.get("uart_tx_pin"), lidar.get("voltage"), lidar.get("notes")),
            _row("LiDAR", "I2C SDA", lidar.get("i2c_sda_pin"), lidar.get("voltage"), lidar.get("notes")),
            _row("LiDAR", "I2C SCL", lidar.get("i2c_scl_pin"), lidar.get("voltage"), lidar.get("notes")),
        ]
    )
    motor = data.get("motor_driver", {})
    rows.extend(
        [
            _row("モータドライバ", "Left PWM", motor.get("left_pwm_pin"), motor.get("voltage_logic"), motor.get("notes")),
            _row("モータドライバ", "Left DIR", motor.get("left_dir_pin"), motor.get("voltage_logic"), motor.get("notes")),
            _row("モータドライバ", "Right PWM", motor.get("right_pwm_pin"), motor.get("voltage_logic"), motor.get("notes")),
            _row("モータドライバ", "Right DIR", motor.get("right_dir_pin"), motor.get("voltage_logic"), motor.get("notes")),
            _row("モータドライバ", "STBY", motor.get("standby_pin"), motor.get("voltage_logic"), motor.get("notes")),
        ]
    )
    encoder = data.get("encoder", {})
    rows.extend(
        [
            _row("エンコーダ", "Left A", encoder.get("left_a_pin"), encoder.get("voltage", "-"), encoder.get("notes")),
            _row("エンコーダ", "Left B", encoder.get("left_b_pin"), encoder.get("voltage", "-"), encoder.get("notes")),
            _row("エンコーダ", "Right A", encoder.get("right_a_pin"), encoder.get("voltage", "-"), encoder.get("notes")),
            _row("エンコーダ", "Right B", encoder.get("right_b_pin"), encoder.get("voltage", "-"), encoder.get("notes")),
        ]
    )
    actuator = data.get("actuator", {})
    rows.append(_row("アクチュエータ", actuator.get("type", "信号"), "-", "-", actuator.get("notes")))
    return rows


def _build_check_sheet(data: dict[str, Any]) -> list[str]:
    return [
        "ESP32のUSB接続を確認した",
        "GND共通を確認した",
        "IMUの電圧と通信方式を確認した",
        "LiDARの電圧と通信方式を確認した",
        "モータドライバのモータ電源とロジック電源を確認した",
        "エンコーダのA/B相ピンを確認した",
        "配線写真を保存した",
        "Arduino IDEのシリアルモニタを閉じた",
        "MOTOR_OUTPUT_ENABLED 0 のままであることを確認した",
        "USE_REAL_IMU 0 のままであることを確認した",
        "USE_REAL_LIDAR 0 のままであることを確認した",
        f"ボードFQBNを確認した: {data.get('board', {}).get('fqbn', '-')}",
        f"COMポートを確認した: {data.get('board', {}).get('port', '-')}",
    ]


def _row(device: str, signal: str, pin: Any, voltage: Any, notes: Any) -> dict[str, Any]:
    return {
        "device": device,
        "signal": signal,
        "esp32_pin": "-" if pin in (None, "") else pin,
        "voltage": "-" if voltage in (None, "") else voltage,
        "notes": "-" if notes in (None, "") else notes,
    }
