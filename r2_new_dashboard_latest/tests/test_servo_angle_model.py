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
from pc_controller.gui_servo_angle_model import ServoAngleDraftStore
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


def test_angle_draft_separates_current_pending_saved_and_revert(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    drafts = ServoAngleDraftStore()

    initial = drafts.build(diagnostic)
    assert initial.workflow_state == "READ_ONLY_AUDIT"
    assert initial.pending_count == 0
    assert initial.rows[0].current_min_us == 500
    assert initial.rows[0].saved_max_angle_deg == 135.0

    staged = drafts.stage(
        diagnostic,
        0,
        min_us_text="550",
        max_us_text="2450",
        min_angle_deg_text="-120",
        max_angle_deg_text="125.5",
    )
    row = staged.rows[0]
    assert staged.workflow_state == "LOCAL_DRAFT_READY"
    assert staged.pending_count == 1
    assert row.current_min_us == 500
    assert row.saved_max_us == 2500
    assert row.pending_min_us == 550
    assert row.pending_max_us == 2450
    assert row.pending_min_angle_deg == -120.0
    assert row.pending_max_angle_deg == 125.5
    assert row.validation == "PENDING_VALID_LOCAL_ONLY"
    assert row.revert_state == "AVAILABLE_LOCAL_ONLY"
    assert row.apply_state == "BLOCKED_NO_CONTROLLER_API"
    assert row.save_state == "BLOCKED_NO_CONTROLLER_API"
    assert row.hardware_validation_state == "REQUIRED_BEFORE_APPLY"
    assert not hasattr(drafts, "apply")
    assert not hasattr(drafts, "save")

    assert drafts.revert("R2", 0) is True
    reverted = drafts.build(diagnostic)
    assert reverted.pending_count == 0
    assert reverted.rows[0].pending_min_us is None
    assert drafts.revert("R2", 0) is False


def test_invalid_format_pulse_and_angle_ranges_remain_visible(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    drafts = ServoAngleDraftStore()

    invalid_format = drafts.stage(
        diagnostic, 0,
        min_us_text="500", max_us_text="bad", min_angle_deg_text="-90", max_angle_deg_text="90",
    )
    assert invalid_format.workflow_state == "LOCAL_DRAFT_INVALID"
    assert invalid_format.rows[0].validation == "PENDING_INVALID_FORMAT"
    assert invalid_format.rows[0].pending_max_us_text == "bad"

    invalid_pulse = drafts.stage(
        diagnostic, 0,
        min_us_text="1490", max_us_text="2500", min_angle_deg_text="-90", max_angle_deg_text="90",
    )
    assert invalid_pulse.rows[0].validation == "PENDING_INVALID_PULSE_RANGE"

    invalid_angle = drafts.stage(
        diagnostic, 0,
        min_us_text="550", max_us_text="2450", min_angle_deg_text="0", max_angle_deg_text="90",
    )
    assert invalid_angle.rows[0].validation == "PENDING_INVALID_ANGLE_RANGE"
    assert invalid_angle.rows[0].apply_state == "BLOCKED_NO_CONTROLLER_API"


def test_angle_draft_stales_when_mapping_base_changes(tmp_path: Path) -> None:
    diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    drafts = ServoAngleDraftStore()
    drafts.stage(
        diagnostic, 0,
        min_us_text="550", max_us_text="2450", min_angle_deg_text="-120", max_angle_deg_text="120",
    )
    changed_servo = replace(diagnostic.servos[0], current_trim_deg=1.0, direction_inverted=False)
    changed = replace(diagnostic, servos=(changed_servo,) + diagnostic.servos[1:])

    stale = drafts.build(changed)
    assert stale.workflow_state == "LOCAL_DRAFT_INVALID"
    assert stale.rows[0].validation == "STALE_BASE_CONFIG"
    assert stale.rows[0].pending_min_angle_deg_text == "-120"


def test_angle_drafts_are_isolated_by_robot_and_identical_values_clear(tmp_path: Path) -> None:
    r2_diagnostic = build_calibration_diagnostic_snapshot(_robot_snapshot(tmp_path))
    r1_diagnostic = replace(r2_diagnostic, robot_id="R1")
    drafts = ServoAngleDraftStore()

    drafts.stage(
        r2_diagnostic, 2,
        min_us_text="600", max_us_text="2400", min_angle_deg_text="-110", max_angle_deg_text="115",
    )
    assert drafts.build(r2_diagnostic).pending_count == 1
    assert drafts.build(r1_diagnostic).pending_count == 0

    cleared = drafts.stage(
        r2_diagnostic, 2,
        min_us_text="500", max_us_text="2500", min_angle_deg_text="-135", max_angle_deg_text="135",
    )
    assert cleared.pending_count == 0


def test_unbound_robot_cannot_create_an_angle_draft(tmp_path: Path) -> None:
    robot = _robot_snapshot(tmp_path)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (robot,), now_ms=robot.timestamp_ms)
    diagnostic = build_calibration_diagnostic_snapshot(fleet.selected)
    drafts = ServoAngleDraftStore()

    assert drafts.build(diagnostic).rows == ()
    with pytest.raises(ValueError, match="unbound robot"):
        drafts.stage(
            diagnostic, 0,
            min_us_text="500", max_us_text="2500", min_angle_deg_text="-135", max_angle_deg_text="135",
        )
