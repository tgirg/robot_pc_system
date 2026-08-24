from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_calibration_model import build_calibration_diagnostic_snapshot
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import encode_message, hello_message


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _args(config_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir), simulate=False, fake_esp32=True, fake_trace=False,
        port=None, node_role="drive", node_id=None, discovery_timeout=0.1,
        reconnect_interval=1.0, reconnect_handshake_timeout=0.5, auto_reconnect=True,
        once=False, duration=None, joystick=False, list_controllers=False,
        debug_controller=None, rpm_monitor=False, rpm_monitor_hz=5.0,
    )


def _snapshot(tmp_path: Path):
    ensure_config_files(tmp_path)
    clock = ManualClock()
    controller = ControllerApp(_args(tmp_path), now_ms=clock)
    assert controller.serial is not None
    controller.safety.apply_config()
    controller.serial.write(encode_message(hello_message()))
    controller.serial.write(encode_message(controller.config))
    controller._read_serial_messages()
    return build_robot_dashboard_snapshot(
        controller,
        RobotId.R2,
        now_ms=clock.ms,
        node_requirements=(NodeRequirement("mcb44_drive_main", "drive", True),),
    )


def test_model_audits_controller_config_without_pending_or_output(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_snapshot(tmp_path))

    assert diagnostic.robot_id == "R2"
    assert diagnostic.workflow_state == "READ_ONLY_AUDIT"
    assert diagnostic.controller_api_state == "REQUIRES_SAFETY_GOVERNED_CALIBRATION_API"
    assert diagnostic.output_state == "BLOCKED_NO_CONTROLLER_API"
    assert len(diagnostic.servos) == 4
    assert [servo.logical_name for servo in diagnostic.servos] == ["FL", "FR", "RL", "RR"]
    assert [servo.channel for servo in diagnostic.servos] == [6, 5, 7, 4]
    assert [servo.current_center_us for servo in diagnostic.servos] == [1490, 1580, 1590, 1550]
    assert all(servo.min_us == 500 and servo.max_us == 2500 for servo in diagnostic.servos)
    assert all(servo.min_angle_deg == -135.0 and servo.max_angle_deg == 135.0 for servo in diagnostic.servos)
    assert all(servo.current_trim_deg == 0.0 for servo in diagnostic.servos)
    assert all(servo.direction_inverted is True for servo in diagnostic.servos)
    assert all(servo.current_command_angle_deg is None for servo in diagnostic.servos)
    assert all(servo.observed_angle_deg is None for servo in diagnostic.servos)
    assert all(servo.calibrated is False for servo in diagnostic.servos)
    assert all(servo.pending_center_us is None and servo.pending_trim_deg is None for servo in diagnostic.servos)
    assert all(servo.saved_center_us == servo.current_center_us for servo in diagnostic.servos)
    assert all(servo.saved_trim_deg == servo.current_trim_deg for servo in diagnostic.servos)
    assert all(servo.validation == "CONFIG_ONLY_VALID" for servo in diagnostic.servos)
    assert all(servo.revert_state == "NO_PENDING_CHANGE" for servo in diagnostic.servos)
    assert all(servo.apply_state == "BLOCKED_NO_CONTROLLER_API" for servo in diagnostic.servos)


def test_unbound_robot_has_no_calibration_rows(tmp_path: Path) -> None:
    r2 = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms)
    diagnostic = build_calibration_diagnostic_snapshot(fleet.selected)

    assert diagnostic.robot_id == "R1"
    assert diagnostic.workflow_state == "UNBOUND"
    assert diagnostic.controller_api_state == "UNAVAILABLE"
    assert diagnostic.output_state == "BLOCKED"
    assert diagnostic.servos == ()


def test_config_validation_is_not_physical_calibration_or_apply_authority(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    wheels = (replace(robot.wheels[0], servo_center_us=3000),) + robot.wheels[1:]
    diagnostic = build_calibration_diagnostic_snapshot(replace(robot, wheels=wheels, armed=True))

    assert diagnostic.servos[0].validation == "CONFIG_INVALID"
    assert diagnostic.servos[0].apply_state == "BLOCKED_NO_CONTROLLER_API"
    assert diagnostic.armed is True
