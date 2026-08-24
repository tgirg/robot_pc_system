from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import (
    NodeDisplayState,
    NodeSnapshot,
    build_fleet_dashboard_snapshot,
    build_robot_dashboard_snapshot,
)
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import encode_message, hello_message

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.mechanism_diagnostic_widget import MechanismDiagnosticWidget  # noqa: E402


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


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


def test_widget_renders_explicit_not_configured_state(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = MechanismDiagnosticWidget()
    widget.resize(1400, 900)
    widget.set_fleet_snapshot(fleet)
    widget.show()
    qt_app.processEvents()

    assert widget.selected_robot == "R2"
    assert widget.selected_state_label.text() == "R2 | ONLINE | SAFE | READY | DISARMED"
    assert "inventory=NOT_CONFIGURED" in widget.inventory_state_label.text()
    assert "drive-role nodes excluded=1" in widget.boundary_label.text()
    assert widget.mechanism_table.rowCount() == 0
    assert "Command/state/limit/telemetry remain N/A" in widget.empty_state_label.text()

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    assert not image.isNull()
    assert image.pixelColor(5, 5).alpha() > 0
    widget.close()


def test_widget_keeps_unbound_robot_empty(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    r2 = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms)
    widget = MechanismDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.selected_robot == "R1"
    assert widget.diagnostic_snapshot is not None
    assert widget.diagnostic_snapshot.inventory_state == "UNBOUND"
    assert widget.mechanism_table.rowCount() == 0


def test_widget_labels_non_drive_node_unmapped_and_preserves_fault(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    node = NodeSnapshot(
        "candidate_tool_node",
        "tool",
        False,
        NodeDisplayState.PRESENT,
        ("virtual://tool",),
    )
    robot = replace(robot, nodes=robot.nodes + (node,), fault="mechanism safety boundary fault", ready=False)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = MechanismDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert "inventory=NODE_MAPPING_REQUIRED" in widget.inventory_state_label.text()
    assert widget.mechanism_table.rowCount() == 1
    assert widget.mechanism_table.item(0, 0).text() == "candidate_tool_node"
    assert widget.mechanism_table.item(0, 5).text() == "UNMAPPED"
    assert all(widget.mechanism_table.item(0, column).text() == "N/A" for column in range(6, 11))
    assert "FAULT | mechanism safety boundary fault" in widget.fault_banner.text()
    assert "Safety response=SAFE/DISARMED" in widget.fault_banner.text()
