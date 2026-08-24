"""Offline Competition replay model derived only from validated local logs.

Replay is a local visualization cursor.  It never calls ``ControllerApp``,
``CompetitionSession``, an Autonomy state machine, Serial, ARM, or an executor.
Recorded action names remain inert text and missing fields remain unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

from .autonomy import RobotId
from .gui_logs_model import (
    UNKNOWN,
    CompetitionLogEventSnapshot,
    CompetitionLogSourceSnapshot,
)


@dataclass(frozen=True)
class ReplayScreenSnapshot:
    robot_id: RobotId
    availability: str
    source_status: str
    source_path: str | None
    validation_state: str
    validation_message: str
    session_id: str | None
    timeline_count: int
    cursor_index: int | None
    cursor_position: int | None
    current_sequence: int | None
    current_timestamp_ms: int | None
    elapsed_from_session_start_ms: int | None
    retained_first_sequence: int | None
    retained_last_sequence: int | None
    prefix_truncated: bool
    truncated_record_count: int
    current_scope: str
    competition_state: str
    state_transition: str
    competition_event: str
    autonomy_state: str
    autonomy_basis: str
    safety_state: str
    safety_basis: str
    armed_state: str
    armed_basis: str
    fault_context: str
    retry_context: str
    node_context: str
    reason: str
    data_summary: str
    remote_sync_status: str
    remote_transfer_performed: bool
    control_boundary: str
    timeline: tuple[CompetitionLogEventSnapshot, ...]


class ReplayCursorStore:
    """Keep a stable, R1/R2-isolated local cursor for one immutable source."""

    def __init__(self, source: CompetitionLogSourceSnapshot) -> None:
        self._source = source
        self._source_key = _source_key(source)
        self._cursor_sequences: dict[RobotId, int | None] = {
            RobotId.R1: None,
            RobotId.R2: None,
        }
        self.set_source(source)

    @property
    def source(self) -> CompetitionLogSourceSnapshot:
        return self._source

    def set_source(self, source: CompetitionLogSourceSnapshot) -> None:
        if not isinstance(source, CompetitionLogSourceSnapshot):
            raise ValueError("replay source must be a CompetitionLogSourceSnapshot")
        next_key = _source_key(source)
        source_changed = next_key != self._source_key
        self._source = source
        self._source_key = next_key
        for robot_id in (RobotId.R1, RobotId.R2):
            timeline = _timeline(source, robot_id)
            current = self._cursor_sequences[robot_id]
            sequences = {event.sequence for event in timeline}
            if source_changed or current not in sequences:
                self._cursor_sequences[robot_id] = timeline[0].sequence if timeline else None

    def snapshot(self, robot_id: RobotId) -> ReplayScreenSnapshot:
        _require_robot_id(robot_id)
        return build_replay_screen_snapshot(
            self._source,
            robot_id,
            cursor_sequence=self._cursor_sequences[robot_id],
        )

    def select_sequence(self, robot_id: RobotId, sequence: int) -> ReplayScreenSnapshot:
        _require_robot_id(robot_id)
        if type(sequence) is not int:
            raise ValueError("replay sequence must be an integer")
        timeline = _timeline(self._source, robot_id)
        if sequence not in {event.sequence for event in timeline}:
            raise ValueError("replay sequence is not in the selected robot timeline")
        self._cursor_sequences[robot_id] = sequence
        return self.snapshot(robot_id)

    def move(self, robot_id: RobotId, delta: int) -> ReplayScreenSnapshot:
        _require_robot_id(robot_id)
        if type(delta) is not int:
            raise ValueError("replay cursor delta must be an integer")
        timeline = _timeline(self._source, robot_id)
        if not timeline:
            return self.snapshot(robot_id)
        current = self._cursor_sequences[robot_id]
        sequences = [event.sequence for event in timeline]
        index = sequences.index(current) if current in sequences else 0
        index = max(0, min(len(timeline) - 1, index + delta))
        self._cursor_sequences[robot_id] = timeline[index].sequence
        return self.snapshot(robot_id)

    def first(self, robot_id: RobotId) -> ReplayScreenSnapshot:
        return self._move_to_boundary(robot_id, last=False)

    def last(self, robot_id: RobotId) -> ReplayScreenSnapshot:
        return self._move_to_boundary(robot_id, last=True)

    def _move_to_boundary(self, robot_id: RobotId, *, last: bool) -> ReplayScreenSnapshot:
        _require_robot_id(robot_id)
        timeline = _timeline(self._source, robot_id)
        if timeline:
            self._cursor_sequences[robot_id] = timeline[-1 if last else 0].sequence
        return self.snapshot(robot_id)


def build_replay_screen_snapshot(
    source: CompetitionLogSourceSnapshot,
    robot_id: RobotId,
    *,
    cursor_sequence: int | None = None,
) -> ReplayScreenSnapshot:
    """Project one inert replay frame from a validated retained log suffix."""
    if not isinstance(source, CompetitionLogSourceSnapshot):
        raise ValueError("replay source must be a CompetitionLogSourceSnapshot")
    _require_robot_id(robot_id)
    timeline = _timeline(source, robot_id)
    if not timeline:
        return _empty_screen(source, robot_id)

    if cursor_sequence is None:
        cursor_index = 0
    else:
        cursor_index = next(
            (index for index, event in enumerate(timeline) if event.sequence == cursor_sequence),
            -1,
        )
        if cursor_index < 0:
            raise ValueError("replay cursor sequence is not in the selected robot timeline")
    event = timeline[cursor_index]
    robot_events = tuple(
        item
        for item in timeline[: cursor_index + 1]
        if item.robot_id == robot_id
    )
    autonomy_state, autonomy_basis = _last_recorded(
        robot_events,
        "autonomy_state",
        robot_id,
        source.truncated_record_count,
    )
    safety_state, safety_basis = _last_recorded(
        robot_events,
        "safety_state",
        robot_id,
        source.truncated_record_count,
    )
    armed_state, armed_basis = _last_recorded(
        robot_events,
        "armed_state",
        robot_id,
        source.truncated_record_count,
    )
    first_timestamp = source.first_timestamp_ms
    elapsed = (
        max(0, event.timestamp_ms - first_timestamp)
        if first_timestamp is not None
        else None
    )
    return ReplayScreenSnapshot(
        robot_id=robot_id,
        availability="READY_LOCAL_REPLAY",
        source_status=source.source_status,
        source_path=source.source_path,
        validation_state=source.validation_state,
        validation_message=source.validation_message,
        session_id=source.session_id,
        timeline_count=len(timeline),
        cursor_index=cursor_index,
        cursor_position=cursor_index + 1,
        current_sequence=event.sequence,
        current_timestamp_ms=event.timestamp_ms,
        elapsed_from_session_start_ms=elapsed,
        retained_first_sequence=timeline[0].sequence,
        retained_last_sequence=timeline[-1].sequence,
        prefix_truncated=source.truncated_record_count > 0,
        truncated_record_count=source.truncated_record_count,
        current_scope=event.scope,
        competition_state=event.competition_state,
        state_transition=event.state_transition,
        competition_event=event.event,
        autonomy_state=autonomy_state,
        autonomy_basis=autonomy_basis,
        safety_state=safety_state,
        safety_basis=safety_basis,
        armed_state=armed_state,
        armed_basis=armed_basis,
        fault_context=event.fault_context,
        retry_context=event.retry_context,
        node_context=event.node_context,
        reason=event.reason,
        data_summary=event.data_summary,
        remote_sync_status=source.remote_sync_status,
        remote_transfer_performed=source.remote_transfer_performed,
        control_boundary=(
            "OFFLINE_VISUALIZATION_ONLY_NO_COMMAND_REEMIT_ARM_EXECUTOR_"
            "STATE_MACHINE_MUTATION_OR_REMOTE_TRANSFER"
        ),
        timeline=timeline,
    )


def _empty_screen(
    source: CompetitionLogSourceSnapshot,
    robot_id: RobotId,
) -> ReplayScreenSnapshot:
    availability = (
        "NOT_CONFIGURED"
        if source.source_status == "NOT_CONFIGURED"
        else "INVALID_SOURCE"
        if source.source_status == "INVALID"
        else "NO_MATCHING_RETAINED_EVENTS"
    )
    return ReplayScreenSnapshot(
        robot_id=robot_id,
        availability=availability,
        source_status=source.source_status,
        source_path=source.source_path,
        validation_state=source.validation_state,
        validation_message=source.validation_message,
        session_id=source.session_id,
        timeline_count=0,
        cursor_index=None,
        cursor_position=None,
        current_sequence=None,
        current_timestamp_ms=None,
        elapsed_from_session_start_ms=None,
        retained_first_sequence=None,
        retained_last_sequence=None,
        prefix_truncated=source.truncated_record_count > 0,
        truncated_record_count=source.truncated_record_count,
        current_scope=UNKNOWN,
        competition_state=UNKNOWN,
        state_transition=UNKNOWN,
        competition_event=UNKNOWN,
        autonomy_state=UNKNOWN,
        autonomy_basis="UNKNOWN_NO_REPLAY_FRAME",
        safety_state=UNKNOWN,
        safety_basis="UNKNOWN_NO_REPLAY_FRAME",
        armed_state=UNKNOWN,
        armed_basis="UNKNOWN_NO_REPLAY_FRAME",
        fault_context=UNKNOWN,
        retry_context=UNKNOWN,
        node_context=UNKNOWN,
        reason=UNKNOWN,
        data_summary=UNKNOWN,
        remote_sync_status=source.remote_sync_status,
        remote_transfer_performed=source.remote_transfer_performed,
        control_boundary=(
            "OFFLINE_VISUALIZATION_ONLY_NO_COMMAND_REEMIT_ARM_EXECUTOR_"
            "STATE_MACHINE_MUTATION_OR_REMOTE_TRANSFER"
        ),
        timeline=(),
    )


def _timeline(
    source: CompetitionLogSourceSnapshot,
    robot_id: RobotId,
) -> tuple[CompetitionLogEventSnapshot, ...]:
    return tuple(
        event
        for event in source.events
        if event.robot_id is None or event.robot_id == robot_id
    )


def _last_recorded(
    events: tuple[CompetitionLogEventSnapshot, ...],
    field: str,
    robot_id: RobotId,
    truncated_record_count: int,
) -> tuple[str, str]:
    for event in reversed(events):
        value = str(getattr(event, field))
        if value != UNKNOWN:
            return value, f"LAST_RECORDED_FOR_{robot_id.value}@sequence={event.sequence}"
    basis = (
        "UNKNOWN_RETAINED_PREFIX_TRUNCATED"
        if truncated_record_count > 0
        else f"UNKNOWN_NOT_RECORDED_FOR_{robot_id.value}"
    )
    return UNKNOWN, basis


def _source_key(source: CompetitionLogSourceSnapshot) -> tuple[str | None, str | None]:
    return source.source_path, source.session_id


def _require_robot_id(robot_id: RobotId) -> None:
    if not isinstance(robot_id, RobotId):
        raise ValueError("robot_id must be RobotId.R1 or RobotId.R2")
