from __future__ import annotations

from pathlib import Path

import pytest

from pc_controller.autonomy import AutonomyState, RobotId
from pc_controller.competition import CompetitionLogWriter, CompetitionState
from pc_controller.gui_logs_model import UNKNOWN, load_competition_log_source
from pc_controller.gui_replay_model import (
    ReplayCursorStore,
    build_replay_screen_snapshot,
)


def _replay_log(path: Path) -> Path:
    writer = CompetitionLogWriter(path, "replay-session")
    writer.append(0, "competition_enabled", CompetitionState.PRECHECK)
    writer.append(
        10,
        "r1_running",
        CompetitionState.ACTIVE,
        robot_id=RobotId.R1,
        autonomy_state=AutonomyState.RUNNING,
        safety_state="NORMAL",
        armed=True,
        data={"actions": ["RUN_STEP"], "node_id": "mcb44_drive_main"},
    )
    writer.append(
        20,
        "r2_running",
        CompetitionState.ACTIVE,
        robot_id=RobotId.R2,
        autonomy_state=AutonomyState.RUNNING,
        safety_state="NORMAL",
        armed=True,
    )
    writer.append(
        30,
        "r1_retry",
        CompetitionState.ACTIVE,
        robot_id=RobotId.R1,
        reason="temporary blockage",
        data={"actions": ["HOLD_REQUESTED", "RETRY_SCHEDULED"], "retry_count": 1},
    )
    writer.append(40, "competition_stopped", CompetitionState.STOPPED, reason="operator stop")
    writer.append(50, "session_finalized", CompetitionState.POST_COMPETITION)
    writer.close()
    return path


def test_replay_uses_only_selected_robot_and_fleet_records(tmp_path: Path) -> None:
    source = load_competition_log_source(_replay_log(tmp_path / "replay.jsonl"))

    r1 = build_replay_screen_snapshot(source, RobotId.R1, cursor_sequence=4)
    r2 = build_replay_screen_snapshot(source, RobotId.R2, cursor_sequence=3)

    assert [event.sequence for event in r1.timeline] == [1, 2, 4, 5, 6]
    assert [event.sequence for event in r2.timeline] == [1, 3, 5, 6]
    assert r1.current_sequence == 4
    assert r1.current_timestamp_ms == 30
    assert r1.elapsed_from_session_start_ms == 30
    assert r1.competition_state == "ACTIVE"
    assert r1.competition_event == "r1_retry"
    assert r1.autonomy_state == "RUNNING"
    assert r1.autonomy_basis == "LAST_RECORDED_FOR_R1@sequence=2"
    assert r1.safety_state == "NORMAL"
    assert r1.armed_state == "ARMED"
    assert r1.retry_context == '{"actions":["RETRY_SCHEDULED"],"retry_count":1}'
    assert r1.reason == "temporary blockage"
    assert r2.autonomy_basis == "LAST_RECORDED_FOR_R2@sequence=3"
    assert "NO_COMMAND_REEMIT_ARM" in r1.control_boundary
    assert r1.remote_transfer_performed is False


def test_fleet_events_do_not_invent_robot_recorded_state(tmp_path: Path) -> None:
    path = tmp_path / "fleet-only.ndjson"
    writer = CompetitionLogWriter(path, "fleet-only")
    writer.append(0, "enabled", CompetitionState.PRECHECK, safety_state="SAFE", armed=False)
    writer.close()
    source = load_competition_log_source(path)

    screen = build_replay_screen_snapshot(source, RobotId.R1)

    assert screen.current_scope == "FLEET"
    assert screen.safety_state == UNKNOWN
    assert screen.armed_state == UNKNOWN
    assert screen.safety_basis == "UNKNOWN_NOT_RECORDED_FOR_R1"
    assert screen.armed_basis == "UNKNOWN_NOT_RECORDED_FOR_R1"


def test_replay_cursor_store_is_local_and_r1_r2_isolated(tmp_path: Path) -> None:
    source = load_competition_log_source(_replay_log(tmp_path / "cursor.jsonl"))
    store = ReplayCursorStore(source)

    assert store.snapshot(RobotId.R1).current_sequence == 1
    assert store.snapshot(RobotId.R2).current_sequence == 1
    store.move(RobotId.R1, 2)
    assert store.snapshot(RobotId.R1).current_sequence == 4
    assert store.snapshot(RobotId.R2).current_sequence == 1
    store.last(RobotId.R2)
    assert store.snapshot(RobotId.R2).current_sequence == 6
    assert store.snapshot(RobotId.R1).current_sequence == 4
    store.first(RobotId.R1)
    assert store.snapshot(RobotId.R1).current_sequence == 1
    store.select_sequence(RobotId.R1, 5)
    assert store.snapshot(RobotId.R1).current_sequence == 5


def test_reload_preserves_available_sequence_and_resets_for_new_session(tmp_path: Path) -> None:
    first_path = _replay_log(tmp_path / "first.jsonl")
    first = load_competition_log_source(first_path)
    store = ReplayCursorStore(first)
    store.select_sequence(RobotId.R1, 4)

    store.set_source(load_competition_log_source(first_path))
    assert store.snapshot(RobotId.R1).current_sequence == 4

    second_path = tmp_path / "second.jsonl"
    writer = CompetitionLogWriter(second_path, "new-session")
    writer.append(100, "new", CompetitionState.CREATED)
    writer.close()
    store.set_source(load_competition_log_source(second_path))
    assert store.snapshot(RobotId.R1).current_sequence == 1


def test_truncated_prefix_is_explicit_and_never_backfilled(tmp_path: Path) -> None:
    source = load_competition_log_source(
        _replay_log(tmp_path / "truncated.jsonl"),
        max_retained_records=2,
    )

    screen = build_replay_screen_snapshot(source, RobotId.R1)

    assert screen.prefix_truncated is True
    assert screen.truncated_record_count == 4
    assert screen.current_sequence == 5
    assert screen.autonomy_state == UNKNOWN
    assert screen.autonomy_basis == "UNKNOWN_RETAINED_PREFIX_TRUNCATED"


def test_unconfigured_invalid_and_no_matching_sources_fail_closed(tmp_path: Path) -> None:
    unconfigured = build_replay_screen_snapshot(load_competition_log_source(None), RobotId.R1)
    invalid_path = tmp_path / "invalid.jsonl"
    invalid_path.write_text("not json\n", encoding="utf-8")
    invalid = build_replay_screen_snapshot(load_competition_log_source(invalid_path), RobotId.R1)

    assert unconfigured.availability == "NOT_CONFIGURED"
    assert unconfigured.timeline == ()
    assert invalid.availability == "INVALID_SOURCE"
    assert invalid.timeline == ()
    assert invalid.remote_transfer_performed is False


def test_invalid_cursor_and_robot_are_rejected(tmp_path: Path) -> None:
    source = load_competition_log_source(_replay_log(tmp_path / "invalid-cursor.jsonl"))
    store = ReplayCursorStore(source)

    with pytest.raises(ValueError, match="cursor sequence"):
        build_replay_screen_snapshot(source, RobotId.R1, cursor_sequence=3)
    with pytest.raises(ValueError, match="selected robot timeline"):
        store.select_sequence(RobotId.R1, 3)
    with pytest.raises(ValueError, match="robot_id"):
        build_replay_screen_snapshot(source, "R1")  # type: ignore[arg-type]
