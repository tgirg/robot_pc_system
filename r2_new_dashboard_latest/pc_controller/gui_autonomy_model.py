"""Read-only Autonomy screen model derived from immutable GUI snapshots.

The model exposes state-machine policy and retained events only.  It owns no
executor, ControllerApp, transport, ARM, START, STOP, SKIP, fallback, or direct
state-transition API.  HOLD/STOP are labelled as state-machine requests rather
than actuator/executor confirmations.
"""

from __future__ import annotations

from dataclasses import dataclass

from .autonomy import RobotId
from .gui_model import AutonomyEventSnapshot, AutonomySnapshot, RobotDashboardSnapshot


_STATE_NAMES = {
    "IDLE": "Idle",
    "READY_DISARMED": "Ready / disarmed",
    "ARMED_READY": "Armed / ready",
    "RUNNING": "Running",
    "RETRY_WAIT": "Retry wait",
    "FALLBACK": "Fallback",
    "COMPLETED": "Completed",
    "STOPPED": "Stopped",
    "BLOCKED": "Blocked",
}

_STATUS_BY_STATE = {
    "IDLE": "PLAN_IDLE",
    "READY_DISARMED": "WAITING_FOR_EXTERNAL_EXPLICIT_ARM_CONFIRMATION",
    "ARMED_READY": "WAITING_FOR_EXTERNAL_EXPLICIT_START",
    "RUNNING": "MISSION_STEP_RUNNING",
    "RETRY_WAIT": "WAITING_FOR_RETRY_DEADLINE",
    "FALLBACK": "FALLBACK_POLICY_ACTIVE",
    "COMPLETED": "MISSION_COMPLETED_STOP_REQUESTED",
    "STOPPED": "STOP_REQUESTED",
    "BLOCKED": "BLOCKED_STOP_REQUESTED",
}


@dataclass(frozen=True)
class AutonomyScreenSnapshot:
    robot_id: RobotId
    controller_configured: bool
    autonomy_configured: bool
    snapshot_timestamp_ms: int
    state_id: str
    state_name: str
    status: str
    mission_id: str | None
    step_position: int | None
    step_count: int | None
    current_step: str | None
    current_target: str | None
    next_step: str | None
    next_state: str
    next_state_condition: str
    attempt: int | None
    max_retries: int | None
    retry_delay_ms: int | None
    retry_deadline_ms: int | None
    retry_remaining_ms: int | None
    timeout_state: str
    failure_action: str | None
    hold_context: str
    stop_context: str
    skipped_steps: tuple[str, ...]
    active_fallback_id: str | None
    configured_fallback_id: str | None
    blocked_reason: str | None
    terminal_reason: str | None
    recent_events: tuple[AutonomyEventSnapshot, ...]
    executor_confirmation: str
    control_boundary: str


def build_autonomy_screen_snapshot(robot: RobotDashboardSnapshot) -> AutonomyScreenSnapshot:
    """Build an output-free view of one robot's current autonomy context."""
    robot_id = _robot_id(robot)
    autonomy = robot.autonomy
    if not autonomy.configured:
        return AutonomyScreenSnapshot(
            robot_id=robot_id,
            controller_configured=bool(robot.configured),
            autonomy_configured=False,
            snapshot_timestamp_ms=int(robot.timestamp_ms),
            state_id="NOT_CONFIGURED",
            state_name="Not configured",
            status="NO_AUTONOMY_MACHINE_IN_SHARED_RUNTIME",
            mission_id=None,
            step_position=None,
            step_count=None,
            current_step=None,
            current_target=None,
            next_step=None,
            next_state="UNKNOWN",
            next_state_condition="AUTONOMY_MACHINE_REQUIRED",
            attempt=None,
            max_retries=None,
            retry_delay_ms=None,
            retry_deadline_ms=None,
            retry_remaining_ms=None,
            timeout_state="NOT_CONFIGURED",
            failure_action=None,
            hold_context="NOT_AVAILABLE",
            stop_context="NOT_AVAILABLE",
            skipped_steps=(),
            active_fallback_id=None,
            configured_fallback_id=None,
            blocked_reason=None,
            terminal_reason=None,
            recent_events=(),
            executor_confirmation="NOT_AVAILABLE",
            control_boundary="READ_ONLY_NO_TRANSITION_OR_EXECUTOR_API",
        )

    state = autonomy.state or "UNKNOWN"
    next_state, condition = _next_state(autonomy)
    retry_remaining = None
    if autonomy.retry_deadline_ms is not None:
        retry_remaining = max(0, int(autonomy.retry_deadline_ms) - int(robot.timestamp_ms))
    return AutonomyScreenSnapshot(
        robot_id=robot_id,
        controller_configured=bool(robot.configured),
        autonomy_configured=True,
        snapshot_timestamp_ms=int(robot.timestamp_ms),
        state_id=state,
        state_name=_STATE_NAMES.get(state, state),
        status=_STATUS_BY_STATE.get(state, "UNKNOWN_STATE"),
        mission_id=autonomy.mission_id,
        step_position=autonomy.step_index + 1 if autonomy.step_index is not None else None,
        step_count=autonomy.step_count,
        current_step=autonomy.current_step,
        # MissionStep retains a policy step ID, not a physical task/pose target.
        # Keep the target absent until an authoritative mission target contract exists.
        current_target=None,
        next_step=autonomy.next_step,
        next_state=next_state,
        next_state_condition=condition,
        attempt=autonomy.attempt,
        max_retries=autonomy.max_retries,
        retry_delay_ms=autonomy.retry_delay_ms,
        retry_deadline_ms=autonomy.retry_deadline_ms,
        retry_remaining_ms=retry_remaining,
        timeout_state="NOT_CONFIGURED_IN_MISSION_STEP_CONTRACT",
        failure_action=autonomy.failure_action,
        hold_context=_request_context(
            autonomy.recent_events,
            ("retry_scheduled", "step_skipped", "fallback_started"),
            request="HOLD_REQUESTED",
        ),
        stop_context=_request_context(
            autonomy.recent_events,
            ("stopped", "blocked", "mission_completed"),
            request="STOP_REQUESTED",
        ),
        skipped_steps=autonomy.skipped_steps,
        active_fallback_id=autonomy.fallback_id,
        configured_fallback_id=autonomy.configured_fallback_id,
        blocked_reason=autonomy.reason if state == "BLOCKED" else None,
        terminal_reason=autonomy.reason if state in {"BLOCKED", "STOPPED"} else None,
        recent_events=autonomy.recent_events,
        executor_confirmation="UNKNOWN_NOT_RETAINED_BY_STATE_MACHINE",
        control_boundary="READ_ONLY_NO_ARM_START_STOP_SKIP_FALLBACK_OR_STATE_TRANSITION",
    )


def _robot_id(robot: RobotDashboardSnapshot) -> RobotId:
    try:
        return RobotId(robot.robot_id)
    except ValueError as exc:
        raise ValueError("autonomy screen robot_id must be R1 or R2") from exc


def _request_context(
    events: tuple[AutonomyEventSnapshot, ...],
    event_names: tuple[str, ...],
    *,
    request: str,
) -> str:
    event = next((item for item in reversed(events) if item.event in event_names), None)
    if event is None:
        return "NONE_RECORDED_IN_SNAPSHOT"
    return (
        f"LAST_RETAINED_{request}@{event.timestamp_ms}ms via {event.event}; "
        "EXECUTOR_CONFIRMATION=UNKNOWN"
    )


def _next_state(autonomy: AutonomySnapshot) -> tuple[str, str]:
    state = autonomy.state
    if state == "IDLE":
        return "READY_DISARMED | BLOCKED", "prepare() result depends on required-node and Safety gates"
    if state == "READY_DISARMED":
        return "ARMED_READY", "only after external explicit ARM confirmation"
    if state == "ARMED_READY":
        return "RUNNING", "only after separate external explicit START"
    if state == "RETRY_WAIT":
        return "RUNNING", "tick() at or after retry_deadline_ms"
    if state == "FALLBACK":
        success = "RUNNING" if autonomy.next_step is not None else "COMPLETED"
        return f"{success} | STOPPED", "fallback result: success advances; failure requests STOP"
    if state == "RUNNING":
        success = "RUNNING" if autonomy.next_step is not None else "COMPLETED"
        if (
            autonomy.attempt is not None
            and autonomy.max_retries is not None
            and autonomy.attempt <= autonomy.max_retries
        ):
            failure = "RETRY_WAIT"
        elif autonomy.failure_action == "STOP":
            failure = "STOPPED"
        elif autonomy.failure_action == "FALLBACK":
            failure = "FALLBACK"
        elif autonomy.failure_action == "SKIP":
            failure = success
        else:
            failure = "UNKNOWN"
        return f"success={success} | failure={failure}", "step result and configured failure policy"
    if state in {"COMPLETED", "STOPPED", "BLOCKED"}:
        return "NONE", "terminal state"
    return "UNKNOWN", "state is unavailable or not recognized"
