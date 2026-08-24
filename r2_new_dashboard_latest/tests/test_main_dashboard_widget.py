from __future__ import annotations

import argparse
import json
import os
import sys
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
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import arm_message, encode_message, hello_message

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.main_dashboard_widget import MainDashboardWidget  # noqa: E402


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


def _ready_fake_app(config_dir: Path) -> tuple[ControllerApp, ManualClock]:
    ensure_config_files(config_dir)
    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(json.dumps(vehicle, indent=2) + "\n", encoding="utf-8")

    clock = ManualClock()
    app = ControllerApp(_args(config_dir), now_ms=clock)
    assert app.serial is not None
    app.safety.apply_config()
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    assert app.safety.config_accepted is True
    return app, clock


def _arm_and_drive(app: ControllerApp, clock: ManualClock) -> None:
    assert app.serial is not None
    clock.ms += 10
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()
    clock.ms += 20
    app.tick(0.3, 0.4, -0.2)


def test_offscreen_main_dashboard_renders_fake_snapshot_and_robot_selection(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    controller, clock = _ready_fake_app(tmp_path)
    _arm_and_drive(controller, clock)
    r2 = build_robot_dashboard_snapshot(
        controller,
        RobotId.R2,
        now_ms=clock.ms,
        node_requirements=(NodeRequirement("mcb44_drive_main", "drive", True),),
    )
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=clock.ms)

    widget = MainDashboardWidget()
    widget.resize(1300, 900)
    widget.set_fleet_snapshot(fleet)
    widget.show()
    qt_app.processEvents()

    assert "R1: OFFLINE" in widget._summary_labels["R1"].text()
    assert "R2: ONLINE" in widget._summary_labels["R2"].text()
    assert "backend=FAKE_ESP32" in widget._summary_labels["R2"].text()
    assert widget.selected_robot == "R1"

    selected: list[str] = []
    widget.robot_selected.connect(selected.append)
    widget._robot_buttons["R2"].click()
    qt_app.processEvents()

    assert selected == ["R2"]
    assert widget.selected_robot == "R2"
    assert "ONLINE | NORMAL | READY | ARMED" in widget.selected_state_label.text()
    assert "backend: FAKE_ESP32" in widget.communication_label.text()
    assert widget.node_table.rowCount() == 1
    assert widget.node_table.item(0, 0).text() == "mcb44_drive_main"
    assert widget.node_table.item(0, 3).text() == "PRESENT"
    assert widget.wheel_table.rowCount() == 4
    assert widget.vector_canvas.motion == pytest.approx((0.3, 0.4, -0.2, True))
    assert "magnitude=0.50" in widget.motion_label.text()
    assert "rotation=CW" in widget.motion_label.text()

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    assert not image.isNull()
    assert image.pixelColor(5, 5).alpha() > 0
    widget.close()


def test_fault_banner_preserves_source_reason_node_and_safety_response(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    controller, clock = _ready_fake_app(tmp_path)
    _arm_and_drive(controller, clock)
    assert controller.fake_device is not None
    controller.fake_device.faults.explicit_fault = "dashboard fault detail"
    clock.ms += 20
    controller.tick(0.0, 0.0, 0.0)
    r2 = build_robot_dashboard_snapshot(controller, RobotId.R2, now_ms=clock.ms)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (r2,), now_ms=clock.ms)

    widget = MainDashboardWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    banner = widget.fault_banner.text()
    assert "FAULT" in banner
    assert "source=ESP32" in banner
    assert "node=mcb44_drive_main" in banner
    assert "reason=dashboard fault detail" in banner
    assert "Safety response=SAFE/DISARMED" in banner
    assert "SAFE | NOT_READY | FAULT" in widget.selected_state_label.text()


def test_renderer_rejects_invalid_fleet_ids(qt_app: QApplication) -> None:
    del qt_app
    widget = MainDashboardWidget()
    invalid = type("Fleet", (), {"selected_robot": "R3", "robots": ()})()
    with pytest.raises(ValueError, match="selected_robot"):
        widget.set_fleet_snapshot(invalid)
