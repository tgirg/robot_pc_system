from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_drive_model import build_drive_diagnostic_snapshot
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import arm_message, encode_message, hello_message


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _args(config_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir),
        simulate=False,
        fake_esp32=True,
        fake_trace=False,
        port=None,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        reconnect_interval=1.0,
        reconnect_handshake_timeout=0.5,
        auto_reconnect=True,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


def _ready_driving_snapshot(tmp_path: Path):
    ensure_config_files(tmp_path)
    vehicle_path = tmp_path / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(json.dumps(vehicle, indent=2) + "\n", encoding="utf-8")

    clock = ManualClock()
    controller = ControllerApp(_args(tmp_path), now_ms=clock)
    assert controller.serial is not None
    controller.safety.apply_config()
    controller.serial.write(encode_message(hello_message()))
    controller.serial.write(encode_message(controller.config))
    controller._read_serial_messages()
    clock.ms += 10
    controller.safety.request_arm(clock.ms)
    controller.serial.write(encode_message(arm_message("normal")))
    controller._read_serial_messages()
    clock.ms += 20
    controller.tick(0.3, 0.4, -0.2)
    return build_robot_dashboard_snapshot(
        controller,
        RobotId.R2,
        now_ms=clock.ms,
        node_requirements=(NodeRequirement("mcb44_drive_main", "drive", True),),
    )


def test_drive_diagnostic_uses_only_shared_wheel_and_node_state(tmp_path: Path) -> None:
    robot = _ready_driving_snapshot(tmp_path)
    diagnostic = build_drive_diagnostic_snapshot(robot)

    assert diagnostic.robot_id == "R2"
    assert diagnostic.drive_type == "4WIS"
    assert diagnostic.steering_available is True
    assert diagnostic.drive_node_state == "PRESENT"
    assert diagnostic.drive_node_summary == "mcb44_drive_main=PRESENT"
    assert len(diagnostic.wheels) == 4
    assert all(wheel.status == "MONITORING" for wheel in diagnostic.wheels)
    assert all(wheel.node_link == "ONLINE/PRESENT" for wheel in diagnostic.wheels)
    assert all(wheel.command_control == "pwm" for wheel in diagnostic.wheels)
    assert all(wheel.command_target is not None for wheel in diagnostic.wheels)
    assert all(wheel.observed_rpm is not None for wheel in diagnostic.wheels)
    assert all(wheel.observed_pwm is not None for wheel in diagnostic.wheels)
    assert all(wheel.observed_steering_deg is not None for wheel in diagnostic.wheels)


def test_unbound_robot_remains_unknown_without_invented_wheels(tmp_path: Path) -> None:
    r2 = _ready_driving_snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms)
    diagnostic = build_drive_diagnostic_snapshot(fleet.selected)

    assert diagnostic.robot_id == "R1"
    assert diagnostic.configured is False
    assert diagnostic.drive_type == "UNKNOWN"
    assert diagnostic.drive_node_state == "UNBOUND"
    assert diagnostic.wheels == ()


def test_non_4wis_drive_does_not_render_steering_or_servo_inversion(tmp_path: Path) -> None:
    robot = _ready_driving_snapshot(tmp_path)
    robot = replace(robot, drive_type="OMNI")
    diagnostic = build_drive_diagnostic_snapshot(robot)

    assert diagnostic.steering_available is False
    assert all(wheel.commanded_steering_deg is None for wheel in diagnostic.wheels)
    assert all(wheel.observed_steering_deg is None for wheel in diagnostic.wheels)
    assert all(wheel.servo_inverted is None for wheel in diagnostic.wheels)


def test_global_safety_fault_is_not_downgraded_to_wheel_ok(tmp_path: Path) -> None:
    robot = _ready_driving_snapshot(tmp_path)
    robot = replace(robot, fault="diagnostic fault", ready=False, armed=False)
    diagnostic = build_drive_diagnostic_snapshot(robot)

    assert all(wheel.status == "SAFETY_FAULT" for wheel in diagnostic.wheels)
