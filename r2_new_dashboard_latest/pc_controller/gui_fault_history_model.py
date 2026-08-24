"""Session-local Fault / Warning History derived from immutable GUI snapshots.

The store observes diagnostic event edges only.  It owns no ControllerApp,
transport, SafetyMonitor, config, ARM, or hardware-output API.  Acknowledgement
is local GUI metadata and never clears the latched Safety root cause.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .autonomy import RobotId
from .gui_model import DiagnosticEventSnapshot, DisplaySeverity, FleetDashboardSnapshot, RobotDashboardSnapshot


@dataclass(frozen=True)
class FaultHistoryEntrySnapshot:
    event_id: str
    robot_id: RobotId
    severity: DisplaySeverity
    source: str
    node_id: str | None
    reason: str
    timestamp_ms: int
    timestamp_basis: str
    fault_flags: int | None
    safety_response: str
    acknowledged: bool
    active: bool


@dataclass(frozen=True)
class FaultHistorySnapshot:
    robot_id: RobotId
    configured: bool
    snapshot_timestamp_ms: int
    entries: tuple[FaultHistoryEntrySnapshot, ...]
    active_count: int
    unacknowledged_count: int
    retention_state: str
    acknowledgement_state: str


class FaultHistoryStore:
    """Retain bounded per-robot event history for the current GUI process."""

    def __init__(self, *, max_entries_per_robot: int = 200) -> None:
        if max_entries_per_robot < 1:
            raise ValueError("max_entries_per_robot must be positive")
        self._max_entries = int(max_entries_per_robot)
        self._entries: dict[RobotId, list[FaultHistoryEntrySnapshot]] = {
            RobotId.R1: [],
            RobotId.R2: [],
        }
        self._active_ids: dict[RobotId, dict[tuple[object, ...], str]] = {
            RobotId.R1: {},
            RobotId.R2: {},
        }
        self._next_sequence: dict[RobotId, int] = {RobotId.R1: 1, RobotId.R2: 1}
        self._latest: dict[RobotId, RobotDashboardSnapshot] = {}

    def ingest_fleet(self, fleet: FleetDashboardSnapshot) -> FaultHistorySnapshot:
        for robot in fleet.robots:
            self.ingest(robot)
        return self.build(fleet.selected)

    def ingest(self, robot: RobotDashboardSnapshot) -> FaultHistorySnapshot:
        robot_id = _robot_id(robot)
        current_events: dict[tuple[object, ...], DiagnosticEventSnapshot] = {}
        for event in robot.diagnostic_events:
            current_events.setdefault(_event_key(event), event)

        active_ids = self._active_ids[robot_id]
        removed_keys = tuple(key for key in active_ids if key not in current_events)
        for key in removed_keys:
            event_id = active_ids.pop(key)
            self._replace_entry(robot_id, event_id, active=False)

        for key, event in current_events.items():
            if key in active_ids:
                continue
            event_id = self._new_event_id(robot_id)
            timestamp = event.timestamp_ms if event.timestamp_ms is not None else int(robot.timestamp_ms)
            entry = FaultHistoryEntrySnapshot(
                event_id=event_id,
                robot_id=robot_id,
                severity=event.severity,
                source=event.source,
                node_id=event.node_id,
                reason=event.reason,
                timestamp_ms=int(timestamp),
                timestamp_basis="SOURCE" if event.timestamp_ms is not None else "FIRST_OBSERVED",
                fault_flags=event.fault_flags,
                safety_response=event.safety_response,
                acknowledged=False,
                active=True,
            )
            self._entries[robot_id].append(entry)
            active_ids[key] = event_id

        self._latest[robot_id] = robot
        self._prune(robot_id)
        return self.build(robot)

    def acknowledge(self, robot_id: RobotId | str, event_id: str) -> FaultHistorySnapshot:
        return self._set_acknowledged(robot_id, event_id, True)

    def unacknowledge(self, robot_id: RobotId | str, event_id: str) -> FaultHistorySnapshot:
        return self._set_acknowledged(robot_id, event_id, False)

    def build(self, robot: RobotDashboardSnapshot) -> FaultHistorySnapshot:
        robot_id = _robot_id(robot)
        entries = tuple(reversed(self._entries[robot_id]))
        return FaultHistorySnapshot(
            robot_id=robot_id,
            configured=bool(robot.configured),
            snapshot_timestamp_ms=int(robot.timestamp_ms),
            entries=entries,
            active_count=sum(1 for entry in entries if entry.active),
            unacknowledged_count=sum(1 for entry in entries if not entry.acknowledged),
            retention_state=f"SESSION_MEMORY_ONLY_MAX_{self._max_entries}",
            acknowledgement_state="LOCAL_VIEW_ONLY_DOES_NOT_CLEAR_SAFETY",
        )

    def _set_acknowledged(
        self,
        robot_id: RobotId | str,
        event_id: str,
        acknowledged: bool,
    ) -> FaultHistorySnapshot:
        normalized = RobotId(robot_id)
        if not self._replace_entry(normalized, event_id, acknowledged=bool(acknowledged)):
            raise KeyError(event_id)
        robot = self._latest.get(normalized)
        if robot is None:
            raise RuntimeError(f"no snapshot ingested for {normalized.value}")
        return self.build(robot)

    def _replace_entry(self, robot_id: RobotId, event_id: str, **changes: object) -> bool:
        entries = self._entries[robot_id]
        for index, entry in enumerate(entries):
            if entry.event_id == event_id:
                entries[index] = replace(entry, **changes)
                return True
        return False

    def _new_event_id(self, robot_id: RobotId) -> str:
        sequence = self._next_sequence[robot_id]
        self._next_sequence[robot_id] = sequence + 1
        return f"{robot_id.value}-{sequence:06d}"

    def _prune(self, robot_id: RobotId) -> None:
        entries = self._entries[robot_id]
        overflow = len(entries) - self._max_entries
        if overflow <= 0:
            return
        removed_ids = {entry.event_id for entry in entries[:overflow]}
        del entries[:overflow]
        active_ids = self._active_ids[robot_id]
        for key, event_id in tuple(active_ids.items()):
            if event_id in removed_ids:
                del active_ids[key]


def _robot_id(robot: RobotDashboardSnapshot) -> RobotId:
    try:
        return RobotId(robot.robot_id)
    except ValueError as exc:
        raise ValueError("fault history robot_id must be R1 or R2") from exc


def _event_key(event: DiagnosticEventSnapshot) -> tuple[object, ...]:
    return (
        event.severity.value,
        event.source,
        event.node_id,
        event.reason,
        event.fault_flags,
        event.timestamp_ms,
    )
