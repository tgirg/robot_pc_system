from __future__ import annotations

import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROFILE: dict[str, Any] = {
    "board": {"name": "ESP32", "fqbn": "esp32:esp32:esp32", "port": "COM6", "baudrate": 115200},
    "imu": {
        "enabled": False,
        "type": "dummy",
        "communication": "dummy",
        "sda_pin": None,
        "scl_pin": None,
        "voltage": "3.3V",
        "notes": "実IMU接続前",
    },
    "lidar": {
        "enabled": False,
        "type": "dummy",
        "communication": "unknown",
        "uart_rx_pin": None,
        "uart_tx_pin": None,
        "i2c_sda_pin": None,
        "i2c_scl_pin": None,
        "voltage": "unknown",
        "notes": "実LiDARの型番確認待ち",
    },
    "motor_driver": {
        "enabled": False,
        "model": "unknown",
        "left_pwm_pin": None,
        "left_dir_pin": None,
        "right_pwm_pin": None,
        "right_dir_pin": None,
        "standby_pin": None,
        "voltage_motor": "unknown",
        "voltage_logic": "3.3V or 5V",
        "notes": "MOTOR_OUTPUT_ENABLED 0 のまま",
    },
    "encoder": {
        "enabled": False,
        "left_a_pin": None,
        "left_b_pin": None,
        "right_a_pin": None,
        "right_b_pin": None,
        "pulses_per_rev": None,
        "notes": "未接続",
    },
    "actuator": {"enabled": False, "type": "none", "notes": "アーム・ポンプ等は後で追加"},
}


class HardwareProfile:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = _deep_merge(DEFAULT_PROFILE, data or {})

    def get_board_summary(self) -> dict[str, Any]:
        return self._summary("board", type_key="name", communication_key="fqbn", voltage_key=None)

    def get_imu_summary(self) -> dict[str, Any]:
        return self._summary("imu")

    def get_lidar_summary(self) -> dict[str, Any]:
        return self._summary("lidar")

    def get_motor_summary(self) -> dict[str, Any]:
        section = self._section("motor_driver")
        pins = _pin_text(section, ["left_pwm_pin", "left_dir_pin", "right_pwm_pin", "right_dir_pin", "standby_pin"])
        return {
            "enabled": section.get("enabled", False),
            "type": section.get("model", "unknown"),
            "communication": "PWM/DIR",
            "voltage": f"motor={section.get('voltage_motor', 'unknown')} / logic={section.get('voltage_logic', 'unknown')}",
            "pins": pins,
            "notes": section.get("notes", ""),
        }

    def get_encoder_summary(self) -> dict[str, Any]:
        section = self._section("encoder")
        return {
            "enabled": section.get("enabled", False),
            "type": "quadrature",
            "communication": "GPIO割り込み",
            "voltage": section.get("voltage", "unknown"),
            "pins": _pin_text(section, ["left_a_pin", "left_b_pin", "right_a_pin", "right_b_pin"]),
            "notes": f"{section.get('notes', '')} / pulses_per_rev={section.get('pulses_per_rev', '-')}",
        }

    def get_actuator_summary(self) -> dict[str, Any]:
        return self._summary("actuator", communication_key="type", voltage_key=None)

    def to_summary_text(self) -> str:
        rows = [
            ("ボード", self.get_board_summary()),
            ("IMU", self.get_imu_summary()),
            ("LiDAR", self.get_lidar_summary()),
            ("モータドライバ", self.get_motor_summary()),
            ("エンコーダ", self.get_encoder_summary()),
            ("アクチュエータ", self.get_actuator_summary()),
        ]
        lines = ["ハードウェア構成メモ"]
        for title, summary in rows:
            lines.append(
                f"- {title}: {'有効' if summary['enabled'] else '無効'} / "
                f"型番={summary['type']} / 通信={summary['communication']} / "
                f"電圧={summary['voltage']} / ピン={summary['pins']} / メモ={summary['notes']}"
            )
        return "\n".join(lines)

    def _section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name, {})
        return value if isinstance(value, dict) else {}

    def _summary(
        self,
        name: str,
        type_key: str = "type",
        communication_key: str = "communication",
        voltage_key: str | None = "voltage",
    ) -> dict[str, Any]:
        section = self._section(name)
        pin_keys = [key for key in section.keys() if key.endswith("_pin")]
        return {
            "enabled": section.get("enabled", name == "board"),
            "type": section.get(type_key, "unknown"),
            "communication": section.get(communication_key, "-") if communication_key else "-",
            "voltage": section.get(voltage_key, "-") if voltage_key else "-",
            "pins": _pin_text(section, pin_keys),
            "notes": section.get("notes", ""),
        }


def default_profile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "hardware_profile.yaml"


def get_safe_default_profile() -> HardwareProfile:
    return HardwareProfile(deepcopy(DEFAULT_PROFILE))


def load_hardware_profile(path: str | Path | None = None) -> HardwareProfile:
    profile_path = Path(path) if path else default_profile_path()
    if not profile_path.exists():
        return get_safe_default_profile()
    try:
        with profile_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return HardwareProfile(data if isinstance(data, dict) else {})
    except Exception:
        return get_safe_default_profile()


def save_hardware_profile(profile: HardwareProfile | dict[str, Any], path: str | Path | None = None) -> Path:
    profile_path = Path(path) if path else default_profile_path()
    data = profile.data if isinstance(profile, HardwareProfile) else HardwareProfile(profile).data
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    if profile_path.exists():
        backup = profile_path.with_suffix(f".yaml.bak_{time.strftime('%Y%m%d_%H%M%S')}")
        try:
            backup.write_text(profile_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    with profile_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
    return profile_path


def validate_hardware_profile(profile: HardwareProfile | dict[str, Any]) -> dict[str, list[str]]:
    data = profile.data if isinstance(profile, HardwareProfile) else HardwareProfile(profile).data
    errors: list[str] = []
    warnings: list[str] = []

    board = data.get("board", {})
    _require_int(board, "baudrate", "ボーレート", errors)
    for section_name, keys in {
        "imu": ["sda_pin", "scl_pin"],
        "lidar": ["uart_rx_pin", "uart_tx_pin", "i2c_sda_pin", "i2c_scl_pin"],
        "motor_driver": ["left_pwm_pin", "left_dir_pin", "right_pwm_pin", "right_dir_pin", "standby_pin"],
        "encoder": ["left_a_pin", "left_b_pin", "right_a_pin", "right_b_pin", "pulses_per_rev"],
    }.items():
        section = data.get(section_name, {})
        for key in keys:
            _optional_int(section, key, f"{section_name}.{key}", errors)

    for section_name in ["imu", "lidar"]:
        section = data.get(section_name, {})
        if section.get("enabled") and str(section.get("type", "")).lower() == "dummy":
            warnings.append(f"{section_name} が有効ですが型番が dummy です。実センサ値ではありません。")
        if section.get("enabled") and not str(section.get("voltage", "")).strip():
            errors.append(f"{section_name} を有効にする場合は電圧メモを入力してください。")

    motor = data.get("motor_driver", {})
    if motor.get("enabled"):
        warnings.append("モータドライバを有効にしても、実モータ出力はまだ無効です。MOTOR_OUTPUT_ENABLED は変更されません。")
        if not str(motor.get("voltage_motor", "")).strip():
            errors.append("motor_driver を有効にする場合はモータ電源を入力してください。")
        if not str(motor.get("voltage_logic", "")).strip():
            errors.append("motor_driver を有効にする場合はロジック電源を入力してください。")

    return {"errors": errors, "warnings": warnings}


def _require_int(section: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    value = section.get(key)
    try:
        int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} は整数で入力してください。")


def _optional_int(section: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    value = section.get(key)
    if value in (None, ""):
        return
    try:
        int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} は空欄または整数で入力してください。")


def _pin_text(section: dict[str, Any], keys: list[str]) -> str:
    if not keys:
        return "-"
    values = [f"{key}={section.get(key, '-')}" for key in keys]
    return ", ".join(values)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            result[key] = _deep_merge(value, override.get(key, {}) if isinstance(override.get(key), dict) else {})
        else:
            result[key] = override.get(key, value)
    for key, value in override.items():
        if key not in result:
            result[key] = value
    return result
