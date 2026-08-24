from __future__ import annotations

import pytest

from pc_controller.autonomy import (
    ActionKind,
    AutonomyState,
    AutonomyStateMachine,
    FailureAction,
    FleetAutonomyCoordinator,
    MissionPlan,
    MissionStep,
    RobotId,
)


def _machine(*steps: MissionStep, robot_id: RobotId = RobotId.R1) -> AutonomyStateMachine:
    return AutonomyStateMachine(MissionPlan("test_mission", robot_id, tuple(steps)))


def _ready_and_start(machine: AutonomyStateMachine) -> None:
    assert machine.prepare(0, required_nodes_ready=True, safety_ready=True) == ()
    assert machine.confirm_explicit_arm(1, confirmed=True) == ()
    actions = machine.start(2, explicit_start=True)
    assert [action.kind for action in actions] == [ActionKind.RUN_STEP]


def test_mission_plan_rejects_invalid_steps_and_duplicates() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        MissionPlan("empty", RobotId.R1, ())
    with pytest.raises(ValueError, match="must be unique"):
        MissionPlan("duplicate", RobotId.R1, (MissionStep("same"), MissionStep("same")))
    with pytest.raises(ValueError, match="FALLBACK requires fallback_id"):
        MissionStep("step", on_failure=FailureAction.FALLBACK)
    with pytest.raises(ValueError, match="only valid with FALLBACK"):
        MissionStep("step", fallback_id="safe_stop")
    with pytest.raises(ValueError, match="non-negative integer"):
        MissionStep("step", max_retries=1.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="STOP, SKIP, or FALLBACK"):
        MissionStep("step", on_failure="STOP")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="robot_id must be R1 or R2"):
        MissionPlan("robot", "R1", (MissionStep("step"),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("required_nodes_ready", "safety_ready", "reason"),
    [
        (False, True, "required nodes not ready"),
        (True, False, "safety not ready"),
    ],
)
def test_prepare_is_fail_closed_on_external_readiness_gates(
    required_nodes_ready: bool,
    safety_ready: bool,
    reason: str,
) -> None:
    machine = _machine(MissionStep("task"))

    actions = machine.prepare(
        0,
        required_nodes_ready=required_nodes_ready,
        safety_ready=safety_ready,
    )

    assert machine.state == AutonomyState.BLOCKED
    assert machine.stop_reason == reason
    assert [action.kind for action in actions] == [ActionKind.STOP_REQUESTED]


def test_ready_disarmed_never_starts_without_explicit_arm_and_start() -> None:
    machine = _machine(MissionStep("task"))

    assert machine.prepare(0, required_nodes_ready=True, safety_ready=True) == ()
    assert machine.state == AutonomyState.READY_DISARMED
    assert machine.confirm_explicit_arm(1, confirmed=False) == ()
    assert machine.start(2, explicit_start=False) == ()
    assert machine.state == AutonomyState.READY_DISARMED

    actions = machine.start(3, explicit_start=True)
    assert machine.state == AutonomyState.BLOCKED
    assert [action.kind for action in actions] == [ActionKind.STOP_REQUESTED]
    assert machine.stop_reason == "start invalid from READY_DISARMED"


def test_normal_mission_advances_and_completes() -> None:
    machine = _machine(MissionStep("first"), MissionStep("second"), robot_id=RobotId.R2)

    _ready_and_start(machine)
    next_actions = machine.record_step_success(10)
    complete_actions = machine.record_step_success(20)

    assert machine.plan.robot_id == RobotId.R2
    assert [action.kind for action in next_actions] == [ActionKind.RUN_STEP]
    assert next_actions[0].step_id == "second"
    assert [action.kind for action in complete_actions] == [
        ActionKind.STOP_REQUESTED,
        ActionKind.MISSION_COMPLETED,
    ]
    assert complete_actions[0].reason == "mission completed"
    assert machine.state == AutonomyState.COMPLETED


def test_retry_uses_exact_deadline_and_stops_after_budget() -> None:
    machine = _machine(MissionStep("retrying", max_retries=2, retry_delay_ms=100))
    _ready_and_start(machine)

    first = machine.record_step_failure(10, "temporary")
    assert [action.kind for action in first] == [ActionKind.HOLD_REQUESTED, ActionKind.RETRY_SCHEDULED]
    assert first[1].attempt == 2
    assert machine.state == AutonomyState.RETRY_WAIT
    assert machine.tick(109) == ()
    assert [action.attempt for action in machine.tick(110)] == [2]

    second = machine.record_step_failure(120, "temporary")
    assert [action.kind for action in second] == [ActionKind.HOLD_REQUESTED, ActionKind.RETRY_SCHEDULED]
    assert second[1].attempt == 3
    assert machine.tick(219) == ()
    assert [action.attempt for action in machine.tick(220)] == [3]

    final = machine.record_step_failure(230, "permanent")
    assert [action.kind for action in final] == [ActionKind.STOP_REQUESTED]
    assert machine.state == AutonomyState.STOPPED
    assert machine.stop_reason == "permanent"


def test_zero_delay_retry_emits_only_one_attempt_per_tick() -> None:
    machine = _machine(MissionStep("retrying", max_retries=1, retry_delay_ms=0))
    _ready_and_start(machine)
    machine.record_step_failure(10, "temporary")

    released = machine.tick(10)

    assert [action.kind for action in released] == [ActionKind.RUN_STEP]
    assert released[0].attempt == 2
    assert machine.tick(10) == ()
    assert machine.state == AutonomyState.RUNNING


def test_skip_records_failure_and_advances_without_retry() -> None:
    machine = _machine(
        MissionStep("optional", on_failure=FailureAction.SKIP),
        MissionStep("required"),
    )
    _ready_and_start(machine)

    actions = machine.record_step_failure(10, "not available")

    assert [action.kind for action in actions] == [
        ActionKind.HOLD_REQUESTED,
        ActionKind.STEP_SKIPPED,
        ActionKind.RUN_STEP,
    ]
    assert actions[2].step_id == "required"
    assert machine.skipped_steps == ["optional"]
    assert machine.state == AutonomyState.RUNNING


def test_fallback_success_advances_and_failure_stops() -> None:
    success_machine = _machine(
        MissionStep("primary", on_failure=FailureAction.FALLBACK, fallback_id="safe_route"),
        MissionStep("finish"),
    )
    _ready_and_start(success_machine)

    fallback = success_machine.record_step_failure(10, "route blocked")
    advanced = success_machine.record_fallback_result(20, success=True)

    assert [action.kind for action in fallback] == [ActionKind.HOLD_REQUESTED, ActionKind.RUN_FALLBACK]
    assert fallback[1].fallback_id == "safe_route"
    assert [action.kind for action in advanced] == [ActionKind.FALLBACK_SUCCEEDED, ActionKind.RUN_STEP]
    assert success_machine.current_step == MissionStep("finish")

    failure_machine = _machine(
        MissionStep("primary", on_failure=FailureAction.FALLBACK, fallback_id="safe_stop")
    )
    _ready_and_start(failure_machine)
    failure_machine.record_step_failure(10, "blocked")
    stopped = failure_machine.record_fallback_result(20, success=False, reason="safe stop unavailable")

    assert [action.kind for action in stopped] == [ActionKind.STOP_REQUESTED]
    assert failure_machine.state == AutonomyState.STOPPED
    assert failure_machine.stop_reason == "safe stop unavailable"


def test_invalid_result_transition_blocks_and_requests_stop() -> None:
    machine = _machine(MissionStep("task"))

    actions = machine.record_step_success(0)

    assert machine.state == AutonomyState.BLOCKED
    assert [action.kind for action in actions] == [ActionKind.STOP_REQUESTED]
    assert machine.stop_reason == "step success invalid from IDLE"


def test_operator_stop_is_terminal_and_idempotent() -> None:
    machine = _machine(MissionStep("task"))
    _ready_and_start(machine)

    actions = machine.operator_stop(10, "field stop")

    assert [action.kind for action in actions] == [ActionKind.STOP_REQUESTED]
    assert machine.state == AutonomyState.STOPPED
    assert machine.operator_stop(11, "duplicate") == ()
    assert machine.stop_reason == "field stop"


def test_fleet_keeps_r1_r2_independent_and_stop_all_is_fail_safe() -> None:
    r1 = _machine(MissionStep("r1_task"), robot_id=RobotId.R1)
    r2 = _machine(MissionStep("r2_task"), robot_id=RobotId.R2)
    fleet = FleetAutonomyCoordinator((r2, r1))
    _ready_and_start(r1)
    assert r2.prepare(0, required_nodes_ready=True, safety_ready=True) == ()

    actions = fleet.stop_all(10, "competition stop")

    assert fleet.machine(RobotId.R1) is r1
    assert fleet.machine(RobotId.R2) is r2
    assert list(actions) == [RobotId.R1, RobotId.R2]
    assert r1.state == AutonomyState.STOPPED
    assert r2.state == AutonomyState.STOPPED
    assert all(items[0].kind == ActionKind.STOP_REQUESTED for items in actions.values())


def test_fleet_rejects_duplicate_machine_for_same_robot() -> None:
    r1_a = _machine(MissionStep("a"), robot_id=RobotId.R1)
    r1_b = _machine(MissionStep("b"), robot_id=RobotId.R1)

    with pytest.raises(ValueError, match="one autonomy state machine"):
        FleetAutonomyCoordinator((r1_a, r1_b))
