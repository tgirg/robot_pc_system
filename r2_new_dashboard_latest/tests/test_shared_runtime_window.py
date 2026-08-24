from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from pc_controller.autonomy import RobotId
from pc_controller.competition import CompetitionLogWriter, CompetitionState
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_runtime import FakeFleetDashboardRuntime

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

import main_ui  # noqa: E402
import real_dashboard_main  # noqa: E402
import shared_dashboard_main  # noqa: E402
from shared_runtime_binding import QtFleetDashboardBinding  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


def test_shared_runtime_window_constructs_no_legacy_io(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del qt_app

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("legacy hardware/I/O constructor was called")

    monkeypatch.setattr(main_ui, "ConnectionManager", forbidden)
    monkeypatch.setattr(main_ui, "ESP32Serial", forbidden)
    monkeypatch.setattr(main_ui, "CameraModule", forbidden)
    monkeypatch.setattr(main_ui, "detect_ports", forbidden)

    window = main_ui.MainWindow(shared_runtime_only=True)

    assert not hasattr(window, "serial")
    assert not hasattr(window, "camera")
    assert not hasattr(window, "timer")
    assert window.tabs.count() == 12
    assert window.tabs.tabText(0) == "Main Dashboard"
    assert window.tabs.tabText(1) == "Drive Diagnostic"
    assert window.tabs.tabText(2) == "Mechanism Diagnostic"
    assert window.tabs.tabText(3) == "Sensor Check"
    assert window.tabs.tabText(4) == "Sensor Diagnostic"
    assert window.tabs.tabText(5) == "Calibration"
    assert window.tabs.tabText(6) == "Field Map"
    assert window.tabs.tabText(7) == "Fault / Warning History"
    assert window.tabs.tabText(8) == "Autonomy"
    assert window.tabs.tabText(9) == "Logs"
    assert window.tabs.tabText(10) == "Replay"
    assert window.tabs.tabText(11) == "Sound Settings"
    assert window.main_dashboard_widget.isEnabled()
    assert window.drive_diagnostic_widget.isEnabled()
    assert window.mechanism_diagnostic_widget.isEnabled()
    assert window.sensor_check_widget.isEnabled()
    assert window.sensor_diagnostic_widget.isEnabled()
    assert window.calibration_diagnostic_widget.isEnabled()
    assert window.fault_history_widget.isEnabled()
    assert window.autonomy_widget.isEnabled()
    assert window.logs_widget.isEnabled()
    assert window.replay_widget.isEnabled()
    assert window.shared_field_map_widget.isEnabled()
    assert window.sound_settings_widget.isEnabled()
    assert window.command_center_nav.buttons[0].isChecked()
    window.command_center_nav.buttons[-1].click()
    assert window.tabs.currentIndex() == 11
    assert window.command_center_nav.buttons[-1].isChecked()
    window.close()


def test_shared_dashboard_entrypoint_requires_explicit_robot_binding() -> None:
    parser = shared_dashboard_main.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    assert parser.parse_args(["--robot", "R1"]).robot == "R1"
    assert parser.parse_args(["--robot", "R2"]).robot == "R2"
    parsed = parser.parse_args(["--robot", "R1", "--competition-log", "session.jsonl"])
    assert parsed.competition_log == Path("session.jsonl")


def test_real_dashboard_entrypoint_is_r2_only_and_motion_requires_explicit_flag() -> None:
    parser = real_dashboard_main.build_arg_parser()
    parsed = parser.parse_args([])
    assert parsed.robot == "R2"
    assert parsed.enable_motion is False
    assert parsed.max_pwm == 120
    assert parser.parse_args(["--enable-motion", "--port", "COM7"]).enable_motion is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--robot", "R1"])


def test_real_shared_window_labels_r2_and_disables_r1_selectors(qt_app: QApplication) -> None:
    del qt_app
    window = main_ui.MainWindow(
        shared_runtime_only=True,
        shared_runtime_mode="real",
        shared_runtime_max_pwm=120,
    )
    window.lock_shared_runtime_robot("R2")

    assert "R2実機 / 新GUI" in window.windowTitle()
    assert window.tabs.tabText(2) == "実機接続・設定"
    assert window.tabs.tabText(5) == "書き込み"
    assert window.tabs.tabText(6) == "シリアル"
    assert window.tabs.tabText(7) == "センサ診断"
    assert window.real_hardware_settings_widget is not None
    assert window.main_dashboard_widget._robot_buttons["R1"].isEnabled() is False
    assert window.main_dashboard_widget._robot_buttons["R2"].isEnabled() is True
    assert window.drive_diagnostic_widget._robot_buttons["R1"].isEnabled() is False
    assert window.drive_diagnostic_widget._robot_buttons["R2"].isEnabled() is True
    window.close()


def test_qt_binding_injects_periodic_fake_snapshot_and_preserves_selection(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    ensure_config_files(config_dir)
    manifest = ROOT / "config" / "node_manifest.json"
    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R2,
        config_dir=config_dir,
        node_manifest=manifest,
    )
    window = main_ui.MainWindow(shared_runtime_only=True)
    binding = QtFleetDashboardBinding(window, runtime, interval_ms=100)
    window.shared_runtime_binding = binding

    binding.start()
    window.show()
    qt_app.processEvents()

    assert binding.timer.isActive()
    assert "R1: OFFLINE" in window.main_dashboard_widget._summary_labels["R1"].text()
    assert "R2: ONLINE" in window.main_dashboard_widget._summary_labels["R2"].text()
    assert "R2 | ONLINE | SAFE | READY" == window.main_dashboard_widget.selected_state_label.text()
    assert "R2 | 4WIS | ONLINE | SAFE | READY | DISARMED" == (
        window.drive_diagnostic_widget.selected_state_label.text()
    )
    assert "R2 | ONLINE | SAFE | READY | DISARMED" == (
        window.mechanism_diagnostic_widget.selected_state_label.text()
    )
    assert window.mechanism_diagnostic_widget.diagnostic_snapshot is not None
    assert window.mechanism_diagnostic_widget.diagnostic_snapshot.inventory_state == "NOT_CONFIGURED"
    assert "R2 | ONLINE | SAFE | READY | DISARMED" == (
        window.sensor_diagnostic_widget.selected_state_label.text()
    )
    assert window.sensor_diagnostic_widget.diagnostic_snapshot is not None
    assert window.sensor_diagnostic_widget.diagnostic_snapshot.inventory_state == "DEFINED_PENDING_CHECK"
    assert window.sensor_check_widget.table.rowCount() == 12
    assert "R2 | ONLINE | SAFE | READY | DISARMED" == (
        window.calibration_diagnostic_widget.selected_state_label.text()
    )
    assert window.calibration_diagnostic_widget.diagnostic_snapshot is not None
    assert window.calibration_diagnostic_widget.diagnostic_snapshot.workflow_state == "READ_ONLY_AUDIT"
    assert window.fault_history_widget.history_snapshot is not None
    assert window.fault_history_widget.history_snapshot.entries == ()
    assert window.autonomy_widget.screen_snapshot is not None
    assert window.autonomy_widget.screen_snapshot.autonomy_configured is False
    assert window.autonomy_widget.screen_snapshot.state_id == "NOT_CONFIGURED"
    assert window.logs_widget.screen_snapshot is not None
    assert window.logs_widget.screen_snapshot.source_status == "NOT_CONFIGURED"
    assert window.replay_widget.screen_snapshot is not None
    assert window.replay_widget.screen_snapshot.availability == "NOT_CONFIGURED"

    competition_log = tmp_path / "shared-window-competition.jsonl"
    writer = CompetitionLogWriter(competition_log, "shared-window")
    writer.append(0, "session_finalized", CompetitionState.POST_COMPETITION)
    writer.close()
    window.logs_widget.set_competition_log_path(competition_log)
    writes_before_log_reload = tuple(runtime.controller.serial.writes)
    window.logs_widget.reload_button.click()
    qt_app.processEvents()
    assert window.logs_widget.screen_snapshot is not None
    assert window.logs_widget.screen_snapshot.session_id == "shared-window"
    assert window.replay_widget.screen_snapshot is not None
    assert window.replay_widget.screen_snapshot.session_id == "shared-window"
    assert window.replay_widget.screen_snapshot.current_sequence == 1
    assert tuple(runtime.controller.serial.writes) == writes_before_log_reload
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)

    writes_before_draft = tuple(runtime.controller.serial.writes)
    window.calibration_diagnostic_widget.invert_vx_check.setChecked(False)
    window.calibration_diagnostic_widget.logical_front_combo.setCurrentText("LEFT")
    window.calibration_diagnostic_widget.direction_stage_button.click()
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot.pending_count == 2
    window.calibration_diagnostic_widget.parameter_slider.setValue(20)
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot.pending_count == 0
    assert tuple(runtime.controller.serial.writes) == writes_before_draft
    window.calibration_diagnostic_widget.parameter_stage_button.click()
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot.pending_count == 1
    window.calibration_diagnostic_widget.center_edit.setText("1505")
    window.calibration_diagnostic_widget.trim_edit.setText("1.0")
    window.calibration_diagnostic_widget.stage_button.click()
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.adjustment_snapshot.pending_count == 1
    window.calibration_diagnostic_widget.min_pulse_edit.setText("550")
    window.calibration_diagnostic_widget.max_pulse_edit.setText("2450")
    window.calibration_diagnostic_widget.min_angle_edit.setText("-120")
    window.calibration_diagnostic_widget.max_angle_edit.setText("120")
    window.calibration_diagnostic_widget.angle_stage_button.click()
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot.pending_count == 1
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot.pending_count == 2
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot.pending_count == 1
    assert tuple(runtime.controller.serial.writes) == writes_before_draft
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)

    binding._tick()
    qt_app.processEvents()
    assert window.calibration_diagnostic_widget.adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.adjustment_snapshot.pending_count == 1
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot.pending_count == 1
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.parameter_adjustment_snapshot.pending_count == 1
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.direction_adjustment_snapshot.pending_count == 2

    window.main_dashboard_widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R1
    assert window.main_dashboard_widget.selected_robot == "R1"
    assert window.main_dashboard_widget._fleet.selected.configured is False
    assert window.drive_diagnostic_widget.selected_robot == "R1"
    assert window.drive_diagnostic_widget.diagnostic_snapshot is not None
    assert window.drive_diagnostic_widget.diagnostic_snapshot.configured is False
    assert window.mechanism_diagnostic_widget.selected_robot == "R1"
    assert window.mechanism_diagnostic_widget.diagnostic_snapshot is not None
    assert window.mechanism_diagnostic_widget.diagnostic_snapshot.inventory_state == "UNBOUND"
    assert window.sensor_diagnostic_widget.selected_robot == "R1"
    assert window.sensor_diagnostic_widget.diagnostic_snapshot is not None
    assert window.sensor_diagnostic_widget.diagnostic_snapshot.inventory_state == "UNBOUND"
    assert window.calibration_diagnostic_widget.selected_robot == "R1"
    assert window.calibration_diagnostic_widget.diagnostic_snapshot is not None
    assert window.calibration_diagnostic_widget.diagnostic_snapshot.workflow_state == "UNBOUND"
    assert window.fault_history_widget.selected_robot == "R1"
    assert window.fault_history_widget.history_snapshot is not None
    assert [entry.source for entry in window.fault_history_widget.history_snapshot.entries] == ["GUI_BINDING"]
    assert window.autonomy_widget.selected_robot == "R1"
    assert window.logs_widget.selected_robot == "R1"
    assert window.replay_widget.selected_robot == "R1"
    assert window.autonomy_widget.screen_snapshot is not None
    assert window.autonomy_widget.screen_snapshot.autonomy_configured is False
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)

    window.drive_diagnostic_widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R2
    assert window.main_dashboard_widget.selected_robot == "R2"
    assert window.drive_diagnostic_widget.selected_robot == "R2"
    assert window.mechanism_diagnostic_widget.selected_robot == "R2"
    assert window.sensor_diagnostic_widget.selected_robot == "R2"
    assert window.calibration_diagnostic_widget.selected_robot == "R2"
    assert window.fault_history_widget.selected_robot == "R2"
    assert window.autonomy_widget.selected_robot == "R2"
    assert window.logs_widget.selected_robot == "R2"
    assert window.replay_widget.selected_robot == "R2"
    assert window.calibration_diagnostic_widget.adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.adjustment_snapshot.pending_count == 1
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot is not None
    assert window.calibration_diagnostic_widget.angle_adjustment_snapshot.pending_count == 1

    window.mechanism_diagnostic_widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R1
    assert window.main_dashboard_widget.selected_robot == "R1"
    assert window.drive_diagnostic_widget.selected_robot == "R1"
    assert window.mechanism_diagnostic_widget.selected_robot == "R1"
    assert window.sensor_diagnostic_widget.selected_robot == "R1"
    assert window.calibration_diagnostic_widget.selected_robot == "R1"
    assert window.fault_history_widget.selected_robot == "R1"
    assert window.autonomy_widget.selected_robot == "R1"
    assert window.logs_widget.selected_robot == "R1"
    assert window.replay_widget.selected_robot == "R1"

    window.calibration_diagnostic_widget._robot_buttons["R2"].click()
    qt_app.processEvents()

    binding._tick()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R2
    assert window.main_dashboard_widget.selected_robot == "R2"
    assert window.drive_diagnostic_widget.selected_robot == "R2"
    assert window.mechanism_diagnostic_widget.selected_robot == "R2"
    assert window.sensor_diagnostic_widget.selected_robot == "R2"
    assert window.calibration_diagnostic_widget.selected_robot == "R2"
    assert window.fault_history_widget.selected_robot == "R2"
    assert window.autonomy_widget.selected_robot == "R2"
    assert window.logs_widget.selected_robot == "R2"
    assert window.replay_widget.selected_robot == "R2"

    window.fault_history_widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R1
    assert window.main_dashboard_widget.selected_robot == "R1"
    assert window.drive_diagnostic_widget.selected_robot == "R1"
    assert window.mechanism_diagnostic_widget.selected_robot == "R1"
    assert window.sensor_diagnostic_widget.selected_robot == "R1"
    assert window.calibration_diagnostic_widget.selected_robot == "R1"
    assert window.fault_history_widget.selected_robot == "R1"
    assert window.autonomy_widget.selected_robot == "R1"
    assert window.logs_widget.selected_robot == "R1"
    assert window.replay_widget.selected_robot == "R1"

    window.logs_widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R2
    assert window.main_dashboard_widget.selected_robot == "R2"
    assert window.autonomy_widget.selected_robot == "R2"
    assert window.logs_widget.selected_robot == "R2"
    assert window.replay_widget.selected_robot == "R2"

    window.replay_widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R1
    assert window.main_dashboard_widget.selected_robot == "R1"
    assert window.logs_widget.selected_robot == "R1"
    assert window.replay_widget.selected_robot == "R1"

    window.fault_history_widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R2
    assert window.autonomy_widget.selected_robot == "R2"

    window.autonomy_widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert runtime.selected_robot == RobotId.R1
    assert window.main_dashboard_widget.selected_robot == "R1"
    assert window.drive_diagnostic_widget.selected_robot == "R1"
    assert window.mechanism_diagnostic_widget.selected_robot == "R1"
    assert window.sensor_diagnostic_widget.selected_robot == "R1"
    assert window.calibration_diagnostic_widget.selected_robot == "R1"
    assert window.fault_history_widget.selected_robot == "R1"
    assert window.autonomy_widget.selected_robot == "R1"
    assert window.logs_widget.selected_robot == "R1"
    assert window.replay_widget.selected_robot == "R1"
    window.close()
    assert binding.timer.isActive() is False
    assert runtime.closed is True
