from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton

from pc_controller.autonomy import AutonomyState, RobotId
from pc_controller.competition import CompetitionLogWriter, CompetitionState
from pc_controller.gui_logs_model import load_competition_log_source

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.replay_widget import ReplayWidget  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


def _log(path: Path) -> Path:
    writer = CompetitionLogWriter(path, "replay-widget")
    writer.append(0, "enabled", CompetitionState.PRECHECK)
    writer.append(
        10,
        "r1-running",
        CompetitionState.ACTIVE,
        robot_id=RobotId.R1,
        autonomy_state=AutonomyState.RUNNING,
        safety_state="NORMAL",
        armed=True,
    )
    writer.append(20, "r2-running", CompetitionState.ACTIVE, robot_id=RobotId.R2)
    writer.append(30, "stopped", CompetitionState.STOPPED, reason="operator stop")
    writer.close()
    return path


def test_widget_manual_cursor_and_robot_selection_are_local(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    widget = ReplayWidget()
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.availability == "NOT_CONFIGURED"
    assert widget.timeline_table.rowCount() == 0

    source = load_competition_log_source(_log(tmp_path / "replay.jsonl"))
    widget.set_log_source(source)
    qt_app.processEvents()
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.robot_id == RobotId.R1
    assert [event.sequence for event in widget.screen_snapshot.timeline] == [1, 2, 4]
    assert widget.screen_snapshot.current_sequence == 1
    assert widget.timeline_table.rowCount() == 3

    widget.next_button.click()
    qt_app.processEvents()
    assert widget.screen_snapshot.current_sequence == 2
    assert widget.screen_snapshot.autonomy_state == "RUNNING"
    assert "LAST_RECORDED_FOR_R1@sequence=2" in widget.recorded_state_label.text()

    widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert widget.selected_robot == "R2"
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.current_sequence == 1
    widget.last_button.click()
    assert widget.screen_snapshot.current_sequence == 4

    widget._robot_buttons["R1"].click()
    assert widget.screen_snapshot.current_sequence == 2
    widget.set_log_source(source)
    assert widget.screen_snapshot.current_sequence == 2

    controls = {button.text() for button in widget.findChildren(QPushButton)}
    assert controls == {"R1", "R2", "First", "Previous", "Next", "Last"}
    assert not controls.intersection({"ARM", "START", "STOP", "Apply", "Execute", "Send"})
    assert "Recorded actions are inert labels" in widget.boundary_label.text()
    widget.close()


def test_widget_invalid_source_disables_cursor_and_paints(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    widget = ReplayWidget()
    widget.set_log_source(load_competition_log_source(path))
    widget.resize(1400, 900)
    widget.show()
    qt_app.processEvents()

    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.availability == "INVALID_SOURCE"
    assert widget.timeline_table.rowCount() == 0
    assert widget.cursor_slider.isEnabled() is False
    assert widget.first_button.isEnabled() is False
    assert "OFFLINE_VISUALIZATION_ONLY" in widget.boundary_label.text()

    image = QImage(1400, 900, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    assert not image.isNull()
    widget.close()
