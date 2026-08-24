from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_runtime import FakeFleetDashboardRuntime

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.fault_history_widget import FaultHistoryWidget  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    yield app


def _runtime(tmp_path: Path) -> FakeFleetDashboardRuntime:
    config_dir = tmp_path / "config"
    ensure_config_files(config_dir)
    return FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R2,
        config_dir=config_dir,
        node_manifest=ROOT / "config" / "node_manifest.json",
    )


def test_widget_retains_session_fault_and_acknowledges_without_clearing_safety_or_output(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    widget = FaultHistoryWidget()
    widget.set_fleet_snapshot(runtime.start())
    writes_before = tuple(runtime.controller.serial.writes)

    assert widget.selected_robot == "R2"
    assert widget.history_snapshot is not None
    assert widget.history_snapshot.entries == ()

    runtime.controller.safety.disarm("widget safety root cause")
    widget.set_fleet_snapshot(runtime.snapshot())
    history = widget.history_snapshot
    assert history is not None
    assert history.active_count == 1
    assert history.entries[0].source == "PC_SAFETY"
    assert history.entries[0].reason == "widget safety root cause"
    assert "FIRST_OBSERVED" in widget.history_table.item(0, 5).text()
    assert widget.acknowledge_button.isEnabled() is False

    widget.history_table.selectRow(0)
    qt_app.processEvents()
    assert widget.acknowledge_button.isEnabled() is True

    # A 100 ms shared-runtime refresh must not make the local action impossible
    # by clearing the operator's selected event on every snapshot.
    selected_event_id = history.entries[0].event_id
    widget.set_fleet_snapshot(runtime.snapshot())
    qt_app.processEvents()
    assert widget.history_table.currentRow() == 0
    assert widget.history_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == selected_event_id
    assert widget.acknowledge_button.isEnabled() is True

    widget.acknowledge_button.click()
    qt_app.processEvents()

    history = widget.history_snapshot
    assert history is not None
    assert history.entries[0].acknowledged is True
    assert history.entries[0].active is True
    assert runtime.controller.safety.fault == "widget safety root cause"
    assert tuple(runtime.controller.serial.writes) == writes_before
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)

    runtime.controller.safety.apply_config()
    widget.set_fleet_snapshot(runtime.snapshot())
    history = widget.history_snapshot
    assert history is not None
    assert history.active_count == 0
    assert history.entries[0].acknowledged is True
    assert history.entries[0].active is False
    runtime.close()


def test_widget_keeps_r1_r2_history_and_selection_isolated(qt_app: QApplication, tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    widget = FaultHistoryWidget()
    widget.set_fleet_snapshot(runtime.start())

    widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert widget.selected_robot == "R1"
    assert widget.history_snapshot is not None
    assert [entry.source for entry in widget.history_snapshot.entries] == ["GUI_BINDING"]

    widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert widget.selected_robot == "R2"
    assert widget.history_snapshot is not None
    assert widget.history_snapshot.entries == ()
    runtime.close()


def test_widget_paints_offscreen(qt_app: QApplication, tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    widget = FaultHistoryWidget()
    widget.resize(1400, 900)
    widget.set_fleet_snapshot(runtime.start())
    runtime.controller.safety.disarm("painted fault")
    widget.set_fleet_snapshot(runtime.snapshot())
    widget.show()
    qt_app.processEvents()

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    widget.render(painter, widget.rect().topLeft(), QRect(widget.rect()))
    painter.end()

    assert image.isNull() is False
    assert widget.history_table.rowCount() == 1
    assert "LOCAL_VIEW_ONLY" in widget.boundary_label.text()
    assert "No clear/delete/apply control" in widget.action_notice.text()
    widget.close()
    runtime.close()
