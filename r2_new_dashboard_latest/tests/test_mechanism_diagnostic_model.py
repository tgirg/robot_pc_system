from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_mechanism_model import build_mechanism_diagnostic_snapshot
from pc_controller.gui_model import (
    NodeDisplayState,
    NodeSnapshot,
    build_fleet_dashboard_snapshot,
    build_robot_dashboard_snapshot,
)
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import encode_message, hello_message


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


def _ready_disarmed_snapshot(tmp_path: Path):
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


def test_current_drive_only_snapshot_reports_no_non_drive_inventory(tmp_path: Path) -> None:
    diagnostic = build_mechanism_diagnostic_snapshot(_ready_disarmed_snapshot(tmp_path))

    assert diagnostic.robot_id == "R2"
    assert diagnostic.inventory_state == "NOT_CONFIGURED"
    assert diagnostic.unmapped_nodes == ()
    assert diagnostic.excluded_drive_nodes == 1
    assert diagnostic.excluded_sensor_nodes == 0
    assert "steering servos remain in Drive Diagnostic" in diagnostic.inventory_summary


def test_unbound_robot_does_not_invent_mechanisms(tmp_path: Path) -> None:
    r2 = _ready_disarmed_snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms)
    diagnostic = build_mechanism_diagnostic_snapshot(fleet.selected)

    assert diagnostic.robot_id == "R1"
    assert diagnostic.configured is False
    assert diagnostic.inventory_state == "UNBOUND"
    assert diagnostic.unmapped_nodes == ()


def test_sensor_role_is_reserved_for_sensor_diagnostic(tmp_path: Path) -> None:
    robot = _ready_disarmed_snapshot(tmp_path)
    sensor_node = NodeSnapshot(
        "sensor_node_candidate",
        "sensor",
        False,
        NodeDisplayState.PRESENT,
        ("virtual://sensor",),
    )
    robot = replace(robot, nodes=robot.nodes + (sensor_node,))
    diagnostic = build_mechanism_diagnostic_snapshot(robot)

    assert diagnostic.inventory_state == "NOT_CONFIGURED"
    assert diagnostic.unmapped_nodes == ()
    assert diagnostic.excluded_drive_nodes == 1
    assert diagnostic.excluded_sensor_nodes == 1


def test_non_drive_node_stays_unmapped_without_fabricated_values(tmp_path: Path) -> None:
    robot = _ready_disarmed_snapshot(tmp_path)
    tool_node = NodeSnapshot(
        "tool_node_candidate",
        "tool",
        False,
        NodeDisplayState.PRESENT,
        ("virtual://tool",),
    )
    robot = replace(robot, nodes=robot.nodes + (tool_node,))
    diagnostic = build_mechanism_diagnostic_snapshot(robot)

    assert diagnostic.inventory_state == "NODE_MAPPING_REQUIRED"
    assert len(diagnostic.unmapped_nodes) == 1
    node = diagnostic.unmapped_nodes[0]
    assert node.node_id == "tool_node_candidate"
    assert node.mapping_state == "UNMAPPED"
    assert node.command is None
    assert node.state is None
    assert node.limit is None
    assert node.telemetry is None
    assert node.fault is None


def test_global_safety_fault_is_preserved_but_not_assigned_to_unmapped_node(tmp_path: Path) -> None:
    robot = _ready_disarmed_snapshot(tmp_path)
    tool_node = NodeSnapshot(
        "tool_node_candidate",
        "actuator",
        True,
        NodeDisplayState.MISSING,
        (),
    )
    robot = replace(robot, nodes=robot.nodes + (tool_node,), fault="latched safety fault", ready=False)
    diagnostic = build_mechanism_diagnostic_snapshot(robot)

    assert diagnostic.fault == "latched safety fault"
    assert diagnostic.unmapped_nodes[0].fault is None
