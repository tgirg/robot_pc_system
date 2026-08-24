"""Read-only GUI model for explicitly selected local Competition JSONL logs."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .autonomy import RobotId
from .competition import read_competition_log_records


UNKNOWN = "UNKNOWN_NOT_RECORDED"
REMOTE_SYNC_STATUS = "AWAITING_REMOTE_CONFIGURATION"
MAX_RETAINED_RECORDS = 1000
MAX_DISPLAYED_RECORDS = 200


@dataclass(frozen=True)
class CompetitionLogEventSnapshot:
    sequence: int
    timestamp_ms: int
    scope: str
    robot_id: RobotId | None
    state_transition: str
    competition_state: str
    event: str
    autonomy_state: str
    safety_state: str
    armed_state: str
    fault_context: str
    retry_context: str
    node_context: str
    reason: str
    data_summary: str


@dataclass(frozen=True)
class CompetitionLogSourceSnapshot:
    source_status: str
    source_kind: str
    source_path: str | None
    validation_state: str
    validation_message: str
    session_id: str | None
    total_record_count: int
    retained_record_count: int
    truncated_record_count: int
    first_timestamp_ms: int | None
    last_timestamp_ms: int | None
    final_competition_state: str | None
    finalized: bool
    remote_sync_status: str
    remote_transfer_performed: bool
    events: tuple[CompetitionLogEventSnapshot, ...]


@dataclass(frozen=True)
class LogsScreenSnapshot:
    robot_id: RobotId
    source_status: str
    source_kind: str
    source_path: str | None
    validation_state: str
    validation_message: str
    session_id: str | None
    total_record_count: int
    retained_record_count: int
    truncated_record_count: int
    matching_record_count: int
    displayed_record_count: int
    hidden_matching_record_count: int
    first_timestamp_ms: int | None
    last_timestamp_ms: int | None
    final_competition_state: str | None
    finalized: bool
    remote_sync_status: str
    remote_transfer_performed: bool
    entries: tuple[CompetitionLogEventSnapshot, ...]


def load_competition_log_source(
    log_path: str | Path | None,
    *,
    max_retained_records: int = MAX_RETAINED_RECORDS,
) -> CompetitionLogSourceSnapshot:
    """Load one explicit local log without scanning or mutating its directory."""
    if max_retained_records < 1 or max_retained_records > 10000:
        raise ValueError("max_retained_records must be between 1 and 10000")
    if log_path is None:
        return _empty_source(
            source_status="NOT_CONFIGURED",
            source_path=None,
            validation_state="NO_EXPLICIT_LOCAL_LOG",
            validation_message="No local Competition JSONL was explicitly selected.",
        )

    source_path = str(log_path)
    try:
        records = read_competition_log_records(log_path)
    except (OSError, UnicodeError, ValueError) as exc:
        return _empty_source(
            source_status="INVALID",
            source_path=source_path,
            validation_state="INVALID_LOCAL_COMPETITION_JSONL",
            validation_message=str(exc),
        )

    events: deque[CompetitionLogEventSnapshot] = deque(maxlen=max_retained_records)
    previous_state: str | None = None
    for record in records:
        state = str(record["competition_state"])
        transition = (
            f"FIRST_RECORDED_STATE={state}"
            if previous_state is None
            else f"{previous_state} -> {state}"
            if previous_state != state
            else f"NO_CHANGE ({state})"
        )
        events.append(_event_snapshot(record, transition))
        previous_state = state

    first = records[0]
    last = records[-1]
    retained = tuple(events)
    return CompetitionLogSourceSnapshot(
        source_status="LOADED",
        source_kind="LOCAL_COMPETITION_JSONL",
        source_path=source_path,
        validation_state="VALIDATED_LOCAL_COMPETITION_JSONL",
        validation_message="Core schema, sequence, timestamp, state, and session identity are valid.",
        session_id=str(first["session_id"]),
        total_record_count=len(records),
        retained_record_count=len(retained),
        truncated_record_count=len(records) - len(retained),
        first_timestamp_ms=int(first["timestamp_ms"]),
        last_timestamp_ms=int(last["timestamp_ms"]),
        final_competition_state=str(last["competition_state"]),
        finalized=(
            last.get("event") == "session_finalized"
            and last.get("competition_state") == "POST_COMPETITION"
        ),
        remote_sync_status=REMOTE_SYNC_STATUS,
        remote_transfer_performed=False,
        events=retained,
    )


def build_logs_screen_snapshot(
    source: CompetitionLogSourceSnapshot,
    robot_id: RobotId,
    *,
    max_displayed_records: int = MAX_DISPLAYED_RECORDS,
) -> LogsScreenSnapshot:
    """Filter one immutable source for a robot while retaining fleet events."""
    if not isinstance(robot_id, RobotId):
        raise ValueError("robot_id must be RobotId.R1 or RobotId.R2")
    if max_displayed_records < 1 or max_displayed_records > 1000:
        raise ValueError("max_displayed_records must be between 1 and 1000")
    matching = tuple(
        event
        for event in source.events
        if event.robot_id is None or event.robot_id == robot_id
    )
    entries = matching[-max_displayed_records:]
    return LogsScreenSnapshot(
        robot_id=robot_id,
        source_status=source.source_status,
        source_kind=source.source_kind,
        source_path=source.source_path,
        validation_state=source.validation_state,
        validation_message=source.validation_message,
        session_id=source.session_id,
        total_record_count=source.total_record_count,
        retained_record_count=source.retained_record_count,
        truncated_record_count=source.truncated_record_count,
        matching_record_count=len(matching),
        displayed_record_count=len(entries),
        hidden_matching_record_count=len(matching) - len(entries),
        first_timestamp_ms=source.first_timestamp_ms,
        last_timestamp_ms=source.last_timestamp_ms,
        final_competition_state=source.final_competition_state,
        finalized=source.finalized,
        remote_sync_status=source.remote_sync_status,
        remote_transfer_performed=source.remote_transfer_performed,
        entries=entries,
    )


def _empty_source(
    *,
    source_status: str,
    source_path: str | None,
    validation_state: str,
    validation_message: str,
) -> CompetitionLogSourceSnapshot:
    return CompetitionLogSourceSnapshot(
        source_status=source_status,
        source_kind="LOCAL_COMPETITION_JSONL",
        source_path=source_path,
        validation_state=validation_state,
        validation_message=validation_message,
        session_id=None,
        total_record_count=0,
        retained_record_count=0,
        truncated_record_count=0,
        first_timestamp_ms=None,
        last_timestamp_ms=None,
        final_competition_state=None,
        finalized=False,
        remote_sync_status=REMOTE_SYNC_STATUS,
        remote_transfer_performed=False,
        events=(),
    )


def _event_snapshot(record: Mapping[str, Any], transition: str) -> CompetitionLogEventSnapshot:
    data = record.get("data") if isinstance(record.get("data"), Mapping) else {}
    robot_id = _robot_id(record.get("robot_id"))
    return CompetitionLogEventSnapshot(
        sequence=int(record["sequence"]),
        timestamp_ms=int(record["timestamp_ms"]),
        scope=robot_id.value if robot_id is not None else "FLEET",
        robot_id=robot_id,
        state_transition=transition,
        competition_state=str(record["competition_state"]),
        event=str(record["event"]),
        autonomy_state=_text(record.get("autonomy_state")),
        safety_state=_text(record.get("safety_state")),
        armed_state=_armed_text(record.get("armed")),
        fault_context=_data_context(data, ("fault", "fault_reason", "fault_flags")),
        retry_context=_retry_context(data),
        node_context=_data_context(data, ("node_event", "node_id", "node")),
        reason=_text(record.get("reason")),
        data_summary=_data_summary(data),
    )


def _robot_id(value: Any) -> RobotId | None:
    try:
        return RobotId(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else UNKNOWN


def _armed_text(value: Any) -> str:
    return "ARMED" if value is True else "DISARMED" if value is False else UNKNOWN


def _data_context(data: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    selected = {key: data[key] for key in keys if key in data}
    return _json_text(selected) if selected else UNKNOWN


def _retry_context(data: Mapping[str, Any]) -> str:
    selected = {
        key: data[key]
        for key in ("retry", "retry_count", "attempt", "retry_deadline_ms")
        if key in data
    }
    actions = data.get("actions")
    if isinstance(actions, (list, tuple)):
        retry_actions = [item for item in actions if isinstance(item, str) and "RETRY" in item.upper()]
        if retry_actions:
            selected["actions"] = retry_actions
    return _json_text(selected) if selected else UNKNOWN


def _data_summary(data: Mapping[str, Any]) -> str:
    return _json_text(data) if data else "NONE"


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return UNKNOWN
