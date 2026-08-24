"""Hardware-free COMPETITION mode and post-session outbox E2E."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .autonomy import (
    ActionKind,
    AutonomyStateMachine,
    FleetAutonomyCoordinator,
    MissionPlan,
    MissionStep,
    RobotId,
)
from .competition import (
    CompetitionLogWriter,
    CompetitionSession,
    CompetitionState,
    _safe_component,
    prepare_post_competition_bundle,
)
from .fake_autonomy_scenarios import (
    _build_ready_disarmed_app,
    _close,
    _drive_node_ready,
    _explicit_arm,
    _stop_fake_robot,
    _tick_motion,
)
from .safety import SafetyState
from .virtual_serial import VirtualSerialLink


@dataclass(frozen=True)
class FakeCompetitionResult:
    passed: bool
    session_id: str
    competition_state: str
    autonomy_state: str
    safety_state: str
    armed: bool
    motor_pwm: tuple[int, int, int, int]
    log_path: Path
    bundle_dir: Path
    sha256: str
    event_count: int


def run_fake_competition(
    *,
    config_dir: str,
    output_dir: str | Path,
    session_id: str,
    trace: bool = False,
) -> FakeCompetitionResult:
    """Run one explicit, deterministic Fake competition and stage its log."""
    output = Path(output_dir)
    app, clock = _build_ready_disarmed_app(config_dir, trace)
    machine = AutonomyStateMachine(
        MissionPlan(
            "fake_competition_mission",
            RobotId.R1,
            (MissionStep("fake_forward"), MissionStep("fake_finish")),
        )
    )
    writer = CompetitionLogWriter(output / f"{_safe_component(session_id)}.jsonl", session_id)
    session = CompetitionSession(FleetAutonomyCoordinator((machine,)), writer)
    try:
        session.enable(clock.ms, explicit=True)
        session.precheck(
            clock.ms,
            required_nodes_ready={RobotId.R1: _drive_node_ready(app)},
            safety_ready={
                RobotId.R1: app.safety.state == SafetyState.SAFE and app.safety.config_accepted
            },
        )
        _explicit_arm(app, clock)
        session.confirm_explicit_arm(clock.ms, RobotId.R1, confirmed=app.safety.armed)
        session.start(clock.ms, explicit=True)

        _tick_motion(app, clock, 0.1, steps=5)
        session.record_step_result(clock.ms, RobotId.R1, success=True)
        _tick_motion(app, clock, 0.0, steps=2)
        final_actions = session.record_step_result(clock.ms, RobotId.R1, success=True)
        if any(
            action.kind == ActionKind.STOP_REQUESTED
            for actions in final_actions.values()
            for action in actions
        ):
            _stop_fake_robot(app, "competition mission completed")
        session.finalize(clock.ms)

        bundle = prepare_post_competition_bundle(
            writer.path,
            output / "outbox",
            created_at_ms=clock.ms,
        )
        writes = app.serial.writes if isinstance(app.serial, VirtualSerialLink) else []
        motor_pwm = tuple(int(value) for value in (app.fake_device.motor_pwm if app.fake_device else []))
        passed = (
            session.state == CompetitionState.POST_COMPETITION
            and machine.state.value == "COMPLETED"
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and motor_pwm == (0, 0, 0, 0)
            and sum(1 for message in writes if message.get("type") == "arm") == 1
            and bundle.log_path.read_bytes() == writer.path.read_bytes()
        )
        return FakeCompetitionResult(
            passed,
            session_id,
            session.state.value,
            machine.state.value,
            app.safety.state.value,
            app.safety.armed,
            motor_pwm,  # type: ignore[arg-type]
            writer.path,
            bundle.bundle_dir,
            bundle.sha256,
            bundle.event_count,
        )
    finally:
        if not writer.closed:
            writer.close()
        _close(app)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a hardware-free COMPETITION mode E2E")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    result = run_fake_competition(
        config_dir=args.config_dir,
        output_dir=args.output_dir,
        session_id=args.session_id,
        trace=args.trace,
    )
    print(
        f"fake_competition {'PASS' if result.passed else 'FAIL'} "
        f"competition={result.competition_state} autonomy={result.autonomy_state} "
        f"safety={result.safety_state} armed={str(result.armed).lower()} pwm={list(result.motor_pwm)}",
        flush=True,
    )
    print(
        f"log={result.log_path} bundle={result.bundle_dir} sha256={result.sha256} "
        f"events={result.event_count} remote_transfer=false",
        flush=True,
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
