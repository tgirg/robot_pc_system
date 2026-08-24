from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import arm_message, encode_message, hello_message

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.drive_diagnostic_widget import DriveDiagnosticWidget  # noqa: E402


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


def test_drive_widget_renders_four_wheels_vectors_and_selection(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    r2 = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (r2,), now_ms=r2.timestamp_ms)
    widget = DriveDiagnosticWidget()
    widget.resize(1400, 900)
    widget.set_fleet_snapshot(fleet)
    widget.show()
    qt_app.processEvents()

    assert widget.selected_robot == "R2"
    assert "R2 | 4WIS | ONLINE | NORMAL | READY | ARMED" == widget.selected_state_label.text()
    assert "mcb44_drive_main=PRESENT" in widget.node_state_label.text()
    assert widget.wheel_table.rowCount() == 4
    assert widget.wheel_table.item(0, 1).text() == "MONITORING"
    assert widget.wheel_table.item(0, 10).text() == "ONLINE/PRESENT"
    assert widget.vector_canvas.motion == pytest.approx((0.3, 0.4, -0.2, True))
    assert widget.wheel_canvas.snapshot is widget.diagnostic_snapshot

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    assert not image.isNull()
    assert image.pixelColor(5, 5).alpha() > 0
    widget.close()


def test_drive_widget_hides_steering_for_non_4wis_snapshot(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = replace(_snapshot(tmp_path), drive_type="OMNI")
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = DriveDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.wheel_table.item(0, 6).text() == "N/A"
    assert widget.wheel_table.item(0, 7).text() == "N/A"
    assert widget.wheel_table.item(0, 9).text() == "N/A"


def test_drive_widget_keeps_safety_fault_prominent(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = replace(_snapshot(tmp_path), fault="drive diagnostic fault", ready=False, armed=False)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = DriveDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert "FAULT | drive diagnostic fault" in widget.fault_banner.text()
    assert all(widget.wheel_table.item(row, 1).text() == "SAFETY_FAULT" for row in range(4))
