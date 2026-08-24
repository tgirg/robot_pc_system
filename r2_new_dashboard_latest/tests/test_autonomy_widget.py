from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton

from pc_controller.autonomy import (
    AutonomyStateMachine,
    FailureAction,
    MissionPlan,
    MissionStep,
    RobotId,
)
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.gui_runtime import FakeFleetDashboardRuntime

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from widgets.autonomy_widget import AutonomyWidget  # noqa: E402


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


def _machine() -> AutonomyStateMachine:
    return AutonomyStateMachine(
        MissionPlan(
            "field_mission",
            RobotId.R2,
            (
                MissionStep(
                    "collect_block",
                    max_retries=1,
                    retry_delay_ms=100,
                    on_failure=FailureAction.FALLBACK,
                    fallback_id="safe_stop",
                ),
                MissionStep("return_home"),
            ),
        )
    )


def _fleet_with_machine(runtime: FakeFleetDashboardRuntime, machine: AutonomyStateMachine):
    now_ms = runtime.controller._now_ms()
    bound = build_robot_dashboard_snapshot(
        runtime.controller,
        RobotId.R2,
        now_ms=now_ms,
        node_requirements=runtime.node_requirements,
        autonomy=machine,
    )
    return build_fleet_dashboard_snapshot(RobotId.R2, (bound,), now_ms=now_ms)


def test_fake_runtime_without_machine_renders_not_configured_and_no_action_controls(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    del qt_app
    runtime = _runtime(tmp_path)
    widget = AutonomyWidget()
    widget.set_fleet_snapshot(runtime.start())
    writes_before = tuple(runtime.controller.serial.writes)

    screen = widget.screen_snapshot
    assert screen is not None
    assert screen.robot_id == RobotId.R2
    assert screen.controller_configured is True
    assert screen.autonomy_configured is False
    assert screen.state_id == "NOT_CONFIGURED"
    assert "NO_AUTONOMY_MACHINE" in widget.state_label.text()
    assert widget.event_table.rowCount() == 0
    buttons = widget.findChildren(QPushButton)
    assert {button.objectName() for button in buttons} == {
        "autonomySelectR1Button",
        "autonomySelectR2Button",
    }
    assert tuple(runtime.controller.serial.writes) == writes_before
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)
    widget.close()
    runtime.close()


def test_widget_displays_authoritative_machine_context_and_keeps_r1_r2_isolated(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.start()
    machine = _machine()
    machine.prepare(10, required_nodes_ready=True, safety_ready=True)
    machine.confirm_explicit_arm(20, confirmed=True)
    machine.start(30, explicit_start=True)
    writes_before = tuple(runtime.controller.serial.writes)
    state_before = machine.state

    widget = AutonomyWidget()
    widget.set_fleet_snapshot(_fleet_with_machine(runtime, machine))
    screen = widget.screen_snapshot
    assert screen is not None
    assert screen.state_id == "RUNNING"
    assert screen.current_step == "collect_block"
    assert screen.current_target is None
    assert "current target=NOT_DEFINED_IN_MISSION_MODEL" in widget.mission_label.text()
    assert screen.next_step == "return_home"
    assert screen.failure_action == "FALLBACK"
    assert screen.configured_fallback_id == "safe_stop"
    assert widget.event_table.rowCount() == 3
    assert "executor confirmation=UNKNOWN_NOT_RETAINED" in widget.boundary_label.text()

    widget._robot_buttons["R1"].click()
    qt_app.processEvents()
    assert widget.selected_robot == "R1"
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.autonomy_configured is False
    assert widget.screen_snapshot.state_id == "NOT_CONFIGURED"

    widget._robot_buttons["R2"].click()
    qt_app.processEvents()
    assert widget.selected_robot == "R2"
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.state_id == "RUNNING"
    assert machine.state == state_before
    assert tuple(runtime.controller.serial.writes) == writes_before
    assert all(message["type"] != "arm" for message in runtime.controller.serial.writes)
    widget.close()
    runtime.close()


def test_widget_paints_retry_and_request_semantics_offscreen(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.start()
    machine = _machine()
    machine.prepare(0, required_nodes_ready=True, safety_ready=True)
    machine.confirm_explicit_arm(1, confirmed=True)
    machine.start(2, explicit_start=True)
    machine.record_step_failure(10, "temporary blockage")

    widget = AutonomyWidget()
    widget.resize(1400, 900)
    widget.set_fleet_snapshot(_fleet_with_machine(runtime, machine))
    widget.show()
    qt_app.processEvents()

    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    widget.render(painter, widget.rect().topLeft(), QRect(widget.rect()))
    painter.end()

    assert image.isNull() is False
    assert widget.screen_snapshot is not None
    assert widget.screen_snapshot.state_id == "RETRY_WAIT"
    assert "HOLD_REQUESTED" in widget.failure_policy_label.text()
    assert "EXECUTOR_CONFIRMATION=UNKNOWN" in widget.failure_policy_label.text()
    assert "No direct action controls" in widget.boundary_label.text()
    widget.close()
    runtime.close()
