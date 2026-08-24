from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from pc_controller.config_manager import default_controller_mapping, default_vehicle_config, save_json
from pc_controller.controller_input import ControllerState

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.real_hardware_settings_widget import RealHardwareSettingsWidget  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


def _config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    vehicle = default_vehicle_config()
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    save_json(config_dir / "vehicle_config.json", vehicle)
    save_json(config_dir / "controller_mapping.json", default_controller_mapping())
    return config_dir


def test_editor_loads_connection_and_numeric_settings(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    del qt_app
    widget = RealHardwareSettingsWidget(_config_dir(tmp_path))

    assert widget.connector_inputs["FL"]["servo_channel"].value() == 6
    assert widget.connector_inputs["FL"]["motor_physical"].value() == 2
    assert widget.connector_inputs["FL"]["encoder_physical"].value() == 0
    assert widget.motion_inputs["open_loop_max_pwm"].value() == 120
    assert widget.controller_inputs["deadzone"].value() == pytest.approx(0.12)
    assert widget.controller_inputs["logical_front"].currentText() == "FRONT"
    widget.close()


def test_editor_saves_and_live_applies_validated_settings_with_backup(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del qt_app
    config_dir = _config_dir(tmp_path)
    applied: list[tuple[dict, dict]] = []
    widget = RealHardwareSettingsWidget(
        config_dir,
        apply_callback=lambda vehicle, mapping: applied.append((vehicle, mapping)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    for index, name in enumerate(("FL", "FR", "RL", "RR")):
        widget.connector_inputs[name]["servo_channel"].setValue(index)
        widget.connector_inputs[name]["motor_physical"].setValue(index)
        widget.connector_inputs[name]["encoder_physical"].setValue(index)
    widget.motion_inputs["open_loop_max_pwm"].setValue(75)
    widget.controller_inputs["deadzone"].setValue(0.2)
    widget.controller_inputs["logical_front"].setCurrentText("REAR")
    widget.save_to_disk()

    vehicle = json.loads((config_dir / "vehicle_config.json").read_text(encoding="utf-8"))
    mapping = json.loads((config_dir / "controller_mapping.json").read_text(encoding="utf-8"))
    assert vehicle["config_revision"] == 2
    assert vehicle["motion"]["open_loop_max_pwm"] == 75
    assert [item["channel"] for item in vehicle["servos"]] == [0, 1, 2, 3]
    assert [item["physical"] for item in vehicle["motors"]] == [0, 1, 2, 3]
    assert mapping["deadzone"] == pytest.approx(0.2)
    assert mapping["logical_front"] == "REAR"
    assert list((config_dir / "gui_backups").glob("*/vehicle_config.json"))
    assert len(applied) == 1
    assert applied[0][0]["motion"]["open_loop_max_pwm"] == 75
    assert applied[0][1]["deadzone"] == pytest.approx(0.2)
    assert applied[0][1]["logical_front"] == "REAR"
    assert "即時反映完了" in widget.save_state_label.text()
    widget.close()


def test_editor_restores_files_when_live_apply_fails(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del qt_app
    config_dir = _config_dir(tmp_path)
    original_vehicle = (config_dir / "vehicle_config.json").read_text(encoding="utf-8")
    original_mapping = (config_dir / "controller_mapping.json").read_text(encoding="utf-8")

    def reject_apply(vehicle: dict, mapping: dict) -> None:
        del vehicle, mapping
        raise RuntimeError("CONFIG rejected for test")

    widget = RealHardwareSettingsWidget(config_dir, apply_callback=reject_apply)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    widget.motion_inputs["open_loop_max_pwm"].setValue(70)
    widget.save_to_disk()

    assert (config_dir / "vehicle_config.json").read_text(encoding="utf-8") == original_vehicle
    assert (config_dir / "controller_mapping.json").read_text(encoding="utf-8") == original_mapping
    assert widget.motion_inputs["open_loop_max_pwm"].value() == 120
    assert "保存失敗" in widget.save_state_label.text()
    widget.close()


def test_controller_input_panel_shows_live_axes(qt_app: QApplication, tmp_path: Path) -> None:
    del qt_app
    widget = RealHardwareSettingsWidget(_config_dir(tmp_path))
    widget.set_controller_input_snapshot(
        ControllerState(
            connected=True,
            name="Wireless Controller",
            vx=0.5,
            vy=-0.25,
            omega=0.75,
            arm_pressed=True,
            safe_pressed=False,
        )
    )

    assert "接続済み" in widget.controller_connection_label.text()
    assert "Wireless Controller" in widget.controller_connection_label.text()
    assert "vx=+0.500" in widget.controller_live_label.text()
    assert "ARM組合せ=ON" in widget.controller_live_label.text()
    widget.close()
