from __future__ import annotations

import json
from pathlib import Path

from pc_controller.autonomy import RobotId
from pc_controller.competition import CompetitionLogWriter, CompetitionState
from pc_controller.gui_logs_model import (
    UNKNOWN,
    build_logs_screen_snapshot,
    load_competition_log_source,
)


def _example_log(path: Path) -> Path:
    writer = CompetitionLogWriter(path, "session-gui-030")
    writer.append(0, "competition_enabled", CompetitionState.PRECHECK)
    writer.append(
        10,
        "competition_step_result",
        CompetitionState.ACTIVE,
        robot_id=RobotId.R1,
        safety_state="SAFE",
        armed=False,
        reason="retry requested",
        data={
            "actions": ["HOLD_REQUESTED", "RETRY_SCHEDULED"],
            "retry_count": 1,
            "fault_flags": 4,
            "node_id": "mcb44_drive_main",
        },
    )
    writer.append(
        20,
        "competition_step_result",
        CompetitionState.STOPPED,
        robot_id=RobotId.R2,
        reason="R2 complete",
    )
    writer.append(30, "session_finalized", CompetitionState.POST_COMPETITION)
    writer.close()
    return path


def test_unconfigured_source_is_explicit_and_remote_transfer_remains_disabled() -> None:
    source = load_competition_log_source(None)
    screen = build_logs_screen_snapshot(source, RobotId.R1)

    assert screen.source_status == "NOT_CONFIGURED"
    assert screen.validation_state == "NO_EXPLICIT_LOCAL_LOG"
    assert screen.entries == ()
    assert screen.remote_sync_status == "AWAITING_REMOTE_CONFIGURATION"
    assert screen.remote_transfer_performed is False


def test_valid_log_preserves_session_state_and_robot_scope_without_inventing_fields(
    tmp_path: Path,
) -> None:
    source = load_competition_log_source(_example_log(tmp_path / "competition.jsonl"))
    r1 = build_logs_screen_snapshot(source, RobotId.R1)
    r2 = build_logs_screen_snapshot(source, RobotId.R2)

    assert source.source_status == "LOADED"
    assert source.validation_state == "VALIDATED_LOCAL_COMPETITION_JSONL"
    assert source.session_id == "session-gui-030"
    assert source.total_record_count == 4
    assert source.final_competition_state == "POST_COMPETITION"
    assert source.finalized is True
    assert [entry.sequence for entry in r1.entries] == [1, 2, 4]
    assert [entry.sequence for entry in r2.entries] == [1, 3, 4]
    assert all(entry.robot_id != RobotId.R2 for entry in r1.entries)
    assert all(entry.robot_id != RobotId.R1 for entry in r2.entries)

    first = r1.entries[0]
    assert first.scope == "FLEET"
    assert first.state_transition == "FIRST_RECORDED_STATE=PRECHECK"
    assert first.safety_state == UNKNOWN
    assert first.fault_context == UNKNOWN
    assert first.retry_context == UNKNOWN
    assert first.node_context == UNKNOWN

    retry = r1.entries[1]
    assert retry.scope == "R1"
    assert retry.state_transition == "PRECHECK -> ACTIVE"
    assert retry.safety_state == "SAFE"
    assert retry.armed_state == "DISARMED"
    assert retry.fault_context == '{"fault_flags":4}'
    assert retry.retry_context == '{"actions":["RETRY_SCHEDULED"],"retry_count":1}'
    assert retry.node_context == '{"node_id":"mcb44_drive_main"}'
    assert retry.reason == "retry requested"


def test_invalid_or_nonlocal_source_fails_closed_without_partial_rows(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "bad",
                "sequence": 2,
                "timestamp_ms": 0,
                "event": "bad",
                "competition_state": "CREATED",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    invalid_source = load_competition_log_source(invalid)
    remote_source = load_competition_log_source("https://example.invalid/competition.jsonl")

    assert invalid_source.source_status == "INVALID"
    assert invalid_source.events == ()
    assert "sequence mismatch" in invalid_source.validation_message
    assert remote_source.source_status == "INVALID"
    assert remote_source.events == ()
    assert "local filesystem path" in remote_source.validation_message


def test_invalid_optional_robot_scope_is_not_relabelled_as_fleet(tmp_path: Path) -> None:
    path = tmp_path / "invalid-robot.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "bad-scope",
                "sequence": 1,
                "timestamp_ms": 0,
                "event": "event",
                "competition_state": "CREATED",
                "robot_id": "R3",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    source = load_competition_log_source(path)

    assert source.source_status == "INVALID"
    assert source.events == ()
    assert "robot_id invalid" in source.validation_message


def test_source_and_screen_retention_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "bounded.ndjson"
    writer = CompetitionLogWriter(path, "bounded")
    for timestamp_ms in range(8):
        writer.append(timestamp_ms, f"event-{timestamp_ms}", CompetitionState.ACTIVE)
    writer.close()

    source = load_competition_log_source(path, max_retained_records=5)
    screen = build_logs_screen_snapshot(source, RobotId.R1, max_displayed_records=3)

    assert source.total_record_count == 8
    assert source.retained_record_count == 5
    assert source.truncated_record_count == 3
    assert [entry.sequence for entry in source.events] == [4, 5, 6, 7, 8]
    assert [entry.sequence for entry in screen.entries] == [6, 7, 8]
    assert screen.hidden_matching_record_count == 2


def test_invalid_bounds_and_robot_id_are_rejected() -> None:
    source = load_competition_log_source(None)

    try:
        load_competition_log_source(None, max_retained_records=0)
    except ValueError as exc:
        assert "max_retained_records" in str(exc)
    else:
        raise AssertionError("invalid retained bound was accepted")

    try:
        build_logs_screen_snapshot(source, "R1")  # type: ignore[arg-type]
    except ValueError as exc:
        assert "robot_id" in str(exc)
    else:
        raise AssertionError("invalid robot ID was accepted")
