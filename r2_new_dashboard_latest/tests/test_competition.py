from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pc_controller.autonomy import (
    ActionKind,
    AutonomyState,
    AutonomyStateMachine,
    FleetAutonomyCoordinator,
    MissionPlan,
    MissionStep,
    RobotId,
)
from pc_controller.competition import (
    CompetitionLogWriter,
    CompetitionSession,
    CompetitionState,
    prepare_post_competition_bundle,
)


def _machine(robot_id: RobotId, step_id: str = "task") -> AutonomyStateMachine:
    return AutonomyStateMachine(MissionPlan(f"{robot_id.value}_mission", robot_id, (MissionStep(step_id),)))


def _session(tmp_path: Path, *machines: AutonomyStateMachine) -> CompetitionSession:
    writer = CompetitionLogWriter(tmp_path / "competition.jsonl", "session-test")
    return CompetitionSession(FleetAutonomyCoordinator(tuple(machines)), writer)


def _prepare_and_arm(session: CompetitionSession, robot_ids: tuple[RobotId, ...]) -> None:
    assert session.enable(0, explicit=True) == {}
    assert session.precheck(
        1,
        required_nodes_ready={robot_id: True for robot_id in robot_ids},
        safety_ready={robot_id: True for robot_id in robot_ids},
    ) == {}
    for robot_id in robot_ids:
        assert session.confirm_explicit_arm(2, robot_id, confirmed=True) == {}


def test_competition_log_is_exclusive_append_only_fsynced_and_redacted(tmp_path: Path) -> None:
    path = tmp_path / "competition.jsonl"
    writer = CompetitionLogWriter(path, "session-1")
    writer.append(
        10,
        "created",
        CompetitionState.CREATED,
        data={"api_token": "secret-value", "nested": {"wifi_psk": "also-secret"}, "safe": 3},
    )
    writer.append(20, "ready", CompetitionState.READY_DISARMED, robot_id=RobotId.R1)
    writer.close()

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["sequence"] for record in records] == [1, 2]
    assert records[0]["data"] == {
        "api_token": "***REDACTED***",
        "nested": {"wifi_psk": "***REDACTED***"},
        "safe": 3,
    }
    assert records[1]["robot_id"] == "R1"
    with pytest.raises(RuntimeError, match="log is closed"):
        writer.append(30, "late", CompetitionState.STOPPED)
    with pytest.raises(FileExistsError):
        CompetitionLogWriter(path, "session-2")


def test_competition_enable_requires_explicit_confirmation(tmp_path: Path) -> None:
    session = _session(tmp_path, _machine(RobotId.R1))

    assert session.enable(0, explicit=False) == {}
    assert session.state == CompetitionState.CREATED
    assert session.enable(1, explicit=True) == {}
    assert session.state == CompetitionState.PRECHECK
    session.finalize(2)


def test_finalized_session_is_terminal_and_does_not_reopen_closed_log(tmp_path: Path) -> None:
    session = _session(tmp_path, _machine(RobotId.R1))
    session.finalize(1)
    records_before = session.log.path.read_bytes()

    assert session.enable(2, explicit=True) == {}
    assert session.precheck(2, required_nodes_ready={}, safety_ready={}) == {}
    assert session.confirm_explicit_arm(2, RobotId.R1, confirmed=True) == {}
    assert session.start(2, explicit=False) == {}
    assert session.start(2, explicit=True) == {}
    assert session.record_step_result(2, RobotId.R1, success=True) == {}
    assert session.record_fallback_result(2, RobotId.R1, success=True) == {}
    assert session.operator_stop(2) == {}
    assert session.state == CompetitionState.POST_COMPETITION
    assert session.log.path.read_bytes() == records_before


def test_competition_precheck_missing_node_blocks_all_robots(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1)
    r2 = _machine(RobotId.R2)
    session = _session(tmp_path, r1, r2)
    session.enable(0, explicit=True)

    actions = session.precheck(
        1,
        required_nodes_ready={RobotId.R1: True, RobotId.R2: False},
        safety_ready={RobotId.R1: True, RobotId.R2: True},
    )

    assert session.state == CompetitionState.BLOCKED
    assert r1.state == AutonomyState.STOPPED
    assert r2.state == AutonomyState.BLOCKED
    assert set(actions) == {RobotId.R1, RobotId.R2}
    assert any(action.kind == ActionKind.STOP_REQUESTED for action in actions[RobotId.R1])
    session.finalize(2)


def test_competition_cannot_start_before_all_explicit_arm_confirmations(tmp_path: Path) -> None:
    session = _session(tmp_path, _machine(RobotId.R1), _machine(RobotId.R2))
    session.enable(0, explicit=True)
    session.precheck(
        1,
        required_nodes_ready={RobotId.R1: True, RobotId.R2: True},
        safety_ready={RobotId.R1: True, RobotId.R2: True},
    )
    assert session.start(2, explicit=False) == {}
    session.confirm_explicit_arm(3, RobotId.R1, confirmed=True)

    actions = session.start(4, explicit=True)

    assert session.state == CompetitionState.BLOCKED
    assert set(actions) == {RobotId.R1, RobotId.R2}
    assert all(machine.state in {AutonomyState.BLOCKED, AutonomyState.STOPPED} for machine in session.fleet.machines.values())
    session.finalize(5)


def test_competition_start_rechecks_every_machine_state_fail_closed(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1)
    r2 = _machine(RobotId.R2)
    session = _session(tmp_path, r1, r2)
    _prepare_and_arm(session, (RobotId.R1, RobotId.R2))
    r2.state = AutonomyState.READY_DISARMED

    actions = session.start(3, explicit=True)

    assert session.state == CompetitionState.BLOCKED
    assert session.reason == "competition start failed: R2"
    assert set(actions) == {RobotId.R1, RobotId.R2}
    assert r1.state == AutonomyState.STOPPED
    assert r2.state == AutonomyState.BLOCKED
    session.finalize(4)


def test_unknown_robot_operation_blocks_and_stops_configured_fleet(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1)
    session = _session(tmp_path, r1)
    session.enable(0, explicit=True)
    session.precheck(
        1,
        required_nodes_ready={RobotId.R1: True},
        safety_ready={RobotId.R1: True},
    )

    actions = session.confirm_explicit_arm(2, RobotId.R2, confirmed=True)

    assert session.state == CompetitionState.BLOCKED
    assert session.reason == "competition robot not configured: R2"
    assert set(actions) == {RobotId.R1}
    assert r1.state == AutonomyState.BLOCKED
    session.finalize(3)


def test_mistyped_robot_id_fails_closed_instead_of_raising(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1)
    session = _session(tmp_path, r1)
    session.enable(0, explicit=True)
    session.precheck(
        1,
        required_nodes_ready={RobotId.R1: True},
        safety_ready={RobotId.R1: True},
    )

    actions = session.confirm_explicit_arm(2, "R1", confirmed=True)  # type: ignore[arg-type]

    assert session.state == CompetitionState.BLOCKED
    assert session.reason == "competition robot not configured: 'R1'"
    assert set(actions) == {RobotId.R1}
    assert r1.state == AutonomyState.BLOCKED
    session.finalize(3)


def test_two_robot_competition_runs_independently_then_finalizes_log(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1, "r1_task")
    r2 = _machine(RobotId.R2, "r2_task")
    session = _session(tmp_path, r1, r2)
    _prepare_and_arm(session, (RobotId.R1, RobotId.R2))

    started = session.start(3, explicit=True)
    r1_done = session.record_step_result(4, RobotId.R1, success=True)
    r2_done = session.record_step_result(5, RobotId.R2, success=True)
    finalized = session.finalize(6)

    assert session.state == CompetitionState.POST_COMPETITION
    assert set(started) == {RobotId.R1, RobotId.R2}
    assert [action.kind for action in r1_done[RobotId.R1]] == [
        ActionKind.STOP_REQUESTED,
        ActionKind.MISSION_COMPLETED,
    ]
    assert [action.kind for action in r2_done[RobotId.R2]] == [
        ActionKind.STOP_REQUESTED,
        ActionKind.MISSION_COMPLETED,
    ]
    assert finalized == {}
    assert session.log.closed is True
    records = [json.loads(line) for line in session.log.path.read_text(encoding="utf-8").splitlines()]
    assert [record["sequence"] for record in records] == list(range(1, len(records) + 1))
    assert records[-1]["event"] == "session_finalized"
    assert records[-1]["competition_state"] == "POST_COMPETITION"


def test_one_robot_stop_policy_stops_entire_competition(tmp_path: Path) -> None:
    r1 = _machine(RobotId.R1)
    r2 = _machine(RobotId.R2)
    session = _session(tmp_path, r1, r2)
    _prepare_and_arm(session, (RobotId.R1, RobotId.R2))
    session.start(3, explicit=True)

    actions = session.record_step_result(4, RobotId.R1, success=False, reason="R1 fault")

    assert session.state == CompetitionState.STOPPED
    assert r1.state == AutonomyState.STOPPED
    assert r2.state == AutonomyState.STOPPED
    assert set(actions) == {RobotId.R1, RobotId.R2}
    assert any(action.reason == "R1 fault" for action in actions[RobotId.R1])
    session.finalize(5)


def test_log_failure_blocks_and_requests_stop_for_all_robots(tmp_path: Path) -> None:
    class BrokenLog:
        def append(self, *_: object, **__: object) -> None:
            raise OSError("disk full")

        def close(self) -> None:
            pass

    r1 = _machine(RobotId.R1)
    r2 = _machine(RobotId.R2)
    session = CompetitionSession(FleetAutonomyCoordinator((r1, r2)), BrokenLog())  # type: ignore[arg-type]

    actions = session.enable(0, explicit=True)

    assert session.state == CompetitionState.BLOCKED
    assert session.reason == "competition log failure: disk full"
    assert set(actions) == {RobotId.R1, RobotId.R2}
    assert r1.state == AutonomyState.STOPPED
    assert r2.state == AutonomyState.STOPPED


def test_post_competition_bundle_is_integrity_checked_and_idempotent(tmp_path: Path) -> None:
    session = _session(tmp_path, _machine(RobotId.R1))
    _prepare_and_arm(session, (RobotId.R1,))
    session.start(3, explicit=True)
    session.record_step_result(4, RobotId.R1, success=True)
    session.finalize(5)
    source_before = session.log.path.read_bytes()

    first = prepare_post_competition_bundle(session.log.path, tmp_path / "outbox", created_at_ms=10)
    second = prepare_post_competition_bundle(session.log.path, tmp_path / "outbox", created_at_ms=999)

    assert first == second
    assert session.log.path.read_bytes() == source_before
    assert first.log_path.read_bytes() == source_before
    assert first.sha256 == hashlib.sha256(source_before).hexdigest()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["sync_status"] == "AWAITING_REMOTE_CONFIGURATION"
    assert manifest["remote_transfer_performed"] is False
    assert manifest["sha256"] == first.sha256
    assert manifest["event_count"] == first.event_count


@pytest.mark.parametrize("created_at_ms", [-1, True, 1.5, "1"])
def test_post_competition_bundle_rejects_invalid_created_at(
    tmp_path: Path,
    created_at_ms: Any,
) -> None:
    session = _session(tmp_path, _machine(RobotId.R1))
    session.finalize(1)

    with pytest.raises(ValueError, match="created_at_ms must be a non-negative integer"):
        prepare_post_competition_bundle(
            session.log.path,
            tmp_path / "outbox",
            created_at_ms=created_at_ms,
        )


def test_post_competition_bundle_rejects_unfinalized_or_corrupt_log(tmp_path: Path) -> None:
    open_log = tmp_path / "open.jsonl"
    writer = CompetitionLogWriter(open_log, "open-session")
    writer.append(0, "created", CompetitionState.CREATED)
    writer.close()
    with pytest.raises(ValueError, match="not finalized"):
        prepare_post_competition_bundle(open_log, tmp_path / "outbox", created_at_ms=1)

    corrupt = tmp_path / "corrupt.jsonl"
    record = {
        "schema_version": 1,
        "session_id": "bad",
        "sequence": 2,
        "timestamp_ms": 0,
        "event": "session_finalized",
        "competition_state": "POST_COMPETITION",
    }
    corrupt.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sequence mismatch"):
        prepare_post_competition_bundle(corrupt, tmp_path / "outbox", created_at_ms=1)


def test_post_competition_bundle_rejects_regressed_log_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "regressed.jsonl"
    records = [
        {
            "schema_version": 1,
            "session_id": "regressed",
            "sequence": 1,
            "timestamp_ms": 10,
            "event": "competition_enabled",
            "competition_state": "PRECHECK",
        },
        {
            "schema_version": 1,
            "session_id": "regressed",
            "sequence": 2,
            "timestamp_ms": 9,
            "event": "session_finalized",
            "competition_state": "POST_COMPETITION",
        },
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    with pytest.raises(ValueError, match="timestamp regressed"):
        prepare_post_competition_bundle(path, tmp_path / "outbox", created_at_ms=1)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema_version", True, "invalid competition record"),
        ("sequence", True, "sequence mismatch"),
        ("timestamp_ms", True, "timestamp invalid"),
        ("event", "", "event missing"),
        ("competition_state", "ACTIVE_UNKNOWN", "state invalid"),
    ],
)
def test_post_competition_bundle_rejects_weakly_typed_records(
    tmp_path: Path,
    field: str,
    value: Any,
    error: str,
) -> None:
    record = {
        "schema_version": 1,
        "session_id": "strict-session",
        "sequence": 1,
        "timestamp_ms": 0,
        "event": "session_finalized",
        "competition_state": "POST_COMPETITION",
    }
    record[field] = value
    path = tmp_path / f"invalid-{field}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        prepare_post_competition_bundle(path, tmp_path / "outbox", created_at_ms=1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("created_at_ms", True),
        ("source_name", "other.jsonl"),
        ("size_bytes", True),
        ("event_count", True),
        ("sync_status", "SYNCED"),
        ("remote_transfer_performed", True),
    ],
)
def test_existing_bundle_rejects_tampered_manifest(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    session = _session(tmp_path, _machine(RobotId.R1))
    _prepare_and_arm(session, (RobotId.R1,))
    session.start(3, explicit=True)
    session.record_step_result(4, RobotId.R1, success=True)
    session.finalize(5)
    bundle = prepare_post_competition_bundle(session.log.path, tmp_path / "outbox", created_at_ms=10)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    bundle.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="failed integrity check"):
        prepare_post_competition_bundle(session.log.path, tmp_path / "outbox", created_at_ms=11)


@pytest.mark.parametrize("timestamp_ms", [-1, True, 1.5, "1"])
def test_competition_log_rejects_invalid_timestamp(tmp_path: Path, timestamp_ms: Any) -> None:
    writer = CompetitionLogWriter(tmp_path / "competition.jsonl", "session")
    try:
        with pytest.raises(ValueError, match="non-negative integer"):
            writer.append(timestamp_ms, "event", CompetitionState.CREATED)
    finally:
        writer.close()


def test_competition_log_rejects_timestamp_regression(tmp_path: Path) -> None:
    writer = CompetitionLogWriter(tmp_path / "competition.jsonl", "session")
    try:
        writer.append(10, "first", CompetitionState.CREATED)
        with pytest.raises(ValueError, match="must not regress"):
            writer.append(9, "past", CompetitionState.CREATED)
    finally:
        writer.close()


@pytest.mark.parametrize(
    "path",
    ["https://example.invalid/log.jsonl", r"\\server\share\log.jsonl", "//server/share/log.jsonl"],
)
def test_competition_log_rejects_nonlocal_paths(path: str) -> None:
    with pytest.raises(ValueError, match="local filesystem path"):
        CompetitionLogWriter(path, "session")
