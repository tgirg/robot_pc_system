"""Fail-closed competition session, local logging, and offline sync staging."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .autonomy import (
    AutonomyAction,
    AutonomyState,
    FleetAutonomyCoordinator,
    RobotId,
)


class CompetitionState(str, Enum):
    CREATED = "CREATED"
    PRECHECK = "PRECHECK"
    READY_DISARMED = "READY_DISARMED"
    ARMED_READY = "ARMED_READY"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"
    POST_COMPETITION = "POST_COMPETITION"


@dataclass(frozen=True)
class CompetitionBundle:
    bundle_dir: Path
    log_path: Path
    manifest_path: Path
    session_id: str
    sha256: str
    event_count: int


class CompetitionLogWriter:
    """Append-only, fsync-backed JSONL writer with exclusive creation."""

    def __init__(self, path: str | Path, session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("competition session_id must be non-empty")
        self.path = _require_local_path(path, "competition log")
        if self.path.suffix.lower() not in {".jsonl", ".ndjson"}:
            raise ValueError("competition log must use .jsonl or .ndjson")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id.strip()
        self.sequence = 0
        self._last_timestamp_ms = -1
        self.closed = False
        self._stream = self.path.open("x", encoding="utf-8", newline="\n")

    def append(
        self,
        timestamp_ms: int,
        event: str,
        competition_state: CompetitionState,
        *,
        robot_id: RobotId | None = None,
        autonomy_state: AutonomyState | None = None,
        safety_state: str | None = None,
        armed: bool | None = None,
        reason: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("competition log is closed")
        _validate_nonnegative_int(timestamp_ms, "competition timestamp_ms")
        if timestamp_ms < self._last_timestamp_ms:
            raise ValueError("competition timestamp_ms must not regress")
        if not isinstance(event, str) or not event.strip():
            raise ValueError("competition event must be non-empty")
        if not isinstance(competition_state, CompetitionState):
            raise ValueError("competition_state must be a CompetitionState")
        self.sequence += 1
        record: dict[str, Any] = {
            "schema_version": 1,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "timestamp_ms": timestamp_ms,
            "event": event.strip(),
            "competition_state": competition_state.value,
        }
        if robot_id is not None:
            record["robot_id"] = robot_id.value
        if autonomy_state is not None:
            record["autonomy_state"] = autonomy_state.value
        if safety_state is not None:
            record["safety_state"] = str(safety_state)
        if armed is not None:
            record["armed"] = bool(armed)
        if reason is not None:
            record["reason"] = str(reason)
        if data:
            record["data"] = _redact(dict(data))
        self._stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._last_timestamp_ms = timestamp_ms
        return record

    def close(self) -> None:
        if self.closed:
            return
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        self.closed = True


class CompetitionSession:
    """Explicit-gate COMPETITION mode around independent R1/R2 machines."""

    def __init__(self, fleet: FleetAutonomyCoordinator, log: CompetitionLogWriter) -> None:
        if not fleet.machines:
            raise ValueError("competition session requires at least one robot")
        self.fleet = fleet
        self.log = log
        self.state = CompetitionState.CREATED
        self.reason: str | None = None

    def enable(self, now_ms: int, *, explicit: bool) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state != CompetitionState.CREATED:
            return self._block(now_ms, f"competition enable invalid from {self.state.value}")
        if not explicit:
            if not self._emit(now_ms, "competition_enable_not_confirmed"):
                return self.fleet.stop_all(now_ms, self.reason or "competition log failure")
            return {}
        self.state = CompetitionState.PRECHECK
        if not self._emit(now_ms, "competition_enabled"):
            return self.fleet.stop_all(now_ms, self.reason or "competition log failure")
        return {}

    def precheck(
        self,
        now_ms: int,
        *,
        required_nodes_ready: Mapping[RobotId, bool],
        safety_ready: Mapping[RobotId, bool],
    ) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state != CompetitionState.PRECHECK:
            return self._block(now_ms, f"competition precheck invalid from {self.state.value}")
        actions: dict[RobotId, tuple[AutonomyAction, ...]] = {}
        for robot_id, machine in self._machines():
            machine_actions = machine.prepare(
                now_ms,
                required_nodes_ready=bool(required_nodes_ready.get(robot_id, False)),
                safety_ready=bool(safety_ready.get(robot_id, False)),
            )
            if machine_actions:
                actions[robot_id] = machine_actions
        blocked = [robot_id for robot_id, machine in self._machines() if machine.state == AutonomyState.BLOCKED]
        if blocked:
            reason = "competition precheck failed: " + ",".join(robot.value for robot in blocked)
            self.state = CompetitionState.BLOCKED
            self.reason = reason
            actions = _merge_actions(actions, self.fleet.stop_all(now_ms, reason))
            if not self._emit(now_ms, "competition_precheck_blocked", reason=reason):
                actions = _merge_actions(
                    actions,
                    self.fleet.stop_all(now_ms, self.reason or "competition log failure"),
                )
            return actions
        self.state = CompetitionState.READY_DISARMED
        if not self._emit(now_ms, "competition_ready_disarmed"):
            return self.fleet.stop_all(now_ms, self.reason or "competition log failure")
        return actions

    def confirm_explicit_arm(
        self,
        now_ms: int,
        robot_id: RobotId,
        *,
        confirmed: bool,
    ) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state not in {CompetitionState.READY_DISARMED, CompetitionState.ARMED_READY}:
            return self._block(now_ms, f"competition arm invalid from {self.state.value}")
        if not isinstance(robot_id, RobotId) or robot_id not in self.fleet.machines:
            return self._block(now_ms, f"competition robot not configured: {_robot_label(robot_id)}")
        machine = self.fleet.machine(robot_id)
        actions = machine.confirm_explicit_arm(now_ms, confirmed=confirmed)
        if machine.state == AutonomyState.BLOCKED:
            return self._block(now_ms, machine.stop_reason or "arm confirmation blocked")
        if all(machine.state == AutonomyState.ARMED_READY for _, machine in self._machines()):
            self.state = CompetitionState.ARMED_READY
        if not self._emit(
            now_ms,
            "competition_arm_confirmation",
            robot_id=robot_id,
            reason="confirmed" if confirmed else "not confirmed",
        ):
            return self.fleet.stop_all(now_ms, self.reason or "competition log failure")
        return {robot_id: actions} if actions else {}

    def start(self, now_ms: int, *, explicit: bool) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state == CompetitionState.POST_COMPETITION:
            return {}
        if not explicit:
            if not self._emit(now_ms, "competition_start_not_confirmed"):
                return self.fleet.stop_all(now_ms, self.reason or "competition log failure")
            return {}
        if self.state != CompetitionState.ARMED_READY:
            return self._block(now_ms, f"competition start invalid from {self.state.value}")
        actions = {
            robot_id: machine.start(now_ms, explicit_start=True)
            for robot_id, machine in self._machines()
        }
        failed = [
            robot_id
            for robot_id, machine in self._machines()
            if machine.state != AutonomyState.RUNNING
        ]
        if failed:
            reason = "competition start failed: " + ",".join(robot.value for robot in failed)
            self.state = CompetitionState.BLOCKED
            self.reason = reason
            actions = _merge_actions(actions, self.fleet.stop_all(now_ms, reason))
            if not self._emit(now_ms, "competition_start_blocked", reason=reason):
                actions = _merge_actions(
                    actions,
                    self.fleet.stop_all(now_ms, self.reason or "competition log failure"),
                )
            return actions
        self.state = CompetitionState.ACTIVE
        if not self._emit(now_ms, "competition_started"):
            return _merge_actions(actions, self.fleet.stop_all(now_ms, self.reason or "competition log failure"))
        return actions

    def record_step_result(
        self,
        now_ms: int,
        robot_id: RobotId,
        *,
        success: bool,
        reason: str | None = None,
    ) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state != CompetitionState.ACTIVE:
            return self._block(now_ms, f"step result invalid from {self.state.value}")
        if not isinstance(robot_id, RobotId) or robot_id not in self.fleet.machines:
            return self._block(now_ms, f"competition robot not configured: {_robot_label(robot_id)}")
        machine = self.fleet.machine(robot_id)
        actions = (
            machine.record_step_success(now_ms)
            if success
            else machine.record_step_failure(now_ms, reason or "step failed")
        )
        result = {robot_id: actions}
        if machine.state in {AutonomyState.BLOCKED, AutonomyState.STOPPED}:
            self.state = CompetitionState.STOPPED if machine.state == AutonomyState.STOPPED else CompetitionState.BLOCKED
            self.reason = machine.stop_reason
            result = _merge_actions(result, self.fleet.stop_all(now_ms, self.reason or "robot stopped"))
        elif all(machine.state == AutonomyState.COMPLETED for _, machine in self._machines()):
            self.state = CompetitionState.STOPPED
            self.reason = "all missions completed"
        if not self._emit(
            now_ms,
            "competition_step_result",
            robot_id=robot_id,
            reason=reason or ("success" if success else "step failed"),
            data={"success": success, "actions": [action.kind.value for action in actions]},
        ):
            return _merge_actions(result, self.fleet.stop_all(now_ms, self.reason or "competition log failure"))
        return result

    def tick(self, now_ms: int) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state != CompetitionState.ACTIVE:
            return {}
        actions = {
            robot_id: machine.tick(now_ms)
            for robot_id, machine in self._machines()
        }
        actions = {robot_id: items for robot_id, items in actions.items() if items}
        if actions and not self._emit(
            now_ms,
            "competition_tick_actions",
            data={
                "actions": {
                    robot_id.value: [action.kind.value for action in items]
                    for robot_id, items in actions.items()
                }
            },
        ):
            return _merge_actions(actions, self.fleet.stop_all(now_ms, self.reason or "competition log failure"))
        return actions

    def record_fallback_result(
        self,
        now_ms: int,
        robot_id: RobotId,
        *,
        success: bool,
        reason: str | None = None,
    ) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state != CompetitionState.ACTIVE:
            return self._block(now_ms, f"fallback result invalid from {self.state.value}")
        if not isinstance(robot_id, RobotId) or robot_id not in self.fleet.machines:
            return self._block(now_ms, f"competition robot not configured: {_robot_label(robot_id)}")
        machine = self.fleet.machine(robot_id)
        actions = machine.record_fallback_result(now_ms, success=success, reason=reason)
        result = {robot_id: actions}
        if machine.state in {AutonomyState.BLOCKED, AutonomyState.STOPPED}:
            self.state = CompetitionState.STOPPED if machine.state == AutonomyState.STOPPED else CompetitionState.BLOCKED
            self.reason = machine.stop_reason
            result = _merge_actions(result, self.fleet.stop_all(now_ms, self.reason or "robot stopped"))
        elif all(machine.state == AutonomyState.COMPLETED for _, machine in self._machines()):
            self.state = CompetitionState.STOPPED
            self.reason = "all missions completed"
        if not self._emit(
            now_ms,
            "competition_fallback_result",
            robot_id=robot_id,
            reason=reason or ("success" if success else "fallback failed"),
            data={"success": success, "actions": [action.kind.value for action in actions]},
        ):
            return _merge_actions(result, self.fleet.stop_all(now_ms, self.reason or "competition log failure"))
        return result

    def operator_stop(self, now_ms: int, reason: str = "operator competition stop") -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state == CompetitionState.POST_COMPETITION:
            return {}
        actions = self.fleet.stop_all(now_ms, reason)
        self.state = CompetitionState.STOPPED
        self.reason = reason
        self._emit(now_ms, "competition_stopped", reason=reason)
        return actions

    def finalize(self, now_ms: int) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state == CompetitionState.POST_COMPETITION:
            return {}
        actions: dict[RobotId, tuple[AutonomyAction, ...]] = {}
        if self.state not in {CompetitionState.STOPPED, CompetitionState.BLOCKED}:
            actions = self.fleet.stop_all(now_ms, "competition finalized")
            self.reason = self.reason or "competition finalized"
        self.state = CompetitionState.POST_COMPETITION
        if not self._emit(now_ms, "session_finalized", reason=self.reason):
            actions = _merge_actions(actions, self.fleet.stop_all(now_ms, self.reason or "competition log failure"))
        self.log.close()
        return actions

    def _machines(self) -> list[tuple[RobotId, Any]]:
        return sorted(self.fleet.machines.items(), key=lambda item: item[0].value)

    def _block(self, now_ms: int, reason: str) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        if self.state == CompetitionState.POST_COMPETITION:
            return {}
        self.state = CompetitionState.BLOCKED
        self.reason = reason
        actions = {
            robot_id: machine.block(now_ms, reason)
            for robot_id, machine in self._machines()
        }
        self._emit(now_ms, "competition_blocked", reason=reason)
        return actions

    def _emit(
        self,
        now_ms: int,
        event: str,
        *,
        robot_id: RobotId | None = None,
        reason: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> bool:
        machine = self.fleet.machines.get(robot_id) if robot_id is not None else None
        try:
            self.log.append(
                now_ms,
                event,
                self.state,
                robot_id=robot_id,
                autonomy_state=machine.state if machine else None,
                reason=reason,
                data=data,
            )
        except Exception as exc:
            self.state = CompetitionState.BLOCKED
            self.reason = f"competition log failure: {exc}"
            return False
        return True


def prepare_post_competition_bundle(
    log_path: str | Path,
    outbox_dir: str | Path,
    *,
    created_at_ms: int,
) -> CompetitionBundle:
    """Stage a finalized local log for later sync without network access."""
    _validate_nonnegative_int(created_at_ms, "competition bundle created_at_ms")
    source = _require_local_path(log_path, "competition log")
    outbox = _require_local_path(outbox_dir, "competition outbox")
    records = read_competition_log_records(source)
    last = records[-1]
    if last.get("event") != "session_finalized" or last.get("competition_state") != CompetitionState.POST_COMPETITION.value:
        raise ValueError("competition log is not finalized for POST_COMPETITION sync")

    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    session_id = str(last["session_id"])
    bundle_name = f"{_safe_component(session_id)}-{digest[:12]}"
    bundle_dir = outbox / bundle_name
    staged_log = bundle_dir / "competition.jsonl"
    manifest_path = bundle_dir / "manifest.json"

    if bundle_dir.exists():
        return _validate_existing_bundle(
            bundle_dir,
            session_id,
            digest,
            len(records),
            source_name=source.name,
            size_bytes=len(payload),
        )

    outbox.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(exist_ok=False)
    with staged_log.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at_ms": created_at_ms,
        "source_name": source.name,
        "sha256": digest,
        "size_bytes": len(payload),
        "event_count": len(records),
        "sync_status": "AWAITING_REMOTE_CONFIGURATION",
        "remote_transfer_performed": False,
    }
    with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return CompetitionBundle(bundle_dir, staged_log, manifest_path, session_id, digest, len(records))


def read_competition_log_records(log_path: str | Path) -> tuple[dict[str, Any], ...]:
    """Read and validate one explicitly selected local Competition JSONL log.

    This is a read-only boundary for local diagnostics such as the shared GUI.
    It deliberately performs no directory discovery, repair, outbox staging, or
    remote transfer.
    """
    source = _require_local_path(log_path, "competition log")
    if source.suffix.lower() not in {".jsonl", ".ndjson"}:
        raise ValueError("competition log must use .jsonl or .ndjson")
    if not source.is_file():
        raise ValueError(f"competition log does not exist: {source}")
    return tuple(_read_validated_records(source))


def _read_validated_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    session_id: str | None = None
    last_timestamp_ms = -1
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid competition JSONL at line {line_number}: {exc.msg}") from exc
        if (
            not isinstance(record, dict)
            or type(record.get("schema_version")) is not int
            or record["schema_version"] != 1
        ):
            raise ValueError(f"invalid competition record at line {line_number}")
        if type(record.get("sequence")) is not int or record["sequence"] != line_number:
            raise ValueError(f"competition sequence mismatch at line {line_number}")
        if type(record.get("timestamp_ms")) is not int or record["timestamp_ms"] < 0:
            raise ValueError(f"competition timestamp invalid at line {line_number}")
        if record["timestamp_ms"] < last_timestamp_ms:
            raise ValueError(f"competition timestamp regressed at line {line_number}")
        last_timestamp_ms = record["timestamp_ms"]
        event = record.get("event")
        if not isinstance(event, str) or not event.strip():
            raise ValueError(f"competition event missing at line {line_number}")
        state = record.get("competition_state")
        if state not in {item.value for item in CompetitionState}:
            raise ValueError(f"competition state invalid at line {line_number}")
        robot_id = record.get("robot_id")
        if "robot_id" in record and robot_id not in {item.value for item in RobotId}:
            raise ValueError(f"competition robot_id invalid at line {line_number}")
        autonomy_state = record.get("autonomy_state")
        if "autonomy_state" in record and autonomy_state not in {item.value for item in AutonomyState}:
            raise ValueError(f"competition autonomy_state invalid at line {line_number}")
        if "safety_state" in record and not isinstance(record.get("safety_state"), str):
            raise ValueError(f"competition safety_state invalid at line {line_number}")
        if "armed" in record and not isinstance(record.get("armed"), bool):
            raise ValueError(f"competition armed state invalid at line {line_number}")
        if "reason" in record and not isinstance(record.get("reason"), str):
            raise ValueError(f"competition reason invalid at line {line_number}")
        if "data" in record and not isinstance(record.get("data"), dict):
            raise ValueError(f"competition data invalid at line {line_number}")
        current_session = record.get("session_id")
        if not isinstance(current_session, str) or not current_session:
            raise ValueError(f"competition session_id missing at line {line_number}")
        if session_id is None:
            session_id = current_session
        elif current_session != session_id:
            raise ValueError(f"competition session_id changed at line {line_number}")
        records.append(record)
    if not records:
        raise ValueError("competition log is empty")
    return records


def _validate_existing_bundle(
    bundle_dir: Path,
    session_id: str,
    digest: str,
    event_count: int,
    *,
    source_name: str,
    size_bytes: int,
) -> CompetitionBundle:
    staged_log = bundle_dir / "competition.jsonl"
    manifest_path = bundle_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        staged_digest = hashlib.sha256(staged_log.read_bytes()).hexdigest()
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"existing competition bundle is incomplete: {bundle_dir}: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or manifest.get("session_id") != session_id
        or type(manifest.get("created_at_ms")) is not int
        or manifest["created_at_ms"] < 0
        or manifest.get("source_name") != source_name
        or manifest.get("sha256") != digest
        or type(manifest.get("size_bytes")) is not int
        or manifest["size_bytes"] != size_bytes
        or type(manifest.get("event_count")) is not int
        or manifest["event_count"] != event_count
        or manifest.get("sync_status") != "AWAITING_REMOTE_CONFIGURATION"
        or staged_digest != digest
        or manifest.get("remote_transfer_performed") is not False
    ):
        raise ValueError(f"existing competition bundle failed integrity check: {bundle_dir}")
    return CompetitionBundle(bundle_dir, staged_log, manifest_path, session_id, digest, event_count)


def _merge_actions(
    left: Mapping[RobotId, tuple[AutonomyAction, ...]],
    right: Mapping[RobotId, tuple[AutonomyAction, ...]],
) -> dict[RobotId, tuple[AutonomyAction, ...]]:
    keys = sorted(set(left) | set(right), key=lambda robot_id: robot_id.value)
    return {robot_id: (*left.get(robot_id, ()), *right.get(robot_id, ())) for robot_id in keys}


def _redact(value: Any, key: str = "") -> Any:
    sensitive = ("password", "passwd", "secret", "token", "psk", "api_key", "private_key", "vault")
    if any(marker in key.lower() for marker in sensitive):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _require_local_path(path: str | Path, label: str) -> Path:
    text = str(path)
    if "://" in text or text.startswith(("\\\\", "//")):
        raise ValueError(f"{label} must be a local filesystem path")
    return Path(path)


def _validate_nonnegative_int(value: Any, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _robot_label(robot_id: Any) -> str:
    return robot_id.value if isinstance(robot_id, RobotId) else repr(robot_id)


def _safe_component(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    if not safe or safe in {".", ".."}:
        raise ValueError("competition session_id cannot form a safe bundle name")
    return safe[:80]
