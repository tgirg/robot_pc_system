from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pytest

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.gui_parameter_model import PARAMETER_SPECS, ParameterDraftStore


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


def _snapshot(tmp_path: Path, robot_id: RobotId = RobotId.R2):
    ensure_config_files(tmp_path)
    clock = ManualClock()
    controller = ControllerApp(_args(tmp_path), now_ms=clock)
    return build_robot_dashboard_snapshot(controller, robot_id, now_ms=clock.ms)


def _row(state, key: str):
    return next(row for row in state.rows if row.key == key)


def test_parameter_source_audit_uses_only_authoritative_runtime_clamps(tmp_path: Path) -> None:
    state = ParameterDraftStore().build(_snapshot(tmp_path))

    assert state.workflow_state == "READ_ONLY_AUDIT"
    assert state.pending_count == 0
    assert state.invalid_count == 0
    assert tuple(row.key for row in state.rows) == tuple(spec.key for spec in PARAMETER_SPECS)
    assert _row(state, "controller.deadzone").current_value == pytest.approx(0.12)
    assert _row(state, "controller.deadzone").maximum == pytest.approx(0.95)
    assert _row(state, "controller.linear_scale").maximum == pytest.approx(1.0)
    assert _row(state, "motion.open_loop_max_pwm").current_value == pytest.approx(120.0)
    assert _row(state, "motion.open_loop_max_pwm").maximum == pytest.approx(1023.0)
    assert all(row.pending_value is None for row in state.rows)
    assert all(row.apply_state == "BLOCKED_NO_CONTROLLER_API" for row in state.rows)
    assert state.save_state == "BLOCKED_NO_CONTROLLER_API"
    assert state.output_state == "LOCAL_DRAFT_ONLY_NO_CONFIG_OR_HARDWARE_OUTPUT"


def test_valid_parameter_drafts_keep_current_pending_and_saved_separate(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = ParameterDraftStore()
    state = store.stage(robot, "controller.linear_scale", "0.25")
    state = store.stage(robot, "motion.open_loop_max_pwm", 240)

    assert state.workflow_state == "LOCAL_DRAFT_READY"
    assert state.pending_count == 2
    linear = _row(state, "controller.linear_scale")
    assert linear.current_value == pytest.approx(0.12)
    assert linear.pending_value == pytest.approx(0.25)
    assert linear.saved_controller_loaded_value == pytest.approx(0.12)
    assert linear.validation == "PENDING_VALID_LOCAL_ONLY"
    pwm = _row(state, "motion.open_loop_max_pwm")
    assert pwm.current_value == pytest.approx(120.0)
    assert pwm.pending_value == pytest.approx(240.0)
    assert pwm.saved_controller_loaded_value == pytest.approx(120.0)

    assert store.build(robot).pending_count == 2
    assert store.revert("R2", "controller.linear_scale") is True
    assert store.build(robot).pending_count == 1
    assert store.revert("R2") is True
    assert store.build(robot).pending_count == 0


def test_invalid_and_stale_parameter_drafts_fail_closed_locally(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = ParameterDraftStore()
    invalid = store.stage(robot, "controller.deadzone", "not-a-number")
    assert invalid.workflow_state == "LOCAL_DRAFT_INVALID"
    assert _row(invalid, "controller.deadzone").validation == "PENDING_INVALID_FORMAT"

    store.revert("R2")
    invalid = store.stage(robot, "motion.pivot_max_pwm", 2048)
    assert _row(invalid, "motion.pivot_max_pwm").validation == "PENDING_OUT_OF_RANGE"

    store.revert("R2")
    invalid = store.stage(robot, "motion.open_loop_max_pwm", 120.9)
    assert _row(invalid, "motion.open_loop_max_pwm").validation == "PENDING_REQUIRES_INTEGER"

    store.revert("R2")
    store.stage(robot, "controller.angular_scale", 0.5)
    unrelated_mapping = replace(robot.controller_mapping, deadzone=0.2)
    unrelated = store.build(replace(robot, controller_mapping=unrelated_mapping))
    assert unrelated.workflow_state == "LOCAL_DRAFT_READY"
    assert _row(unrelated, "controller.angular_scale").validation == "PENDING_VALID_LOCAL_ONLY"

    changed_mapping = replace(robot.controller_mapping, angular_scale=0.4)
    stale = store.build(replace(robot, controller_mapping=changed_mapping))
    assert stale.workflow_state == "LOCAL_DRAFT_INVALID"
    assert _row(stale, "controller.angular_scale").validation == "STALE_BASE_CONFIG"


def test_runtime_clamped_source_is_visible_instead_of_hidden(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    changed_mapping = replace(robot.controller_mapping, linear_scale=1.5)
    changed_motion = replace(robot.motion_parameters, open_loop_max_pwm=1400.0)
    state = ParameterDraftStore().build(
        replace(robot, controller_mapping=changed_mapping, motion_parameters=changed_motion)
    )

    linear = _row(state, "controller.linear_scale")
    assert linear.saved_controller_loaded_value == pytest.approx(1.5)
    assert linear.current_value == pytest.approx(1.0)
    assert linear.validation == "SOURCE_RUNTIME_CLAMPED"
    pwm = _row(state, "motion.open_loop_max_pwm")
    assert pwm.saved_controller_loaded_value == pytest.approx(1400.0)
    assert pwm.current_value == pytest.approx(1023.0)
    assert pwm.validation == "SOURCE_RUNTIME_CLAMPED"


def test_pwm_effective_values_match_controller_integer_and_zero_fallback_semantics(
    tmp_path: Path,
) -> None:
    robot = _snapshot(tmp_path)
    controller = ControllerApp.__new__(ControllerApp)

    def assert_effective(open_loop: float, pivot: float) -> None:
        motion = {"open_loop_max_pwm": open_loop, "pivot_max_pwm": pivot}
        open_limit = controller._pwm_limit(motion, "open_loop_max_pwm", 120)
        expected_open = open_limit if open_limit > 0 else 1023
        pivot_limit = controller._pwm_limit(motion, "pivot_max_pwm", expected_open)
        expected_pivot = pivot_limit if pivot_limit > 0 else expected_open
        state = ParameterDraftStore().build(
            replace(
                robot,
                motion_parameters=replace(
                    robot.motion_parameters,
                    open_loop_max_pwm=open_loop,
                    pivot_max_pwm=pivot,
                ),
            )
        )
        assert _row(state, "motion.open_loop_max_pwm").current_value == pytest.approx(expected_open)
        assert _row(state, "motion.pivot_max_pwm").current_value == pytest.approx(expected_pivot)

    assert_effective(0.0, 0.0)
    assert_effective(120.9, 0.0)
    assert_effective(120.9, 60.9)

    state = ParameterDraftStore().build(
        replace(
            robot,
            motion_parameters=replace(
                robot.motion_parameters,
                open_loop_max_pwm=0.0,
                pivot_max_pwm=0.0,
            ),
        )
    )
    open_row = _row(state, "motion.open_loop_max_pwm")
    assert open_row.saved_controller_loaded_value == pytest.approx(0.0)
    assert open_row.current_value == pytest.approx(1023.0)
    assert open_row.validation == "SOURCE_RUNTIME_CLAMPED"
    assert "0 falls back to 1023" in open_row.source
    assert "0 falls back to open-loop limit" in _row(state, "motion.pivot_max_pwm").source


def test_pivot_zero_draft_tracks_its_open_loop_fallback_dependency(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = ParameterDraftStore()
    state = store.stage(robot, "motion.pivot_max_pwm", 60)
    changed_motion = replace(robot.motion_parameters, open_loop_max_pwm=200.0)
    unchanged = store.build(replace(robot, motion_parameters=changed_motion))
    assert _row(unchanged, "motion.pivot_max_pwm").validation == "PENDING_VALID_LOCAL_ONLY"

    store.revert("R2")
    state = store.stage(robot, "motion.pivot_max_pwm", 0)
    assert _row(state, "motion.pivot_max_pwm").validation == "PENDING_VALID_LOCAL_ONLY"

    stale = store.build(replace(robot, motion_parameters=changed_motion))
    assert _row(stale, "motion.pivot_max_pwm").validation == "STALE_BASE_CONFIG"


def test_parameter_drafts_are_isolated_and_unbound_is_blocked(tmp_path: Path) -> None:
    r1 = _snapshot(tmp_path / "r1", RobotId.R1)
    r2 = _snapshot(tmp_path / "r2", RobotId.R2)
    store = ParameterDraftStore()
    store.stage(r2, "controller.deadzone", 0.2)

    assert store.build(r1).pending_count == 0
    assert store.build(r2).pending_count == 1

    unbound = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=r2.timestamp_ms).selected
    state = store.build(unbound)
    assert state.workflow_state == "UNBOUND"
    assert all(row.current_value is None for row in state.rows)
    with pytest.raises(ValueError, match="unbound"):
        store.stage(unbound, "controller.deadzone", 0.2)


def test_staging_controller_loaded_value_clears_one_pending_key(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = ParameterDraftStore()
    store.stage(robot, "controller.deadzone", 0.2)
    assert store.build(robot).pending_count == 1

    state = store.stage(robot, "controller.deadzone", 0.12)
    assert state.pending_count == 0
    assert state.revert_state == "NO_PENDING_CHANGE"
