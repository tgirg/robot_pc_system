from __future__ import annotations

import argparse

import pytest

from pc_controller.app import ControllerApp
from pc_controller.controller_input import ControllerState, correct_controller_axis


def make_args(tmp_path):
    return argparse.Namespace(
        config_dir=str(tmp_path),
        simulate=True,
        port=None,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


def test_pure_rotation_uses_tangent_pivot_posture_and_pwm_cap(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["motion"]["pivot_max_pwm"] = 80

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    full_stick_omega = float(app.config["motion"]["max_angular_speed_radps"]) * float(app.mapping["angular_scale"])
    for step in range(45):
        now_ms = step * 20
        app.tick(0.0, 0.0, full_stick_omega)

    assert app.last_telemetry is not None
    assert app.last_telemetry["servo_deg"] == [-45.0, 45.0, 45.0, -45.0]
    assert app.last_telemetry["motor_pwm"] == [-80, 80, -80, 80]


def test_pure_rotation_applies_hardware_specific_wheel_direction_correction(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["motion"]["pivot_max_pwm"] = 80
    app.mapping["pivot_motor_direction_inverted"] = [True, True, False, False]

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    full_stick_omega = float(app.config["motion"]["max_angular_speed_radps"]) * float(app.mapping["angular_scale"])
    for step in range(45):
        now_ms = step * 20
        app.tick(0.0, 0.0, full_stick_omega)

    assert app.last_telemetry is not None
    assert app.last_telemetry["servo_deg"] == [-45.0, 45.0, 45.0, -45.0]
    assert app.last_telemetry["motor_pwm"] == [80, -80, -80, 80]


def test_mixed_forward_rotation_does_not_exceed_forward_pwm(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    app.tick(0.15, 0.0, 0.0)
    assert app.last_telemetry is not None
    forward_pwm = max(abs(value) for value in app.last_telemetry["motor_pwm"])

    for step in range(1, 6):
        now_ms = step * 20
        app.tick(0.15, 0.0, 0.30)

    mixed_pwm = max(abs(value) for value in app.last_telemetry["motor_pwm"])
    assert mixed_pwm <= forward_pwm


def test_mixed_forward_rotation_limits_tight_arc_angle(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    for step in range(40):
        now_ms = step * 20
        app.tick(0.108, 0.0, 0.84, steer_input=0.6)

    assert app.last_telemetry is not None
    assert [round(value, 1) for value in app.last_telemetry["servo_deg"]] == [34.7, 16.2, -34.7, -16.2]
    assert app.last_telemetry["motor_pwm"][0] < app.last_telemetry["motor_pwm"][1]
    assert app.last_telemetry["motor_pwm"][2] < app.last_telemetry["motor_pwm"][3]


def test_low_forward_input_with_rotation_stays_mixed_not_pivot(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["motion"]["translation_deadzone"] = 0.12
    app.mapping["linear_scale"] = 0.12

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    for step in range(12):
        now_ms = step * 20
        app.tick(0.10, 0.0, -0.05, steer_input=-0.05)

    assert app.last_telemetry is not None
    assert app.last_telemetry["servo_deg"][0] < 0.0
    assert app.last_telemetry["servo_deg"][2] > 0.0
    assert app.last_telemetry["motor_pwm"][0] > 0
    assert app.last_telemetry["motor_pwm"][2] > 0


def test_mixed_forward_rotation_uses_inner_outer_pwm(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    for step in range(12):
        now_ms = step * 50
        app.tick(0.20, 0.0, 0.30, steer_input=1.0)

    assert app.last_telemetry is not None
    pwm = app.last_telemetry["motor_pwm"]
    assert pwm == [83, 120, 83, 120]


def test_pid_rpm_targets_are_clamped(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["pid_enabled"] = True
    app.config["motion"]["pid_max_target_rpm"] = 50.0

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    app.tick(1.5, 0.0, 0.0)

    assert app.last_telemetry is not None
    assert max(abs(value) for value in app.last_telemetry["motor_pwm"]) <= 250


def test_open_loop_pwm_targets_are_clamped(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["pid_enabled"] = False
    app.config["motion"]["open_loop_max_pwm"] = 90

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    app.tick(1.5, 0.0, 0.0)

    assert app.last_telemetry is not None
    assert max(abs(value) for value in app.last_telemetry["motor_pwm"]) <= 90


def test_open_loop_max_pwm_sets_full_forward_stick_pwm(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["pid_enabled"] = False
    app.config["motion"]["open_loop_max_pwm"] = 300
    app.mapping["linear_scale"] = 0.12

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    max_linear = float(app.config["motion"]["max_linear_speed_mps"])
    for step in range(12):
        now_ms = step * 20
        app.tick(max_linear * 0.12, 0.0, 0.0)

    assert app.last_telemetry is not None
    assert app.last_telemetry["motor_pwm"] == [300, 300, 300, 300]


def test_rear_logical_front_rotates_translation_without_reversing_omega(tmp_path) -> None:
    app = ControllerApp(make_args(tmp_path))
    app.mapping["logical_front"] = "REAR"
    app.safety.apply_config()
    app.safety.arm(app._now_ms())

    app.tick_controller(
        ControllerState(
            connected=True,
            name="test",
            vx=0.5,
            vy=-0.25,
            omega=0.5,
        )
    )

    max_linear = float(app.config["motion"]["max_linear_speed_mps"])
    max_angular = float(app.config["motion"]["max_angular_speed_radps"])
    assert app.last_motion_request == pytest.approx(
        (
            -0.5 * max_linear * float(app.mapping["linear_scale"]),
            0.25 * max_linear * float(app.mapping["linear_scale"]),
            0.5 * max_angular * float(app.mapping["angular_scale"]),
        )
    )


def test_current_rear_front_right_turn_uses_old_right_wheels_as_inner(tmp_path) -> None:
    app = ControllerApp(make_args(tmp_path))
    app.config["motion"]["mixed_omega_inverted"] = True
    app.mapping.update(
        {
            "invert_vx": True,
            "invert_omega": True,
            "logical_front": "REAR",
            "pivot_motor_direction_inverted": [True, True, False, False],
        }
    )
    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    deadzone = float(app.mapping["deadzone"])
    forward = correct_controller_axis(-1.0, bool(app.mapping["invert_vx"]), deadzone)
    turn_right = correct_controller_axis(1.0, bool(app.mapping["invert_omega"]), deadzone)
    state = ControllerState(connected=True, name="PS4 test", vx=forward, omega=turn_right)
    for step in range(45):
        now_ms = step * 20
        app.tick_controller(state)

    assert app.last_telemetry is not None
    pwm = [abs(int(value)) for value in app.last_telemetry["motor_pwm"]]
    # Physical driving showed mixed-turn yaw was opposite to pure-pivot yaw.
    # Keep the pivot correction and reverse only mixed yaw; old FR/RR are inner.
    assert pwm[1] < pwm[0]
    assert pwm[3] < pwm[2]


def test_current_rear_front_right_pivot_reverses_all_previous_wheel_signs(tmp_path) -> None:
    app = ControllerApp(make_args(tmp_path))
    app.config["motion"]["pivot_max_pwm"] = 80
    app.config["motion"]["mixed_omega_inverted"] = True
    app.mapping.update(
        {
            "invert_omega": True,
            "logical_front": "REAR",
            "pivot_motor_direction_inverted": [True, True, False, False],
        }
    )
    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    deadzone = float(app.mapping["deadzone"])
    turn_right = correct_controller_axis(1.0, bool(app.mapping["invert_omega"]), deadzone)
    state = ControllerState(connected=True, name="PS4 test", omega=turn_right)
    for step in range(45):
        now_ms = step * 20
        app.tick_controller(state)

    assert app.last_telemetry is not None
    assert app.last_telemetry["motor_pwm"] == [-80, 80, 80, -80]


def test_invalid_logical_front_fails_safe_before_motion(tmp_path) -> None:
    app = ControllerApp(make_args(tmp_path))
    app.mapping["logical_front"] = "UPSIDE_DOWN"
    app.safety.apply_config()
    app.safety.arm(app._now_ms())

    app.tick_controller(ControllerState(connected=True, name="test", vx=1.0))

    assert app.safety.armed is False
    assert app.safety.state.value == "SAFE"
    assert app.safety.fault == "unsupported logical front: UPSIDE_DOWN"
    assert app.last_motion_request == (0.0, 0.0, 0.0)


def test_pid_pivot_rpm_targets_are_clamped_separately(tmp_path) -> None:
    args = make_args(tmp_path)
    app = ControllerApp(args)
    app.config["pid_enabled"] = True
    app.config["motion"]["pid_max_target_rpm"] = 120.0
    app.config["motion"]["pid_pivot_max_target_rpm"] = 40.0

    now_ms = 0
    app._now_ms = lambda: now_ms  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(now_ms)

    for step in range(45):
        now_ms = step * 20
        app.tick(0.0, 0.0, 0.8)

    assert app.last_telemetry is not None
    assert max(abs(value) for value in app.last_telemetry["motor_pwm"]) <= 200
