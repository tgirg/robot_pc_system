from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from four_wheel_steer_model import calculate_4wis_state, load_vehicle_config, telemetry_from_line  # noqa: E402
from four_wheel_motion_check import format_4wis_motion_check_report, run_4wis_motion_checks  # noqa: E402
from fake_v29_esp32 import FakeV29ESP32  # noqa: E402
from simulation.robot_simulator import RobotSimulator  # noqa: E402
from simulation_controller import keyboard_state_from_keys, normalize_axis  # noqa: E402
from steer_view_geometry import robot_angle_to_screen_vector  # noqa: E402
from v29_send_inspection import inspect_v29_send_line  # noqa: E402
from v29_drive_adapter import (  # noqa: E402
    V29DriveAdapter,
    build_arm_line,
    build_config_line,
    build_disarm_line,
    load_controller_mapping,
)


def test_dashboard_4wis_forward_angles_are_straight() -> None:
    config = load_vehicle_config(ROOT)
    state = calculate_4wis_state(0.6, 0.0, 0.0, config, [0.0, 0.0, 0.0, 0.0])

    assert [round(angle, 1) for angle in state.angles_deg] == [0.0, 0.0, 0.0, 0.0]
    assert all(pwm is not None and pwm > 0 for pwm in state.pwm)


def test_dashboard_4wis_parses_v29_telemetry() -> None:
    config = load_vehicle_config(ROOT)
    line = json.dumps(
        {
            "v": 1,
            "type": "telemetry",
            "servo_deg": [10.0, -10.0, 20.0, -20.0],
            "wheel_rpm": [1.0, 2.0, 3.0, 4.0],
            "motor_pwm": [11, 22, 33, 44],
        }
    )

    state = telemetry_from_line(line, "test", config, [0.0, 0.0, 0.0, 0.0])

    assert state is not None
    assert state.angles_deg == [10.0, -10.0, 20.0, -20.0]
    assert state.pwm == [11, 22, 33, 44]
    assert state.source == "test telemetry"


def test_dashboard_4wis_telemetry_preserves_signed_motion() -> None:
    config = load_vehicle_config(ROOT)
    line = json.dumps(
        {
            "v": 1,
            "type": "telemetry",
            "servo_deg": [0.0, 0.0, 0.0, 0.0],
            "wheel_rpm": [-1.0, -2.0, -3.0, -4.0],
            "motor_pwm": [-11, -22, -33, -44],
        }
    )

    state = telemetry_from_line(line, "test", config, [0.0, 0.0, 0.0, 0.0])

    assert state is not None
    assert all(speed < 0.0 for speed in state.speeds_mps)


def test_dashboard_simulation_controller_forward_and_strafe_motion() -> None:
    simulator = RobotSimulator(robot_speed_mm_s=1000.0, turn_speed_deg_s=90.0)
    simulator.apply_controller_input(1.0, 0.0, 0.0)
    simulator.step(1.0)
    assert simulator.state.x_mm > 900.0
    assert abs(simulator.state.y_mm) < 1.0

    simulator.reset()
    simulator.apply_controller_input(0.0, 1.0, 0.0)
    simulator.step(1.0)
    assert simulator.state.y_mm > 900.0
    assert abs(simulator.state.x_mm) < 1.0


def test_dashboard_simulation_controller_axis_deadzone() -> None:
    assert normalize_axis(0.05, invert=False, deadzone=0.12) == 0.0
    assert normalize_axis(-0.5, invert=True, deadzone=0.12) > 0.0


def test_dashboard_simulation_keyboard_wasd_qe_mapping() -> None:
    state = keyboard_state_from_keys({"w", "a", "q"}, speed=0.5, turn=0.25)
    assert state.connected is True
    assert state.name == "Keyboard"
    assert state.vx == 0.5
    assert state.vy == 0.5
    assert state.omega == 0.25

    stopped = keyboard_state_from_keys({"w", "s", "q", "e"}, speed=0.5, turn=0.25)
    assert stopped.vx == 0.0
    assert stopped.omega == 0.0

    turn_left = keyboard_state_from_keys({"left"}, speed=0.5, turn=0.25)
    turn_right = keyboard_state_from_keys({"right"}, speed=0.5, turn=0.25)
    assert turn_left.vy == 0.0
    assert turn_left.omega == 0.25
    assert turn_right.vy == 0.0
    assert turn_right.omega == -0.25


def test_dashboard_v29_adapter_builds_low_power_forward_drive() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    output = adapter.build_drive(1, 1.0, 0.0, 0.0, armed=True, max_pwm=120)
    message = json.loads(output.line)

    assert message["type"] == "drive"
    assert message["seq"] == 1
    assert message["armed"] is True
    assert message["control"] == "pwm"
    assert message["steer_deg"] == [0.0, 0.0, 0.0, 0.0]
    assert max(abs(value) for value in message["drive_target"]) <= 120


def test_dashboard_v29_adapter_reverses_drive_for_backward() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    output = adapter.build_drive(1, -1.0, 0.0, 0.0, armed=True, max_pwm=120)
    message = json.loads(output.line)

    assert message["steer_deg"] == [0.0, 0.0, 0.0, 0.0]
    assert all(value < 0 for value in message["drive_target"])
    assert all(speed < 0.0 for speed in output.telemetry.speeds_mps)


def test_dashboard_v29_adapter_pivot_uses_tangent_posture() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), load_controller_mapping(ROOT))
    output = adapter.build_drive(1, 0.0, 0.0, 1.0, armed=True, max_pwm=80)
    message = json.loads(output.line)

    assert message["steer_deg"] == [-45.0, 45.0, 45.0, -45.0]
    assert message["drive_target"] == [80.0, -80.0, -80.0, 80.0]


def test_current_r2_controller_axis_and_pivot_corrections_are_explicit() -> None:
    mapping = load_controller_mapping(ROOT)
    config = load_vehicle_config(ROOT)

    assert mapping["logical_front"] == "REAR"
    assert mapping["invert_vy"] is False
    assert mapping["invert_omega"] is True
    assert mapping["pivot_motor_direction_inverted"] == [True, True, False, False]
    assert config["motion"]["mixed_omega_inverted"] is True


def test_dashboard_v29_adapter_multi_axis_input_uses_vector_mix() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    output = adapter.build_drive(1, 0.30, 0.60, -0.60, armed=True, max_pwm=120)
    message = json.loads(output.line)

    assert output.telemetry.detail.startswith("MIX")
    assert [round(angle, 1) for angle in message["steer_deg"]] == [-71.2, 52.0, 19.4, -8.7]
    assert max(abs(value) for value in message["drive_target"]) <= 120.0
    assert [value > 0 for value in message["drive_target"]] == [False, True, False, True]


def test_dashboard_v29_adapter_right_strafe_turn_uses_arc_limited_mix() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    output = adapter.build_drive(1, 0.0, -0.60, 0.60, armed=True, max_pwm=120)
    message = json.loads(output.line)

    assert output.telemetry.detail.startswith("ARC")
    assert [round(angle, 1) for angle in message["steer_deg"]] == [-73.8, -106.2, -55.3, -124.7]
    assert all(value > 0 for value in message["drive_target"])
    assert [round(value) for value in message["drive_target"]] == [120, 120, 74, 79]


def test_dashboard_v29_adapter_forward_turn_uses_arc_limited_mix() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    output = adapter.build_drive(1, 0.60, 0.0, 0.60, armed=True, max_pwm=120)
    message = json.loads(output.line)

    assert output.telemetry.detail.startswith("ARC")
    assert [round(angle, 1) for angle in message["steer_deg"]] == [-16.2, -34.7, 16.2, 34.7]
    assert all(value > 0 for value in message["drive_target"])
    assert [round(value) for value in message["drive_target"]] == [120, 72, 120, 79]


def test_dashboard_4wis_motion_pattern_check_passes() -> None:
    report = run_4wis_motion_checks(
        load_vehicle_config(ROOT),
        {"linear_scale": 0.12, "angular_scale": 0.35},
        max_pwm=120,
    )
    text = format_4wis_motion_check_report(report)

    assert report.passed is True
    assert report.passed_count == len(report.results)
    assert "4WIS動作パターンチェック: PASS" in text
    assert any(result.name == "右移動+左旋回" and result.mode == "ARC" for result in report.results)
    assert any(result.name == "斜め+旋回" and result.mode == "MIX" for result in report.results)


def test_dashboard_v29_adapter_arm_and_disarm_lines() -> None:
    assert json.loads(build_arm_line("normal")) == {"v": 1, "type": "arm", "mode": "normal"}
    assert json.loads(build_disarm_line()) == {"v": 1, "type": "disarm"}


def test_fake_v29_esp32_arm_drive_fault_flow() -> None:
    fake = FakeV29ESP32()

    arm = fake.process_line(build_arm_line("normal"))
    arm_ack = json.loads(arm.response_lines[0])
    assert arm.success is True
    assert arm_ack["type"] == "arm_ack"
    assert arm_ack["armed"] is True

    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    drive = adapter.build_drive(1, 0.60, 0.0, 0.60, armed=True, max_pwm=120)
    response = fake.process_line(drive.line)
    telemetry = json.loads(response.response_lines[0])

    assert response.success is True
    assert telemetry["type"] == "telemetry"
    assert telemetry["armed"] is True
    assert telemetry["servo_deg"] == drive.message["steer_deg"]
    assert telemetry["motor_pwm"] == [int(round(value)) for value in drive.message["drive_target"]]

    fault = json.loads(fake.build_fault_line("test fault"))
    assert fault["type"] == "fault"
    assert fault["reason"] == "test fault"


def test_fake_v29_esp32_config_and_debug_servo_flow() -> None:
    fake = FakeV29ESP32()
    config = load_vehicle_config(ROOT)

    config_response = fake.process_line(build_config_line(config))
    config_ack = json.loads(config_response.response_lines[0])
    assert config_response.success is True
    assert config_ack["type"] == "config_ack"
    assert config_ack["ok"] is True
    assert config_ack["config_revision"] == int(config["config_revision"]) + 1

    arm_response = fake.process_line(build_arm_line("debug"))
    arm_ack = json.loads(arm_response.response_lines[0])
    assert arm_response.success is True
    assert arm_ack["state"] == "DEBUG"

    debug_line = json.dumps({"v": 1, "type": "debug", "action": "servo_deg", "wheel": 0, "value": 12.0})
    debug_response = fake.process_line(debug_line)
    telemetry = json.loads(debug_response.response_lines[0])
    assert debug_response.success is True
    assert telemetry["type"] == "telemetry"
    assert telemetry["state"] == "DEBUG"
    assert telemetry["servo_deg"][0] == 12.0


def test_v29_send_inspection_formats_drive_payload() -> None:
    adapter = V29DriveAdapter(load_vehicle_config(ROOT), {"linear_scale": 0.12, "angular_scale": 0.35})
    drive = adapter.build_drive(7, 0.60, 0.0, 0.60, armed=True, max_pwm=120)

    inspection = inspect_v29_send_line("4WIS v29 drive", drive.line, status="OK", max_pwm=120)

    assert "type=drive" in inspection.summary
    assert "seq=7" in inspection.summary
    assert "max_pwm=120" in inspection.summary
    assert "steer_deg=[-16.2, -34.7, +16.2, +34.7]" in inspection.text
    assert "drive_target=[+120, +72, +120, +79]" in inspection.text
    assert '"type":"drive"' in inspection.text


def test_v29_send_inspection_formats_config_payload() -> None:
    config = load_vehicle_config(ROOT)
    line = build_config_line(config)
    message = json.loads(line)
    inspection = inspect_v29_send_line("4WIS CONFIG", line, status="OK")

    assert len(line.encode("utf-8")) < 2600
    assert "name" not in message["servos"][0]
    assert "pivot_direction_inverted" not in message["motion"]
    assert [item["physical"] for item in config["motors"]] == [1, 2, 3, 0]
    assert [item["inverted"] for item in config["motors"]] == [True, True, True, True]
    assert [item["physical"] for item in config["encoders"]] == [1, 0, 3, 2]
    assert [item["inverted"] for item in config["encoders"]] == [False, False, False, False]
    assert [item["channel"] for item in config["servos"]] == [5, 6, 7, 4]
    assert [item["center_us"] for item in config["servos"]] == [1580, 1490, 1590, 1550]
    assert "type=config" in inspection.summary
    assert f"config_revision={config['config_revision']}" in inspection.text
    assert "servo_direction_inverted=[false, false, false, false]" in inspection.text


def test_dashboard_steer_canvas_uses_robot_angle_sign() -> None:
    forward = robot_angle_to_screen_vector(0.0)
    left = robot_angle_to_screen_vector(90.0)
    right = robot_angle_to_screen_vector(-90.0)

    assert forward == (0.0, -1.0)
    assert left[0] < -0.99
    assert abs(left[1]) < 1e-9
    assert right[0] > 0.99
    assert abs(right[1]) < 1e-9
