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
from PySide6.QtWidgets import QApplication, QPushButton

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import encode_message, hello_message

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.calibration_diagnostic_widget import CalibrationDiagnosticWidget  # noqa: E402


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


def test_widget_renders_read_only_config_audit(qt_app: QApplication, tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.resize(1400, 900)
    widget.set_fleet_snapshot(fleet)
    widget.show()
    qt_app.processEvents()

    assert widget.selected_robot == "R2"
    assert widget.selected_state_label.text() == "R2 | ONLINE | SAFE | READY | DISARMED"
    assert "workflow=READ_ONLY_AUDIT" in widget.workflow_state_label.text()
    assert "direction workflow=READ_ONLY_AUDIT" in widget.workflow_state_label.text()
    assert "parameter workflow=READ_ONLY_AUDIT" in widget.workflow_state_label.text()
    assert "zero local pending=0" in widget.workflow_state_label.text()
    assert "angle local pending=0" in widget.workflow_state_label.text()
    assert "REQUIRES_SAFETY_GOVERNED_CALIBRATION_API" in widget.boundary_label.text()
    assert "output=BLOCKED_NO_CONTROLLER_API" in widget.boundary_label.text()
    assert widget.servo_table.rowCount() == 4
    assert widget.servo_table.item(0, 1).text() == "FL"
    assert widget.servo_table.item(0, 4).text() == "1490"
    assert widget.servo_table.item(0, 9).text() == "NONE"
    assert widget.servo_table.item(0, 11).text() == "CONFIG_ONLY_VALID"
    assert widget.servo_table.item(0, 13).text() == "BLOCKED_NO_CONTROLLER_API"
    assert widget.angle_table.rowCount() == 4
    assert widget.angle_table.item(0, 2).text() == "500 / 2500 us"
    assert widget.angle_table.item(0, 3).text() == "-135.0 / 135.0 deg"
    assert widget.angle_table.item(0, 7).text() == "NONE"
    assert widget.angle_table.item(0, 9).text() == "CONFIG_ONLY_VALID"
    assert widget.angle_table.item(0, 11).text() == "BLOCKED_NO_CONTROLLER_API"
    assert widget.angle_table.item(0, 12).text() == "REQUIRED_BEFORE_APPLY"
    assert widget.direction_adjustment_snapshot is not None
    assert widget.direction_adjustment_snapshot.validation == "SOURCE_CONFIG_VALID"
    assert widget.direction_controller_table.rowCount() == 3
    assert widget.direction_controller_table.item(0, 0).text() == "vx / forward"
    assert widget.direction_controller_table.item(0, 1).text() == "1"
    assert widget.direction_controller_table.item(0, 2).text() == "INVERTED"
    assert widget.direction_controller_table.item(0, 3).text() == "NONE"
    assert widget.direction_wheel_table.rowCount() == 4
    assert widget.direction_wheel_table.item(0, 0).text() == "FL"
    assert widget.direction_wheel_table.item(0, 1).text() == "INVERTED"
    assert "Machine convention: +X=FORWARD / +Y=LEFT / +omega=CCW" in widget.direction_preview_label.text()
    assert "saved=FRONT" in widget.direction_preview_label.text()
    assert widget.parameter_adjustment_snapshot is not None
    assert widget.parameter_adjustment_snapshot.workflow_state == "READ_ONLY_AUDIT"
    assert widget.parameter_table.rowCount() == 5
    assert widget.parameter_table.item(0, 0).text() == "controller.deadzone"
    assert widget.parameter_table.item(0, 2).text() == "0.12"
    assert widget.parameter_table.item(0, 3).text() == "NONE"
    assert widget.parameter_table.item(0, 4).text() == "0.12"
    assert "0..0.95 fraction" == widget.parameter_table.item(0, 5).text()
    assert len(widget.findChildren(QPushButton)) == 18
    assert widget.direction_stage_button.isEnabled()
    assert widget.direction_revert_button.isEnabled() is False
    assert widget.direction_apply_button.isEnabled() is False
    assert widget.direction_save_button.isEnabled() is False
    assert widget.parameter_stage_button.isEnabled()
    assert widget.parameter_revert_button.isEnabled() is False
    assert widget.parameter_apply_button.isEnabled() is False
    assert widget.parameter_save_button.isEnabled() is False
    assert widget.stage_button.isEnabled()
    assert widget.revert_button.isEnabled() is False
    assert widget.apply_button.isEnabled() is False
    assert widget.save_button.isEnabled() is False
    assert widget.angle_stage_button.isEnabled()
    assert widget.angle_revert_button.isEnabled() is False
    assert widget.angle_apply_button.isEnabled() is False
    assert widget.angle_save_button.isEnabled() is False

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    assert not image.isNull()
    assert image.pixelColor(5, 5).alpha() > 0
    widget.close()


def test_widget_keeps_unbound_robot_empty(qt_app: QApplication, tmp_path: Path) -> None:
    r2 = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.selected_robot == "R1"
    assert widget.diagnostic_snapshot is not None
    assert widget.diagnostic_snapshot.workflow_state == "UNBOUND"
    assert widget.servo_table.rowCount() == 0
    assert widget.angle_table.rowCount() == 0
    assert widget.angle_stage_button.isEnabled() is False
    assert widget.direction_controller_table.rowCount() == 3
    assert widget.direction_wheel_table.rowCount() == 0
    assert widget.direction_stage_button.isEnabled() is False
    assert widget.parameter_table.rowCount() == 5
    assert widget.parameter_table.item(0, 2).text() == "UNKNOWN"
    assert widget.parameter_stage_button.isEnabled() is False


def test_widget_preserves_fault_and_never_enables_apply(qt_app: QApplication, tmp_path: Path) -> None:
    robot = replace(_snapshot(tmp_path), fault="latched calibration boundary fault", ready=False)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert "latched calibration boundary fault" in widget.fault_banner.text()
    assert all(widget.servo_table.item(row, 13).text() == "BLOCKED_NO_CONTROLLER_API" for row in range(4))


def test_widget_stages_periodic_local_draft_and_reverts_without_output(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.servo_combo.currentData() == 0
    widget.center_edit.setText("1505")
    widget.trim_edit.setText("1.25")
    widget.stage_button.click()
    qt_app.processEvents()

    assert widget.adjustment_snapshot is not None
    assert widget.adjustment_snapshot.workflow_state == "LOCAL_DRAFT_READY"
    assert widget.adjustment_snapshot.pending_count == 1
    assert widget.servo_table.item(0, 4).text() == "1490"
    assert widget.servo_table.item(0, 9).text() == "1505 us / 1.25 deg"
    assert widget.servo_table.item(0, 10).text() == "1490 us / 0.0 deg"
    assert widget.servo_table.item(0, 11).text() == "PENDING_VALID_LOCAL_ONLY"
    assert widget.revert_button.isEnabled()
    assert widget.apply_button.isEnabled() is False
    assert widget.save_button.isEnabled() is False

    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.adjustment_snapshot is not None
    assert widget.adjustment_snapshot.pending_count == 1

    widget.center_edit.setFocus()
    widget.center_edit.selectAll()
    widget.center_edit.textEdited.emit("1510")
    widget.center_edit.setText("1510")
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.center_edit.text() == "1510"
    assert widget.adjustment_snapshot.pending_count == 1
    widget.center_edit.setText("1505")
    widget.center_edit.textEdited.emit("1505")
    widget.stage_button.click()

    widget.select_robot("R1", emit=False)
    assert widget.servo_table.rowCount() == 0
    assert widget.stage_button.isEnabled() is False
    widget.select_robot("R2", emit=False)
    assert widget.adjustment_snapshot is not None
    assert widget.adjustment_snapshot.pending_count == 1

    widget.revert_button.click()
    qt_app.processEvents()
    assert widget.adjustment_snapshot is not None
    assert widget.adjustment_snapshot.pending_count == 0
    assert widget.servo_table.item(0, 9).text() == "NONE"
    assert widget.center_edit.text() == "1490"
    assert widget.trim_edit.text() == "0.0"


def test_widget_stages_angle_endpoints_locally_and_preserves_unstaged_text(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    widget.min_pulse_edit.setText("550")
    widget.max_pulse_edit.setText("2450")
    widget.min_angle_edit.setText("-120")
    widget.max_angle_edit.setText("125.5")
    widget.angle_stage_button.click()
    qt_app.processEvents()

    assert widget.angle_adjustment_snapshot is not None
    assert widget.angle_adjustment_snapshot.workflow_state == "LOCAL_DRAFT_READY"
    assert widget.angle_adjustment_snapshot.pending_count == 1
    assert widget.angle_table.item(0, 7).text() == "550..2450 us | -120..125.5 deg"
    assert widget.angle_table.item(0, 9).text() == "PENDING_VALID_LOCAL_ONLY"
    assert widget.angle_apply_button.isEnabled() is False
    assert widget.angle_save_button.isEnabled() is False

    widget.min_angle_edit.setFocus()
    widget.min_angle_edit.selectAll()
    widget.min_angle_edit.textEdited.emit("-115")
    widget.min_angle_edit.setText("-115")
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.min_angle_edit.text() == "-115"
    assert widget.angle_adjustment_snapshot.pending_count == 1

    widget.min_angle_edit.setText("-120")
    widget.min_angle_edit.textEdited.emit("-120")
    widget.angle_stage_button.click()
    widget.select_robot("R1", emit=False)
    assert widget.angle_table.rowCount() == 0
    widget.select_robot("R2", emit=False)
    assert widget.angle_adjustment_snapshot is not None
    assert widget.angle_adjustment_snapshot.pending_count == 1

    widget.angle_revert_button.click()
    qt_app.processEvents()
    assert widget.angle_adjustment_snapshot is not None
    assert widget.angle_adjustment_snapshot.pending_count == 0
    assert widget.angle_table.item(0, 7).text() == "NONE"
    assert widget.min_pulse_edit.text() == "500"
    assert widget.max_angle_edit.text() == "135.0"


def test_widget_stages_direction_preview_and_preserves_robot_isolation(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.invert_vx_check.isChecked() is True
    assert widget.logical_front_combo.currentText() == "FRONT"


    assert all(check.isChecked() for check in widget._motor_invert_checks)
    assert all(check.isChecked() for check in widget._servo_invert_checks)

    widget.invert_vx_check.setChecked(False)
    widget.logical_front_combo.setCurrentText("RIGHT")
    widget._motor_invert_checks[0].setChecked(False)
    widget._servo_invert_checks[1].setChecked(False)
    widget.direction_stage_button.click()
    qt_app.processEvents()

    assert widget.direction_adjustment_snapshot is not None
    assert widget.direction_adjustment_snapshot.workflow_state == "LOCAL_DRAFT_READY"
    assert widget.direction_adjustment_snapshot.pending_count == 4
    assert widget.direction_controller_table.item(0, 3).text() == "NORMAL"
    assert widget.direction_wheel_table.item(0, 2).text() == "NORMAL"
    assert widget.direction_wheel_table.item(1, 5).text() == "NORMAL"
    assert "pending=RIGHT" in widget.direction_preview_label.text()
    assert "+logical X -> -machine Y" in widget.direction_preview_label.text()
    assert widget.direction_apply_button.isEnabled() is False
    assert widget.direction_save_button.isEnabled() is False

    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.direction_adjustment_snapshot.pending_count == 4
    assert widget.logical_front_combo.currentText() == "RIGHT"

    widget.direction_raw_vx_edit.setFocus()
    widget.direction_raw_vx_edit.selectAll()
    widget.direction_raw_vx_edit.textEdited.emit("0.75")
    widget.direction_raw_vx_edit.setText("0.75")
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.direction_raw_vx_edit.text() == "0.75"
    assert widget.direction_adjustment_snapshot.pending_count == 4

    widget.select_robot("R1", emit=False)
    assert widget.direction_wheel_table.rowCount() == 0
    assert widget.direction_stage_button.isEnabled() is False
    widget.select_robot("R2", emit=False)
    assert widget.direction_adjustment_snapshot is not None
    assert widget.direction_adjustment_snapshot.pending_count == 4

    widget.direction_revert_button.click()
    qt_app.processEvents()
    assert widget.direction_adjustment_snapshot is not None
    assert widget.direction_adjustment_snapshot.pending_count == 0
    assert widget.invert_vx_check.isChecked() is True
    assert widget.logical_front_combo.currentText() == "FRONT"


def test_parameter_slider_is_local_only_and_draft_survives_refresh_and_robot_switch(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R2, (robot,), now_ms=robot.timestamp_ms)
    widget = CalibrationDiagnosticWidget()
    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()

    assert widget.parameter_combo.currentData() == "controller.deadzone"
    assert widget.parameter_spin.value() == pytest.approx(0.12)
    assert widget.parameter_adjustment_snapshot is not None
    assert widget.parameter_adjustment_snapshot.pending_count == 0

    widget.parameter_slider.setValue(20)
    qt_app.processEvents()
    assert widget.parameter_spin.value() == pytest.approx(0.2)
    assert widget.parameter_adjustment_snapshot.pending_count == 0

    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.parameter_spin.value() == pytest.approx(0.2)
    assert widget.parameter_adjustment_snapshot.pending_count == 0

    widget.parameter_stage_button.click()
    qt_app.processEvents()
    assert widget.parameter_adjustment_snapshot is not None
    assert widget.parameter_adjustment_snapshot.workflow_state == "LOCAL_DRAFT_READY"
    assert widget.parameter_adjustment_snapshot.pending_count == 1
    assert widget.parameter_table.item(0, 2).text() == "0.12"
    assert widget.parameter_table.item(0, 3).text() == "0.2"
    assert widget.parameter_table.item(0, 4).text() == "0.12"
    assert widget.parameter_apply_button.isEnabled() is False
    assert widget.parameter_save_button.isEnabled() is False

    widget.set_fleet_snapshot(fleet)
    qt_app.processEvents()
    assert widget.parameter_adjustment_snapshot.pending_count == 1
    assert widget.parameter_spin.value() == pytest.approx(0.2)

    widget.select_robot("R1", emit=False)
    assert widget.parameter_stage_button.isEnabled() is False
    widget.select_robot("R2", emit=False)
    assert widget.parameter_adjustment_snapshot is not None
    assert widget.parameter_adjustment_snapshot.pending_count == 1

    widget.parameter_revert_button.click()
    qt_app.processEvents()
    assert widget.parameter_adjustment_snapshot is not None
    assert widget.parameter_adjustment_snapshot.pending_count == 0
    assert widget.parameter_spin.value() == pytest.approx(0.12)
    widget.close()
