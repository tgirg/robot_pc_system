from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pytest

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_direction_model import DirectionDraftStore, transform_for_logical_front
from pc_controller.gui_model import build_robot_dashboard_snapshot


class ManualClock:
    def __init__(self) -> None:
        self.ms = 1_000

    def __call__(self) -> int:
        return self.ms


def _args(config_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir),
        simulate=False,
        fake_esp32=True,
        fake_trace=False,
        joystick=False,
        once=True,
        auto_reconnect=True,
        reconnect_interval=0.01,
        reconnect_handshake_timeout=0.1,
        port=None,
        baudrate=115200,
        serial_timeout=0.01,
        list_controllers=False,
        controller_debug=0.0,
        list_nodes=False,
        node_id=None,
        node_role="drive",
        node_manifest=None,
        serial_trace=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


def _snapshot(tmp_path: Path, robot_id: RobotId = RobotId.R2):
    config_dir = tmp_path / robot_id.value
    ensure_config_files(config_dir)
    clock = ManualClock()
    controller = ControllerApp(_args(config_dir), now_ms=clock)
    return build_robot_dashboard_snapshot(controller, robot_id, now_ms=clock.ms)


def _current_motor(robot) -> tuple[bool, ...]:
    return tuple(bool(wheel.motor_inverted) for wheel in robot.wheels)


def _current_servo(robot) -> tuple[bool, ...]:
    return tuple(bool(wheel.servo_inverted) for wheel in robot.wheels)


def test_direction_audit_keeps_semantic_layers_separate(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    state = DirectionDraftStore().build(robot)

    assert state.workflow_state == "READ_ONLY_AUDIT"
    assert state.validation == "SOURCE_CONFIG_VALID"
    assert [(row.axis_index, row.current_inverted, row.pending_inverted, row.saved_inverted) for row in state.controller_rows] == [
        (1, True, None, True),
        (0, True, None, True),
        (2, True, None, True),
    ]
    assert state.machine_x_positive == "FORWARD"
    assert state.machine_y_positive == "LEFT"
    assert state.machine_omega_positive == "CCW"
    assert state.pivot_direction_inverted is False
    assert state.current_logical_front == "FRONT"
    assert state.pending_logical_front is None
    assert state.saved_logical_front == "FRONT"
    assert all(row.current_motor_inverted is True for row in state.wheel_rows)
    assert all(row.current_servo_inverted is True for row in state.wheel_rows)
    assert state.preview.validation == "PREVIEW_VALID_LOCAL_ONLY"
    assert state.preview.corrected_controller.vx is not None
    assert state.preview.corrected_controller.vx < 0.0
    assert state.apply_state == "BLOCKED_NO_CONTROLLER_API"
    assert state.output_state == "LOCAL_PREVIEW_ONLY_NO_OUTPUT"


@pytest.mark.parametrize(
    ("front", "expected"),
    (
        ("FRONT", (2.0, 3.0)),
        ("RIGHT", (3.0, -2.0)),
        ("REAR", (-2.0, -3.0)),
        ("LEFT", (-3.0, 2.0)),
    ),
)
def test_logical_front_rotates_only_translation(front: str, expected: tuple[float, float]) -> None:
    assert transform_for_logical_front(2.0, 3.0, front) == expected


def test_direction_draft_previews_front_and_independent_inversions(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = DirectionDraftStore()
    motors = list(_current_motor(robot))
    servos = list(_current_servo(robot))
    motors[0] = False
    servos[1] = False

    state = store.stage(
        robot,
        invert_vx=False,
        invert_vy=True,
        invert_omega=True,
        logical_front="RIGHT",
        motor_inverted=motors,
        servo_inverted=servos,
        preview_input=(0.6, 0.25, 0.2),
    )

    assert state.workflow_state == "LOCAL_DRAFT_READY"
    assert state.validation == "PENDING_VALID_LOCAL_ONLY"
    assert state.pending_count == 4
    assert state.controller_rows[0].pending_inverted is False
    assert state.controller_rows[1].pending_inverted is True
    assert state.pending_logical_front == "RIGHT"
    assert state.saved_logical_front == "FRONT"
    assert state.wheel_rows[0].pending_motor_inverted is False
    assert state.wheel_rows[1].pending_servo_inverted is False
    assert state.wheel_rows[0].saved_motor_inverted is True
    assert state.wheel_rows[1].saved_servo_inverted is True
    machine = state.preview.machine_relative
    transformed = state.preview.logical_front_transformed
    assert transformed.vx == pytest.approx(machine.vy)
    assert transformed.vy == pytest.approx(-machine.vx)
    assert transformed.omega == pytest.approx(machine.omega)
    assert state.preview.final_command_preview == transformed
    assert "+logical X -> -machine Y" in state.affected_axes

    assert store.build(robot).pending_count == 4
    assert store.revert("R2") is True
    assert store.build(robot).pending_count == 0


def test_invalid_front_and_base_change_fail_closed_locally(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = DirectionDraftStore()
    state = store.stage(
        robot,
        invert_vx=True,
        invert_vy=True,
        invert_omega=True,
        logical_front="UPSIDE_DOWN",
        motor_inverted=_current_motor(robot),
        servo_inverted=_current_servo(robot),
    )
    assert state.workflow_state == "LOCAL_DRAFT_INVALID"
    assert state.validation == "PENDING_INVALID_LOGICAL_FRONT"
    assert state.preview.validation == "PREVIEW_VALID_LOCAL_ONLY"
    assert state.preview.logical_front == "FRONT"

    store.revert("R2")
    store.stage(
        robot,
        invert_vx=False,
        invert_vy=True,
        invert_omega=True,
        logical_front="LEFT",
        motor_inverted=_current_motor(robot),
        servo_inverted=_current_servo(robot),
    )
    changed_mapping = replace(robot.controller_mapping, deadzone=0.2)
    changed_robot = replace(robot, controller_mapping=changed_mapping)
    stale = store.build(changed_robot)
    assert stale.workflow_state == "LOCAL_DRAFT_INVALID"
    assert stale.validation == "STALE_BASE_CONFIG"
    assert stale.revert_state == "AVAILABLE_LOCAL_ONLY"


def test_direction_drafts_are_isolated_by_robot_and_periodic_build(tmp_path: Path) -> None:
    r1 = _snapshot(tmp_path, RobotId.R1)
    r2 = _snapshot(tmp_path, RobotId.R2)
    store = DirectionDraftStore()
    store.stage(
        r2,
        invert_vx=False,
        invert_vy=True,
        invert_omega=True,
        logical_front="REAR",
        motor_inverted=_current_motor(r2),
        servo_inverted=_current_servo(r2),
    )

    assert store.build(r1).pending_count == 0
    assert store.build(r2).pending_count == 2
    assert store.build(r2).pending_logical_front == "REAR"


def test_staging_identical_direction_values_clears_pending(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    store = DirectionDraftStore()
    store.stage(
        robot,
        invert_vx=False,
        invert_vy=True,
        invert_omega=True,
        logical_front="FRONT",
        motor_inverted=_current_motor(robot),
        servo_inverted=_current_servo(robot),
    )
    assert store.build(robot).pending_count == 1

    state = store.stage(
        robot,
        invert_vx=True,
        invert_vy=True,
        invert_omega=True,
        logical_front="FRONT",
        motor_inverted=_current_motor(robot),
        servo_inverted=_current_servo(robot),
    )
    assert state.pending_count == 0
    assert state.revert_state == "NO_PENDING_CHANGE"


def test_unbound_robot_cannot_create_direction_draft(tmp_path: Path) -> None:
    robot = _snapshot(tmp_path)
    from pc_controller.gui_model import build_fleet_dashboard_snapshot

    unbound = build_fleet_dashboard_snapshot(RobotId.R1, (robot,), now_ms=robot.timestamp_ms).selected
    store = DirectionDraftStore()
    state = store.build(unbound)
    assert state.workflow_state == "UNBOUND"
    assert state.controller_rows[0].axis_index is None
    assert state.wheel_rows == ()
    with pytest.raises(ValueError, match="unbound"):
        store.stage(
            unbound,
            invert_vx=True,
            invert_vy=True,
            invert_omega=True,
            logical_front="FRONT",
            motor_inverted=(),
            servo_inverted=(),
        )
