from __future__ import annotations

import argparse
from pathlib import Path

from pc_controller.app import ControllerApp
from pc_controller.autonomy import (
    AutonomyStateMachine,
    FailureAction,
    MissionPlan,
    MissionStep,
    RobotId,
)
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_autonomy_model import build_autonomy_screen_snapshot
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _args(config_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir), simulate=False, fake_esp32=True, fake_trace=False,
        port=None, node_role="drive", node_id=None, discovery_timeout=0.1,
        reconnect_interval=1.0, reconnect_handshake_timeout=0.5, auto_reconnect=True,
        once=False, duration=None, joystick=False, list_controllers=False,
        debug_controller=None, rpm_monitor=False, rpm_monitor_hz=5.0,
    )


def _controller(tmp_path: Path) -> tuple[ControllerApp, ManualClock]:
    ensure_config_files(tmp_path)
    clock = ManualClock()
    return ControllerApp(_args(tmp_path), now_ms=clock), clock


def _machine(robot_id: RobotId = RobotId.R2) -> AutonomyStateMachine:
    return AutonomyStateMachine(
        MissionPlan(
            "field_mission",
            robot_id,
            (
                MissionStep(
                    "collect_block",
                    max_retries=1,
                    retry_delay_ms=200,
                    on_failure=FailureAction.SKIP,
                ),
                MissionStep(
                    "return_home",
                    on_failure=FailureAction.FALLBACK,
                    fallback_id="safe_stop",
                ),
            ),
        )
    )


def _snapshot(controller: ControllerApp, clock: ManualClock, machine: AutonomyStateMachine | None):
    return build_robot_dashboard_snapshot(
        controller,
        RobotId.R2,
        now_ms=clock.ms,
        autonomy=machine,
    )


def test_unconfigured_runtime_stays_explicitly_unknown_without_fabricated_mission(tmp_path: Path) -> None:
    controller, clock = _controller(tmp_path)
    serial = controller.serial
    assert serial is not None
    writes_before = tuple(serial.writes)

    screen = build_autonomy_screen_snapshot(_snapshot(controller, clock, None))

    assert screen.controller_configured is True
    assert screen.autonomy_configured is False
    assert screen.state_id == "NOT_CONFIGURED"
    assert screen.status == "NO_AUTONOMY_MACHINE_IN_SHARED_RUNTIME"
    assert screen.mission_id is None
    assert screen.current_target is None
    assert screen.next_state == "UNKNOWN"
    assert screen.timeout_state == "NOT_CONFIGURED"
    assert screen.control_boundary == "READ_ONLY_NO_TRANSITION_OR_EXECUTOR_API"
    assert tuple(serial.writes) == writes_before


def test_running_and_retry_context_keep_policy_timeout_and_executor_semantics_separate(
    tmp_path: Path,
) -> None:
    controller, clock = _controller(tmp_path)
    machine = _machine()
    machine.prepare(10, required_nodes_ready=True, safety_ready=True)
    machine.confirm_explicit_arm(20, confirmed=True)
    machine.start(30, explicit_start=True)

    clock.ms = 35
    running = build_autonomy_screen_snapshot(_snapshot(controller, clock, machine))
    assert running.state_id == "RUNNING"
    assert running.state_name == "Running"
    assert running.status == "MISSION_STEP_RUNNING"
    assert running.mission_id == "field_mission"
    assert running.step_position == 1
    assert running.step_count == 2
    assert running.current_target is None
    assert running.next_step == "return_home"
    assert running.attempt == 1
    assert running.max_retries == 1
    assert running.failure_action == "SKIP"
    assert running.next_state == "success=RUNNING | failure=RETRY_WAIT"
    assert running.timeout_state == "NOT_CONFIGURED_IN_MISSION_STEP_CONTRACT"
    assert running.hold_context == "NONE_RECORDED_IN_SNAPSHOT"

    machine.record_step_failure(40, "temporary blockage")
    clock.ms = 100
    retry = build_autonomy_screen_snapshot(_snapshot(controller, clock, machine))
    assert retry.state_id == "RETRY_WAIT"
    assert retry.retry_deadline_ms == 240
    assert retry.retry_remaining_ms == 140
    assert retry.next_state == "RUNNING"
    assert "LAST_RETAINED_HOLD_REQUESTED@40ms" in retry.hold_context
    assert "EXECUTOR_CONFIRMATION=UNKNOWN" in retry.hold_context
    assert retry.executor_confirmation == "UNKNOWN_NOT_RETAINED_BY_STATE_MACHINE"


def test_skip_fallback_stop_and_blocked_reasons_are_retained_without_direct_actions(
    tmp_path: Path,
) -> None:
    controller, clock = _controller(tmp_path)
    machine = _machine()
    machine.prepare(0, required_nodes_ready=True, safety_ready=True)
    machine.confirm_explicit_arm(1, confirmed=True)
    machine.start(2, explicit_start=True)
    machine.record_step_failure(10, "first failure")
    machine.tick(210)
    machine.record_step_failure(220, "retry exhausted")

    clock.ms = 221
    skipped = build_autonomy_screen_snapshot(_snapshot(controller, clock, machine))
    assert skipped.state_id == "RUNNING"
    assert skipped.current_step == "return_home"
    assert skipped.skipped_steps == ("collect_block",)
    assert skipped.failure_action == "FALLBACK"
    assert skipped.configured_fallback_id == "safe_stop"
    assert skipped.active_fallback_id is None
    assert "step_skipped" in skipped.hold_context

    machine.record_step_failure(230, "route blocked")
    clock.ms = 231
    fallback = build_autonomy_screen_snapshot(_snapshot(controller, clock, machine))
    assert fallback.state_id == "FALLBACK"
    assert fallback.current_target is None
    assert fallback.active_fallback_id == "safe_stop"
    assert fallback.next_state == "COMPLETED | STOPPED"

    machine.record_fallback_result(240, success=False, reason="fallback failed")
    clock.ms = 241
    stopped = build_autonomy_screen_snapshot(_snapshot(controller, clock, machine))
    assert stopped.state_id == "STOPPED"
    assert stopped.terminal_reason == "fallback failed"
    assert stopped.blocked_reason is None
    assert "LAST_RETAINED_STOP_REQUESTED@240ms" in stopped.stop_context
    assert "EXECUTOR_CONFIRMATION=UNKNOWN" in stopped.stop_context


def test_r1_r2_fleet_snapshots_do_not_copy_autonomy_state(tmp_path: Path) -> None:
    controller, clock = _controller(tmp_path)
    r2_machine = _machine(RobotId.R2)
    r2_machine.prepare(0, required_nodes_ready=True, safety_ready=True)
    r2 = build_robot_dashboard_snapshot(
        controller,
        RobotId.R2,
        now_ms=clock.ms,
        autonomy=r2_machine,
    )
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=clock.ms)

    r1_screen = build_autonomy_screen_snapshot(fleet.robot(RobotId.R1))
    r2_screen = build_autonomy_screen_snapshot(fleet.robot(RobotId.R2))
    assert r1_screen.controller_configured is False
    assert r1_screen.autonomy_configured is False
    assert r1_screen.state_id == "NOT_CONFIGURED"
    assert r2_screen.controller_configured is True
    assert r2_screen.autonomy_configured is True
    assert r2_screen.state_id == "READY_DISARMED"


def test_shared_snapshot_bounds_recent_autonomy_events(tmp_path: Path) -> None:
    controller, clock = _controller(tmp_path)
    machine = _machine()
    for timestamp in range(25):
        machine.confirm_explicit_arm(timestamp, confirmed=False)

    snapshot = _snapshot(controller, clock, machine)

    assert len(snapshot.autonomy.recent_events) == 20
    assert snapshot.autonomy.recent_events[0].timestamp_ms == 5
    assert snapshot.autonomy.recent_events[-1].timestamp_ms == 24
