"""Deterministic Fake Robot E2E scenarios for the autonomy state machine."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from .app import ControllerApp
from .autonomy import (
    ActionKind,
    AutonomyState,
    AutonomyStateMachine,
    FailureAction,
    MissionPlan,
    MissionStep,
    RobotId,
)
from .config_manager import validate_vehicle_config
from .node_inventory import NodeRequirement, evaluate_node_inventory
from .protocol import arm_message, encode_message, hello_message
from .safety import SafetyState
from .serial_discovery import SerialProbe
from .virtual_serial import VirtualSerialLink


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms

    def advance(self, delta_ms: int) -> None:
        self.ms += delta_ms


@dataclass(frozen=True)
class FakeAutonomyResult:
    name: str
    passed: bool
    robot_id: str
    autonomy_state: str
    safety_state: str
    armed: bool
    reason: str | None


def _args(config_dir: str, trace: bool) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=config_dir,
        simulate=False,
        fake_esp32=True,
        fake_trace=trace,
        port=None,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        reconnect_interval=1.0,
        reconnect_handshake_timeout=0.5,
        auto_reconnect=True,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


def _build_ready_disarmed_app(config_dir: str, trace: bool) -> tuple[ControllerApp, ManualClock]:
    clock = ManualClock()
    app = ControllerApp(_args(config_dir, trace), now_ms=clock)
    if not isinstance(app.serial, VirtualSerialLink) or app.fake_device is None:
        raise RuntimeError("Fake ESP32 transport was not created")
    validate_vehicle_config(app.config, require_armable=True)
    app.seq = 1
    app.safety.apply_config()
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    if not app.safety.config_accepted or app.safety.state != SafetyState.SAFE:
        raise RuntimeError(f"Fake ESP32 did not reach READY_DISARMED: {app.safety.fault}")
    return app, clock


def _explicit_arm(app: ControllerApp, clock: ManualClock) -> None:
    if app.serial is None:
        raise RuntimeError("Fake ESP32 serial transport is closed")
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()
    if not app.safety.armed:
        raise RuntimeError(f"Fake ESP32 rejected explicit ARM: {app.safety.fault}")


def _tick_motion(app: ControllerApp, clock: ManualClock, vx: float, steps: int = 5) -> None:
    for _ in range(steps):
        clock.advance(20)
        app.tick(vx, 0.0, 0.0)


def _stop_fake_robot(app: ControllerApp, reason: str) -> None:
    app._send_zero_drive(armed=app.safety.armed)
    app._send_disarm(reason)
    app._read_serial_messages()


def _apply_hold_actions(
    app: ControllerApp,
    clock: ManualClock,
    actions: tuple[object, ...],
) -> bool:
    if not any(getattr(action, "kind", None) == ActionKind.HOLD_REQUESTED for action in actions):
        return False
    _tick_motion(app, clock, 0.0, steps=1)
    telemetry = app.last_telemetry or {}
    return telemetry.get("motor_pwm") == [0, 0, 0, 0]


def _close(app: ControllerApp) -> None:
    if app.serial is not None:
        app.serial.close()


def _drive_node_ready(app: ControllerApp) -> bool:
    if app.serial is None or app.fake_device is None:
        return False
    report = evaluate_node_inventory(
        (NodeRequirement("mcb44_drive_main", "drive", True),),
        [SerialProbe(port=app.serial.port, identity=app.fake_device.node_identity())],
    )
    return report.ready


def _scenario_stop_on_failure(config_dir: str, trace: bool) -> FakeAutonomyResult:
    app, clock = _build_ready_disarmed_app(config_dir, trace)
    machine = AutonomyStateMachine(
        MissionPlan("r2_stop_policy", RobotId.R2, (MissionStep("fake_drive"),))
    )
    try:
        machine.prepare(0, required_nodes_ready=_drive_node_ready(app), safety_ready=True)
        _explicit_arm(app, clock)
        machine.confirm_explicit_arm(clock.ms, confirmed=app.safety.armed)
        machine.start(clock.ms, explicit_start=True)
        _tick_motion(app, clock, 0.1)
        actions = machine.record_step_failure(clock.ms, "simulated task failure")
        if actions and actions[0].kind == ActionKind.STOP_REQUESTED:
            _stop_fake_robot(app, actions[0].reason or "autonomy stop")
        passed = (
            machine.state == AutonomyState.STOPPED
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device is not None
            and app.fake_device.motor_pwm == [0, 0, 0, 0]
            and not app.fake_device.armed
        )
        return FakeAutonomyResult(
            "stop_on_failure",
            passed,
            machine.plan.robot_id.value,
            machine.state.value,
            app.safety.state.value,
            app.safety.armed,
            machine.stop_reason,
        )
    finally:
        _close(app)


def _scenario_retry_skip_fallback(config_dir: str, trace: bool) -> FakeAutonomyResult:
    app, clock = _build_ready_disarmed_app(config_dir, trace)
    machine = AutonomyStateMachine(
        MissionPlan(
            "r1_policy_chain",
            RobotId.R1,
            (
                MissionStep("retry_task", max_retries=1, retry_delay_ms=40),
                MissionStep("optional_task", on_failure=FailureAction.SKIP),
                MissionStep(
                    "fallback_task",
                    on_failure=FailureAction.FALLBACK,
                    fallback_id="safe_stop",
                ),
            ),
        )
    )
    try:
        machine.prepare(0, required_nodes_ready=_drive_node_ready(app), safety_ready=True)
        _explicit_arm(app, clock)
        machine.confirm_explicit_arm(clock.ms, confirmed=app.safety.armed)
        machine.start(clock.ms, explicit_start=True)

        _tick_motion(app, clock, 0.1)
        retry = machine.record_step_failure(clock.ms, "transient")
        retry_held = _apply_hold_actions(app, clock, retry)
        before_deadline = machine.tick(clock.ms + 19)
        clock.advance(20)
        retry_run = machine.tick(clock.ms)
        _tick_motion(app, clock, 0.1)
        next_step = machine.record_step_success(clock.ms)
        skipped = machine.record_step_failure(clock.ms, "optional unavailable")
        skip_held = _apply_hold_actions(app, clock, skipped)
        fallback = machine.record_step_failure(clock.ms, "primary blocked")
        fallback_held = _apply_hold_actions(app, clock, fallback)

        _stop_fake_robot(app, "safe_stop fallback")
        completed = machine.record_fallback_result(clock.ms, success=True)
        event_names = [event.event for event in machine.events]
        passed = (
            [action.kind for action in retry]
            == [ActionKind.HOLD_REQUESTED, ActionKind.RETRY_SCHEDULED]
            and retry_held
            and before_deadline == ()
            and [action.kind for action in retry_run] == [ActionKind.RUN_STEP]
            and retry_run[0].attempt == 2
            and [action.kind for action in next_step] == [ActionKind.RUN_STEP]
            and [action.kind for action in skipped]
            == [ActionKind.HOLD_REQUESTED, ActionKind.STEP_SKIPPED, ActionKind.RUN_STEP]
            and skip_held
            and [action.kind for action in fallback]
            == [ActionKind.HOLD_REQUESTED, ActionKind.RUN_FALLBACK]
            and fallback_held
            and fallback[1].fallback_id == "safe_stop"
            and [action.kind for action in completed]
            == [
                ActionKind.FALLBACK_SUCCEEDED,
                ActionKind.STOP_REQUESTED,
                ActionKind.MISSION_COMPLETED,
            ]
            and machine.state == AutonomyState.COMPLETED
            and machine.skipped_steps == ["optional_task"]
            and {"step_retried", "step_skipped", "fallback_succeeded"}.issubset(event_names)
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device is not None
            and app.fake_device.motor_pwm == [0, 0, 0, 0]
        )
        return FakeAutonomyResult(
            "retry_skip_fallback",
            passed,
            machine.plan.robot_id.value,
            machine.state.value,
            app.safety.state.value,
            app.safety.armed,
            machine.stop_reason,
        )
    finally:
        _close(app)


def _scenario_missing_node_blocks_start(config_dir: str, trace: bool) -> FakeAutonomyResult:
    app, clock = _build_ready_disarmed_app(config_dir, trace)
    machine = AutonomyStateMachine(
        MissionPlan("r1_missing_node", RobotId.R1, (MissionStep("must_not_run"),))
    )
    try:
        missing_report = evaluate_node_inventory(
            (NodeRequirement("mcb44_drive_main", "drive", True),),
            (),
        )
        actions = machine.prepare(0, required_nodes_ready=missing_report.ready, safety_ready=True)
        if actions and actions[0].kind == ActionKind.STOP_REQUESTED:
            _stop_fake_robot(app, actions[0].reason or "required nodes not ready")
        writes = app.serial.writes if isinstance(app.serial, VirtualSerialLink) else []
        passed = (
            machine.state == AutonomyState.BLOCKED
            and machine.stop_reason == "required nodes not ready"
            and all(message.get("type") != "arm" for message in writes)
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device is not None
            and not app.fake_device.armed
        )
        return FakeAutonomyResult(
            "missing_node_blocks_start",
            passed,
            machine.plan.robot_id.value,
            machine.state.value,
            app.safety.state.value,
            app.safety.armed,
            machine.stop_reason,
        )
    finally:
        _close(app)


SCENARIOS = {
    "stop_on_failure": _scenario_stop_on_failure,
    "retry_skip_fallback": _scenario_retry_skip_fallback,
    "missing_node_blocks_start": _scenario_missing_node_blocks_start,
}


def run_fake_autonomy_scenarios(
    names: tuple[str, ...] | None = None,
    *,
    config_dir: str = "config",
    trace: bool = False,
) -> list[FakeAutonomyResult]:
    selected = names or tuple(SCENARIOS)
    unknown = [name for name in selected if name not in SCENARIOS]
    if unknown:
        raise ValueError(f"unknown Fake autonomy scenarios: {', '.join(unknown)}")
    return [SCENARIOS[name](config_dir, trace) for name in selected]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hardware-free autonomy/Fake Robot E2E scenarios")
    parser.add_argument("scenarios", nargs="*", default=None)
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    try:
        results = run_fake_autonomy_scenarios(
            tuple(args.scenarios) if args.scenarios else None,
            config_dir=args.config_dir,
            trace=args.trace,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for result in results:
        print(
            f"{result.name:26s} {'PASS' if result.passed else 'FAIL'} "
            f"robot={result.robot_id} autonomy={result.autonomy_state} "
            f"safety={result.safety_state} armed={str(result.armed).lower()} "
            f"reason={result.reason}",
            flush=True,
        )
    if all(result.passed for result in results):
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
