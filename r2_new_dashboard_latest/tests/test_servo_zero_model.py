from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import pytest

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_calibration_model import build_calibration_diagnostic_snapshot
from pc_controller.gui_model import build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.gui_servo_zero_model import ServoZeroDraftStore
from pc_controller.node_inventory import NodeRequirement
from pc_controller.protocol import encode_message, hello_message


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


def _robot_snapshot(tmp_path: Path):
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


def test_local_draft_keeps_current_pending_saved_and_revert_separate(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    drafts = ServoZeroDraftStore()

    initial = drafts.build(diagnostic)
    assert initial.workflow_state == "READ_ONLY_AUDIT"
    assert initial.pending_count == 0
    assert initial.rows[0].current_center_us == 1490
    assert initial.rows[0].saved_center_us == 1490
    assert initial.rows[0].pending_center_us is None

    staged = drafts.stage(
        diagnostic,
        0,
        center_us_text="1505",
        trim_deg_text="1.25",
    )
    row = staged.rows[0]
    assert staged.workflow_state == "LOCAL_DRAFT_READY"
    assert staged.pending_count == 1
    assert row.current_center_us == 1490
    assert row.saved_center_us == 1490
    assert row.pending_center_us == 1505
    assert row.pending_trim_deg == 1.25
    assert row.validation == "PENDING_VALID_LOCAL_ONLY"
    assert row.revert_state == "AVAILABLE_LOCAL_ONLY"
    assert row.apply_state == "BLOCKED_NO_CONTROLLER_API"
    assert row.save_state == "BLOCKED_NO_CONTROLLER_API"

    assert drafts.revert("R2", 0) is True
    reverted = drafts.build(diagnostic)
    assert reverted.pending_count == 0
    assert reverted.rows[0].pending_center_us is None
    assert reverted.rows[0].revert_state == "NO_PENDING_CHANGE"
    assert drafts.revert("R2", 0) is False


def test_invalid_and_stale_drafts_remain_visible_but_blocked(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    drafts = ServoZeroDraftStore()

    invalid = drafts.stage(
        diagnostic,
        0,
        center_us_text="2500",
        trim_deg_text="not-a-number",
    )
    assert invalid.workflow_state == "LOCAL_DRAFT_INVALID"
    assert invalid.rows[0].validation == "PENDING_INVALID_FORMAT"
    assert invalid.rows[0].pending_center_us_text == "2500"
    assert invalid.rows[0].pending_trim_deg_text == "not-a-number"
    assert invalid.rows[0].apply_state == "BLOCKED_NO_CONTROLLER_API"

    drafts.stage(diagnostic, 0, center_us_text="1505", trim_deg_text="1.0")
    changed_servo = replace(
        diagnostic.servos[0],
        current_center_us=1495,
        saved_center_us=1495,
    )
    changed = replace(diagnostic, servos=(changed_servo,) + diagnostic.servos[1:])
    stale = drafts.build(changed)
    assert stale.workflow_state == "LOCAL_DRAFT_INVALID"
    assert stale.rows[0].validation == "STALE_BASE_CONFIG"
    assert stale.rows[0].pending_center_us_text == "1505"


def test_drafts_are_isolated_by_robot_and_periodic_snapshot_rebuild(tmp_path: Path) -> None:
    r2_diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    r1_diagnostic = replace(r2_diagnostic, robot_id="R1")
    drafts = ServoZeroDraftStore()

    drafts.stage(r2_diagnostic, 2, center_us_text="1600", trim_deg_text="-0.5")
    assert drafts.build(r2_diagnostic).pending_count == 1
    assert drafts.build(r2_diagnostic).rows[2].pending_center_us == 1600
    assert drafts.build(r1_diagnostic).pending_count == 0
    assert all(not row.has_pending for row in drafts.build(r1_diagnostic).rows)


def test_unbound_robot_cannot_create_a_draft(tmp_path: Path) -> None:
    robot = _robot_snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (robot,), now_ms=robot.timestamp_ms)
    diagnostic = build_calibration_diagnostic_snapshot(fleet.selected)
    drafts = ServoZeroDraftStore()

    assert drafts.build(diagnostic).rows == ()
    with pytest.raises(ValueError, match="unbound robot"):
        drafts.stage(diagnostic, 0, center_us_text="1500", trim_deg_text="0")
