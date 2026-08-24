from __future__ import annotations

from pathlib import Path

import pytest

from pc_controller.config_manager import (
    default_controller_mapping,
    default_vehicle_config,
    ensure_config_files,
    load_json,
    save_json,
    validate_vehicle_config,
)
from pc_controller.protocol import encode_message

IO_TEST_DIR = Path(__file__).resolve().parents[1] / "99_\u4f5c\u696d\u7528" / "tmp" / "test_config_io"


def test_default_config_matches_v29_hardware_map() -> None:
    config = default_vehicle_config()
    validate_vehicle_config(config)
    assert [motor["physical"] for motor in config["motors"]] == [2, 1, 3, 0]
    assert [motor["inverted"] for motor in config["motors"]] == [True, True, True, True]
    assert [encoder["physical"] for encoder in config["encoders"]] == [0, 1, 2, 3]
    assert [encoder["inverted"] for encoder in config["encoders"]] == [False, False, False, False]
    assert [servo["channel"] for servo in config["servos"]] == [6, 5, 7, 4]
    assert [servo["center_us"] for servo in config["servos"]] == [1490, 1580, 1590, 1550]
    assert [servo["direction_inverted"] for servo in config["servos"]] == [True, True, True, True]
    assert [servo["calibrated"] for servo in config["servos"]] == [False, False, False, False]
    assert config["motion"]["wheelbase_m"] == pytest.approx(0.327)
    assert config["motion"]["track_width_m"] == pytest.approx(0.327)
    assert config["motion"]["wheel_diameter_m"] == pytest.approx(0.055)
    assert config["motion"]["max_wheel_rpm"] == pytest.approx(520.0)
    assert config["motion"]["pid_max_target_rpm"] == pytest.approx(80.0)
    assert config["motion"]["pid_pivot_max_target_rpm"] == pytest.approx(60.0)
    assert config["motion"]["open_loop_max_pwm"] == 120
    assert config["motion"]["pivot_max_pwm"] == 120
    assert config["motion"]["pivot_steering_mode"] == "optimized"
    assert config["motion"]["pivot_direction_inverted"] is False
    assert config["motion"]["mixed_omega_inverted"] is False
    assert config["motion"]["mixed_steering_mode"] == "limited_arc"
    assert config["motion"]["mixed_arc_min_radius_m"] == pytest.approx(0.4)
    assert config["motion"]["coordinated_4ws_max_steer_deg"] == pytest.approx(45.0)
    assert config["motion"]["coordinated_4ws_inner_outer_speed"] is False
    assert config["motion"]["coordinated_4ws_positive_steer_turns_right"] is True
    assert config["motion"]["limit_mixed_peak_to_translation"] is True
    assert config["pid_enabled"] is False
    assert [motor["pid_enabled"] for motor in config["motors"]] == [False, False, False, False]
    assert [motor["kp"] for motor in config["motors"]] == [1.0, 1.0, 1.0, 1.0]
    assert [motor["ki"] for motor in config["motors"]] == [1.2, 1.2, 1.2, 1.2]
    assert [motor["kd"] for motor in config["motors"]] == [0.0, 0.0, 0.0, 0.0]
    assert [motor["output_min"] for motor in config["motors"]] == [-140, -140, -140, -140]
    assert [motor["output_max"] for motor in config["motors"]] == [140, 140, 140, 140]
    with pytest.raises(ValueError, match="calibrated"):
        validate_vehicle_config(config, require_armable=True)


def test_duplicate_mapping_rejected() -> None:
    config = default_vehicle_config()
    config["motors"][1]["physical"] = 0
    with pytest.raises(ValueError):
        validate_vehicle_config(config)


def test_armable_config_requires_pid_counts_when_pid_enabled() -> None:
    config = default_vehicle_config()
    config["motion"].update({"wheelbase_m": 0.4, "track_width_m": 0.4, "wheel_diameter_m": 0.1, "max_wheel_rpm": 100.0})
    config["servos"] = [dict(servo, calibrated=True) for servo in config["servos"]]
    config["pid_enabled"] = True
    with pytest.raises(ValueError):
        validate_vehicle_config(config, require_armable=True)
    for encoder in config["encoders"]:
        encoder["counts_per_wheel_rev"] = 8192
    validate_vehicle_config(config, require_armable=True)


def test_json_save_and_load() -> None:
    config = default_vehicle_config()
    path = IO_TEST_DIR / "vehicle_config.json"
    save_json(path, config)
    loaded = load_json(path, {})
    assert loaded["schema_version"] == config["schema_version"]


def test_default_config_fits_esp32_rx_buffer() -> None:
    assert len(encode_message(default_vehicle_config())) < 4096


def test_default_controller_mapping_starts_with_low_speed_scale() -> None:
    mapping = default_controller_mapping()
    assert mapping["logical_front"] == "FRONT"
    assert mapping["deadzone"] == pytest.approx(0.12)
    assert mapping["linear_scale"] == pytest.approx(0.12)
    assert mapping["angular_scale"] == pytest.approx(0.35)
    assert mapping["axis_omega"] == 2
    assert mapping["invert_vy"] is True
    assert mapping["invert_omega"] is True
    assert mapping["pivot_motor_direction_inverted"] == [False, False, False, False]
    assert mapping["arm_buttons"] == [9, 10, 0]
    assert mapping["safe_button"] == 6
    assert mapping["safe_button"] not in mapping["arm_buttons"]


def test_firmware_motor_pins_match_v29_standalone_debug_sketch() -> None:
    board_pins = (Path(__file__).resolve().parents[1] / "esp32_firmware" / "board_pins.h").read_text(encoding="utf-8")
    assert '{ "M1", 19, 14, 0 }' in board_pins
    assert '{ "M2", 27, 23, 1 }' in board_pins
    assert '{ "M3", 25, 26, 2 }' in board_pins
    assert '{ "M4", 18, 16, 3 }' in board_pins


def test_invalid_json_falls_back() -> None:
    path = IO_TEST_DIR / "bad.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad", encoding="utf-8")
    assert load_json(path, {"ok": True}) == {"ok": True}


def test_ensure_config_files_does_not_overwrite_invalid_json(tmp_path) -> None:
    vehicle = tmp_path / "vehicle_config.json"
    vehicle.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid vehicle config"):
        ensure_config_files(tmp_path)

    assert vehicle.read_text(encoding="utf-8") == "{bad"
