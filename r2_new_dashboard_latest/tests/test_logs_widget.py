from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton

from pc_controller.autonomy import RobotId
from pc_controller.competition import CompetitionLogWriter, CompetitionState

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.logs_widget import LogsWidget  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


def _log(path: Path) -> Path:
    writer = CompetitionLogWriter(path, "widget-session")
    writer.append(0, "enabled", CompetitionState.PRECHECK)
    writer.append(1, "r1-event", CompetitionState.ACTIVE, robot_id=RobotId.R1)
    writer.append(2, "r2-event", CompetitionState.ACTIVE, robot_id=RobotId.R2)
    writer.append(3, "session_finalized", CompetitionState.POST_COMPETITION)
    writer.close()
    return path


def test_widget_starts_not_configured_and_loads_only_explicit_log(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    widget = LogsWidget()
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.source_status == "NOT_CONFIGURED"
    assert widget.event_table.rowCount() == 0
    assert widget.reload_button.isEnabled() is False

    widget.set_competition_log_path(_log(tmp_path / "competition.jsonl"))
    qt_app.processEvents()
    assert widget.reload_button.isEnabled() is True
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.session_id == "widget-session"
    assert [entry.sequence for entry in widget.screen_snapshot.entries] == [1, 2, 4]
    assert widget.event_table.rowCount() == 3

    widget.select_robot("R2", emit=False)
    assert widget.screen_snapshot is not None
    assert [entry.sequence for entry in widget.screen_snapshot.entries] == [1, 3, 4]
    assert "AWAITING_REMOTE_CONFIGURATION" in widget.boundary_label.text()
    assert "remote transfer performed=False" in widget.boundary_label.text()

    controls = {button.text() for button in widget.findChildren(QPushButton)}
    assert controls == {"R1", "R2", "Reload explicit local log"}
    assert not controls.intersection({"ARM", "START", "STOP", "SKIP", "FALLBACK", "Apply", "Delete"})
    widget.close()


def test_widget_invalid_reload_fails_closed_and_paints(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    widget = LogsWidget()
    widget.set_competition_log_path(path)
    widget.resize(1400, 900)
    widget.show()
    qt_app.processEvents()

    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.source_status == "INVALID"
    assert widget.event_table.rowCount() == 0
    assert "INVALID_LOCAL_COMPETITION_JSONL" in widget.source_label.text()

    image = QImage(1400, 900, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    assert not image.isNull()
    widget.close()
