"""Hardware-independent, fail-closed autonomy state-machine foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RobotId(str, Enum):
    R1 = "R1"
    R2 = "R2"


class AutonomyState(str, Enum):
    IDLE = "IDLE"
    READY_DISARMED = "READY_DISARMED"
    ARMED_READY = "ARMED_READY"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    FALLBACK = "FALLBACK"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"


class FailureAction(str, Enum):
    STOP = "STOP"
    SKIP = "SKIP"
    FALLBACK = "FALLBACK"


class ActionKind(str, Enum):
    RUN_STEP = "RUN_STEP"
    HOLD_REQUESTED = "HOLD_REQUESTED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    STEP_SKIPPED = "STEP_SKIPPED"
    RUN_FALLBACK = "RUN_FALLBACK"
    FALLBACK_SUCCEEDED = "FALLBACK_SUCCEEDED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    STOP_REQUESTED = "STOP_REQUESTED"


@dataclass(frozen=True)
class MissionStep:
    """One abstract mission step; it contains no actuator command."""

    step_id: str
    max_retries: int = 0
    retry_delay_ms: int = 0
    on_failure: FailureAction = FailureAction.STOP
    fallback_id: str | None = None

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("mission step_id must be non-empty")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("mission max_retries must be a non-negative integer")
        if type(self.retry_delay_ms) is not int or self.retry_delay_ms < 0:
            raise ValueError("mission retry_delay_ms must be a non-negative integer")
        if not isinstance(self.on_failure, FailureAction):
            raise ValueError("mission on_failure must be STOP, SKIP, or FALLBACK")
        if self.on_failure == FailureAction.FALLBACK and not self.fallback_id:
            raise ValueError("FALLBACK requires fallback_id")
        if self.on_failure != FailureAction.FALLBACK and self.fallback_id is not None:
            raise ValueError("fallback_id is only valid with FALLBACK")


@dataclass(frozen=True)
class MissionPlan:
    mission_id: str
    robot_id: RobotId
    steps: tuple[MissionStep, ...]

    def __post_init__(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id must be non-empty")
        if not isinstance(self.robot_id, RobotId):
            raise ValueError("mission robot_id must be R1 or R2")
        if not self.steps:
            raise ValueError("mission plan must contain at least one step")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("mission step_id values must be unique")


@dataclass(frozen=True)
class AutonomyAction:
    kind: ActionKind
    robot_id: RobotId
    mission_id: str
    step_id: str | None = None
    attempt: int | None = None
    reason: str | None = None
    fallback_id: str | None = None


@dataclass(frozen=True)
class AutonomyEvent:
    timestamp_ms: int
    state: AutonomyState
    event: str
    step_id: str | None = None
    attempt: int | None = None
    reason: str | None = None


@dataclass
class AutonomyStateMachine:
    """Coordinate mission policy without owning transport or motor authority."""

    plan: MissionPlan
    state: AutonomyState = AutonomyState.IDLE
    step_index: int = 0
    attempt: int = 0
    retry_deadline_ms: int | None = None
    active_fallback_id: str | None = None
    stop_reason: str | None = None
    skipped_steps: list[str] = field(default_factory=list)
    events: list[AutonomyEvent] = field(default_factory=list)

    @property
    def current_step(self) -> MissionStep | None:
        if 0 <= self.step_index < len(self.plan.steps):
            return self.plan.steps[self.step_index]
        return None

    def prepare(
        self,
        now_ms: int,
        *,
        required_nodes_ready: bool,
        safety_ready: bool,
    ) -> tuple[AutonomyAction, ...]:
        """Enter READY_DISARMED only when all external safety gates agree."""
        if self.state != AutonomyState.IDLE:
            return self._block(now_ms, f"prepare invalid from {self.state.value}")
        if not required_nodes_ready:
            return self._block(now_ms, "required nodes not ready")
        if not safety_ready:
            return self._block(now_ms, "safety not ready")
        self.state = AutonomyState.READY_DISARMED
        self._record(now_ms, "ready_disarmed")
        return ()

    def confirm_explicit_arm(self, now_ms: int, *, confirmed: bool) -> tuple[AutonomyAction, ...]:
        """Record an external explicit ARM confirmation; never request ARM."""
        if not confirmed:
            self._record(now_ms, "arm_not_confirmed")
            return ()
        if self.state != AutonomyState.READY_DISARMED:
            return self._block(now_ms, f"arm confirmation invalid from {self.state.value}")
        self.state = AutonomyState.ARMED_READY
        self._record(now_ms, "explicit_arm_confirmed")
        return ()

    def start(self, now_ms: int, *, explicit_start: bool) -> tuple[AutonomyAction, ...]:
        """Start only after separate explicit ARM and START confirmations."""
        if not explicit_start:
            self._record(now_ms, "start_not_confirmed")
            return ()
        if self.state != AutonomyState.ARMED_READY:
            return self._block(now_ms, f"start invalid from {self.state.value}")
        self.state = AutonomyState.RUNNING
        self.step_index = 0
        self.attempt = 1
        self._record(now_ms, "step_started", attempt=self.attempt)
        return (self._run_step_action(),)

    def record_step_success(self, now_ms: int) -> tuple[AutonomyAction, ...]:
        if self.state != AutonomyState.RUNNING or self.current_step is None:
            return self._block(now_ms, f"step success invalid from {self.state.value}")
        self._record(now_ms, "step_succeeded", attempt=self.attempt)
        return self._advance(now_ms)

    def record_step_failure(self, now_ms: int, reason: str) -> tuple[AutonomyAction, ...]:
        if self.state != AutonomyState.RUNNING or self.current_step is None:
            return self._block(now_ms, f"step failure invalid from {self.state.value}")
        step = self.current_step
        self._record(now_ms, "step_failed", attempt=self.attempt, reason=reason)
        if self.attempt <= step.max_retries:
            self.state = AutonomyState.RETRY_WAIT
            self.retry_deadline_ms = now_ms + step.retry_delay_ms
            self._record(now_ms, "retry_scheduled", attempt=self.attempt + 1, reason=reason)
            return (
                self._hold_action(reason),
                AutonomyAction(
                    ActionKind.RETRY_SCHEDULED,
                    self.plan.robot_id,
                    self.plan.mission_id,
                    step_id=step.step_id,
                    attempt=self.attempt + 1,
                    reason=reason,
                ),
            )
        if step.on_failure == FailureAction.SKIP:
            self.skipped_steps.append(step.step_id)
            self._record(now_ms, "step_skipped", attempt=self.attempt, reason=reason)
            skipped = AutonomyAction(
                ActionKind.STEP_SKIPPED,
                self.plan.robot_id,
                self.plan.mission_id,
                step_id=step.step_id,
                attempt=self.attempt,
                reason=reason,
            )
            return (self._hold_action(reason), skipped, *self._advance(now_ms))
        if step.on_failure == FailureAction.FALLBACK:
            self.state = AutonomyState.FALLBACK
            self.active_fallback_id = step.fallback_id
            self._record(now_ms, "fallback_started", attempt=self.attempt, reason=reason)
            return (
                self._hold_action(reason),
                AutonomyAction(
                    ActionKind.RUN_FALLBACK,
                    self.plan.robot_id,
                    self.plan.mission_id,
                    step_id=step.step_id,
                    attempt=self.attempt,
                    reason=reason,
                    fallback_id=step.fallback_id,
                ),
            )
        return self._stop(now_ms, reason)

    def tick(self, now_ms: int) -> tuple[AutonomyAction, ...]:
        """Release a scheduled retry at its deterministic deadline."""
        if self.state != AutonomyState.RETRY_WAIT:
            return ()
        if self.retry_deadline_ms is None:
            return self._block(now_ms, "retry deadline missing")
        if now_ms < self.retry_deadline_ms:
            return ()
        self.state = AutonomyState.RUNNING
        self.retry_deadline_ms = None
        self.attempt += 1
        self._record(now_ms, "step_retried", attempt=self.attempt)
        return (self._run_step_action(),)

    def record_fallback_result(
        self,
        now_ms: int,
        *,
        success: bool,
        reason: str | None = None,
    ) -> tuple[AutonomyAction, ...]:
        if self.state != AutonomyState.FALLBACK or self.current_step is None:
            return self._block(now_ms, f"fallback result invalid from {self.state.value}")
        step = self.current_step
        fallback_id = self.active_fallback_id
        if not success:
            return self._stop(now_ms, reason or f"fallback failed: {fallback_id}")
        self._record(now_ms, "fallback_succeeded", attempt=self.attempt)
        completed = AutonomyAction(
            ActionKind.FALLBACK_SUCCEEDED,
            self.plan.robot_id,
            self.plan.mission_id,
            step_id=step.step_id,
            attempt=self.attempt,
            fallback_id=fallback_id,
        )
        self.active_fallback_id = None
        return (completed, *self._advance(now_ms))

    def operator_stop(self, now_ms: int, reason: str = "operator stop") -> tuple[AutonomyAction, ...]:
        if self.state in {AutonomyState.STOPPED, AutonomyState.BLOCKED}:
            return ()
        return self._stop(now_ms, reason)

    def block(self, now_ms: int, reason: str) -> tuple[AutonomyAction, ...]:
        return self._block(now_ms, reason)

    def _advance(self, now_ms: int) -> tuple[AutonomyAction, ...]:
        self.step_index += 1
        self.attempt = 0
        self.retry_deadline_ms = None
        if self.step_index >= len(self.plan.steps):
            self.state = AutonomyState.COMPLETED
            self._record(now_ms, "mission_completed")
            return (
                AutonomyAction(
                    ActionKind.STOP_REQUESTED,
                    self.plan.robot_id,
                    self.plan.mission_id,
                    reason="mission completed",
                ),
                AutonomyAction(
                    ActionKind.MISSION_COMPLETED,
                    self.plan.robot_id,
                    self.plan.mission_id,
                ),
            )
        self.state = AutonomyState.RUNNING
        self.attempt = 1
        self._record(now_ms, "step_started", attempt=self.attempt)
        return (self._run_step_action(),)

    def _run_step_action(self) -> AutonomyAction:
        step = self.current_step
        if step is None:  # pragma: no cover - guarded by plan/state invariants
            raise RuntimeError("mission has no current step")
        return AutonomyAction(
            ActionKind.RUN_STEP,
            self.plan.robot_id,
            self.plan.mission_id,
            step_id=step.step_id,
            attempt=self.attempt,
        )

    def _hold_action(self, reason: str) -> AutonomyAction:
        step = self.current_step
        return AutonomyAction(
            ActionKind.HOLD_REQUESTED,
            self.plan.robot_id,
            self.plan.mission_id,
            step_id=step.step_id if step else None,
            attempt=self.attempt or None,
            reason=reason,
        )

    def _stop(self, now_ms: int, reason: str) -> tuple[AutonomyAction, ...]:
        self.state = AutonomyState.STOPPED
        self.stop_reason = reason
        self.retry_deadline_ms = None
        self.active_fallback_id = None
        self._record(now_ms, "stopped", reason=reason)
        return (
            AutonomyAction(
                ActionKind.STOP_REQUESTED,
                self.plan.robot_id,
                self.plan.mission_id,
                step_id=self.current_step.step_id if self.current_step else None,
                attempt=self.attempt or None,
                reason=reason,
            ),
        )

    def _block(self, now_ms: int, reason: str) -> tuple[AutonomyAction, ...]:
        self.state = AutonomyState.BLOCKED
        self.stop_reason = reason
        self.retry_deadline_ms = None
        self.active_fallback_id = None
        self._record(now_ms, "blocked", reason=reason)
        return (
            AutonomyAction(
                ActionKind.STOP_REQUESTED,
                self.plan.robot_id,
                self.plan.mission_id,
                step_id=self.current_step.step_id if self.current_step else None,
                attempt=self.attempt or None,
                reason=reason,
            ),
        )

    def _record(
        self,
        now_ms: int,
        event: str,
        *,
        attempt: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.events.append(
            AutonomyEvent(
                int(now_ms),
                self.state,
                event,
                step_id=self.current_step.step_id if self.current_step else None,
                attempt=attempt,
                reason=reason,
            )
        )


class FleetAutonomyCoordinator:
    """Keep R1/R2 state machines independent and provide fail-safe stop-all."""

    def __init__(self, machines: tuple[AutonomyStateMachine, ...]) -> None:
        by_robot = {machine.plan.robot_id: machine for machine in machines}
        if len(by_robot) != len(machines):
            raise ValueError("only one autonomy state machine is allowed per robot_id")
        self.machines = by_robot

    def machine(self, robot_id: RobotId) -> AutonomyStateMachine:
        return self.machines[robot_id]

    def stop_all(self, now_ms: int, reason: str) -> dict[RobotId, tuple[AutonomyAction, ...]]:
        return {
            robot_id: machine.operator_stop(now_ms, reason)
            for robot_id, machine in sorted(self.machines.items(), key=lambda item: item[0].value)
        }
