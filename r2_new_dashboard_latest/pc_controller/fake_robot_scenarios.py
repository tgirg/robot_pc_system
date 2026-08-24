"""Scenario runner for Fake ESP32 failure-injection tests."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Iterable

from .app import ControllerApp
from .config_manager import validate_vehicle_config
from .controller_input import ControllerState
from .protocol import arm_message, disarm_message, encode_message, hello_message
from .safety import SafetyState
from .simulator import SimulatedEsp32, SimulatedFaultProfile
from .virtual_serial import VirtualSerialLink


def _make_args(config_dir: str, trace: bool) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=config_dir,
        simulate=False,
        fake_esp32=True,
        fake_trace=trace,
        port=None,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


class _ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return int(self.ms)

    def tick(self, delta_ms: int) -> None:
        self.ms += delta_ms


def _build_app(
    config_dir: str,
    trace: bool,
    seed: int | None = None,
    faults: SimulatedFaultProfile | None = None,
) -> tuple[ControllerApp, _ManualClock]:
    args = _make_args(config_dir, trace)
    clock = _ManualClock()
    app = ControllerApp(args, now_ms=clock)
    if not isinstance(app.serial, VirtualSerialLink):
        raise RuntimeError("fake ESP32 transport was not created")
    if faults is not None:
        app.fake_device = SimulatedEsp32(faults=faults, clock_ms=clock)
        app.serial.device = app.fake_device
    elif seed is not None:
        app.fake_device = SimulatedEsp32(faults=SimulatedFaultProfile(seed=seed), clock_ms=clock)
        app.serial.device = app.fake_device
    app.seq = 1
    return app, clock


def _handshake(app: ControllerApp) -> None:
    if app.serial is None:
        raise RuntimeError("fake serial transport is not connected")
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()


def _arm(app: ControllerApp) -> None:
    if app.serial is None:
        raise RuntimeError("fake serial transport is not connected")
    validate_vehicle_config(app.config, require_armable=True)
    if not app.safety.config_accepted:
        raise RuntimeError("config was not accepted before ARM")
    app.safety.request_arm(app._now_ms())
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()


def _tick(app: ControllerApp, clock: _ManualClock, steps: int, vx: float, vy: float, omega: float) -> None:
    for _ in range(steps):
        clock.tick(20)
        app.tick(vx, vy, omega)


def _safe_close(app: ControllerApp) -> None:
    if app.serial is not None:
        app.serial.close()


def _disarm_safely(app: ControllerApp) -> None:
    if app.serial is None:
        return
    app.safety.disarm("scenario cleanup")
    app.serial.write(encode_message(disarm_message()))
    app._read_serial_messages()


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    final_state: str
    final_armed: bool
    fault: str | None


def _scenario_normal(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 10, 0.10, 0.0, 0.0)
        return ScenarioResult(
            "normal",
            app.safety.state == SafetyState.NORMAL and app.safety.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _disarm_safely(app)
        _safe_close(app)


def _scenario_telemetry_timeout(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        app.fake_device.faults.telemetry_stop = True
        _tick(app, clock, 35, 0.20, 0.0, 0.0)
        return ScenarioResult(
            "telemetry_timeout",
            app.safety.state == SafetyState.SAFE and not app.safety.armed and app.safety.fault == "telemetry timeout",
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_disconnect(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        app.fake_device.disconnect()
        _tick(app, clock, 1, 0.20, 0.0, 0.0)
        return ScenarioResult(
            "disconnect",
            app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.serial is None
            and app.safety.fault == "serial write failed",
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_automatic_reconnect(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        assert isinstance(app.serial, VirtualSerialLink)
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        original_link = app.serial
        app.fake_device.disconnect()
        _tick(app, clock, 1, 0.20, 0.0, 0.0)
        disconnected_safe = (
            app.serial is None
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.safety.fault == "serial write failed"
        )
        _tick(app, clock, 51, 0.0, 0.0, 0.0)
        replacement_link = app.serial
        no_automatic_arm = (
            isinstance(replacement_link, VirtualSerialLink)
            and all(message.get("type") != "arm" for message in replacement_link.writes)
        )
        reconnect_trace = (
            isinstance(replacement_link, VirtualSerialLink)
            and bool(replacement_link.event_log)
            and all(bool(event.get("reconnect")) for event in replacement_link.event_log)
        )
        return ScenarioResult(
            "automatic_reconnect",
            disconnected_safe
            and replacement_link is not original_link
            and app.reconnect_phase == "ready_disarmed"
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.safety.config_accepted
            and app.fake_device.state == "SAFE"
            and not app.fake_device.armed
            and no_automatic_arm
            and reconnect_trace,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_reboot(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        app.fake_device.request_reboot()
        _tick(app, clock, 40, 0.20, 0.0, 0.0)
        return ScenarioResult(
            "reboot",
            app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device.state == "SAFE"
            and not app.fake_device.armed
            and app.fake_device.reboot_count == 1,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_malformed(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        app.fake_device.faults.malformed_json_count = 1
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        return ScenarioResult(
            "malformed",
            app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device.state == "SAFE"
            and not app.fake_device.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_explicit_fault(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        baseline_was_normal = app.fake_device.state == "NORMAL" and app.safety.state == SafetyState.NORMAL
        app.fake_device.faults.explicit_fault = "explicit scenario fault"
        app.fake_device.faults.explicit_fault_once = True
        app.fake_device.faults.explicit_fault_flags = 1
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        return ScenarioResult(
            "explicit_fault",
            baseline_was_normal
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device.state == "SAFE"
            and app.safety.fault == "explicit scenario fault",
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_controller_disconnect(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        app.tick_controller(ControllerState(False, ""))
        app._read_serial_messages()
        return ScenarioResult(
            "controller_disconnect",
            app.safety.state == SafetyState.SAFE and not app.safety.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_config_rejection(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.fake_device.faults.config_ack_ok = False
        app.safety.apply_config()
        _handshake(app)
        return ScenarioResult(
            "config_rejection",
            app.safety.state == SafetyState.SAFE and not app.safety.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_arm_rejection(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.fake_device.faults.arm_ack_ok = False
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        return ScenarioResult(
            "arm_rejection",
            app.safety.state == SafetyState.SAFE and not app.safety.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_sequence_regression(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        baseline_seq = app.safety.last_telemetry_seq
        app.fake_device.faults.telemetry_seq_regression_count = 1
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        emitted_seq = app.fake_device.last_emitted_telemetry_seq
        return ScenarioResult(
            "sequence_regression",
            isinstance(baseline_seq, int)
            and isinstance(emitted_seq, int)
            and emitted_seq < baseline_seq
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device.state == "SAFE"
            and not app.fake_device.armed
            and app.safety.fault == "telemetry sequence regression",
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


def _scenario_stale_telemetry(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        baseline_seq = app.safety.last_telemetry_seq
        baseline_fresh_ms = app.safety.last_valid_telemetry_ms
        app.fake_device.faults.telemetry_seq_stale = True
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        duplicate_seq = app.fake_device.last_emitted_telemetry_seq
        duplicate_was_ignored = app.safety.last_valid_telemetry_ms == baseline_fresh_ms
        app.fake_device.faults.telemetry_seq_stale = False
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        return ScenarioResult(
            "stale_telemetry",
            isinstance(baseline_seq, int)
            and duplicate_seq == baseline_seq
            and duplicate_was_ignored
            and app.safety.stale_telemetry_count == 1
            and app.safety.state == SafetyState.NORMAL
            and app.safety.armed,
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _disarm_safely(app)
        _safe_close(app)


def _scenario_command_receive_stop(config_dir: str, trace: bool, seed: int | None) -> ScenarioResult:
    app, clock = _build_app(config_dir, trace, seed=seed)
    try:
        assert app.fake_device is not None
        assert isinstance(app.serial, VirtualSerialLink)
        app.safety.apply_config()
        _handshake(app)
        _arm(app)
        _tick(app, clock, 1, 0.10, 0.0, 0.0)
        processed_before = app.fake_device.processed_command_count
        writes_before = len(app.serial.writes)
        app.fake_device.stop_command_reception()
        _tick(app, clock, 35, 0.20, 0.0, 0.0)
        sent_by_pc = len(app.serial.writes) > writes_before
        ignored_by_fake = app.fake_device.processed_command_count == processed_before
        return ScenarioResult(
            "command_receive_stop",
            sent_by_pc
            and ignored_by_fake
            and app.safety.state == SafetyState.SAFE
            and not app.safety.armed
            and app.fake_device.state == "SAFE"
            and not app.fake_device.armed
            and app.safety.fault == "ESP32 command timeout",
            app.safety.state.value,
            app.safety.armed,
            app.safety.fault,
        )
    finally:
        _safe_close(app)


SCENARIOS: dict[str, Callable[[str, bool, int | None], ScenarioResult]] = {
    "normal": _scenario_normal,
    "telemetry_timeout": _scenario_telemetry_timeout,
    "disconnect": _scenario_disconnect,
    "automatic_reconnect": _scenario_automatic_reconnect,
    "reboot": _scenario_reboot,
    "malformed": _scenario_malformed,
    "explicit_fault": _scenario_explicit_fault,
    "controller_disconnect": _scenario_controller_disconnect,
    "config_rejection": _scenario_config_rejection,
    "arm_rejection": _scenario_arm_rejection,
    "sequence_regression": _scenario_sequence_regression,
    "stale_telemetry": _scenario_stale_telemetry,
    "command_receive_stop": _scenario_command_receive_stop,
}


def _print_result(result: ScenarioResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"{result.name:20s} {status} "
        f"finalSafetyState={result.final_state} "
        f"finalArmed={str(result.final_armed).lower()} "
        f"fault={result.fault}",
        flush=True,
    )


def run_scenarios(
    names: Iterable[str],
    *,
    config_dir: str = "config",
    trace: bool = False,
    seed: int | None = None,
) -> list[ScenarioResult]:
    names_list = list(names)
    return [SCENARIOS[name](config_dir, trace, seed) for name in names_list]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Fake ESP32 scenarios")
    parser.add_argument(
        "scenarios",
        nargs="*",
        default=None,
        help="Scenario names. Defaults to all built-in scenarios.",
    )
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--trace", action="store_true", help="print virtual NDJSON TX/RX")
    parser.add_argument("--seed", type=int, default=7, help="seed for deterministic random faults")
    args = parser.parse_args()

    requested = args.scenarios or list(SCENARIOS)
    unknown = [name for name in requested if name not in SCENARIOS]
    if unknown:
        raise SystemExit(f"unknown scenarios: {', '.join(unknown)}")

    results = run_scenarios(requested, config_dir=args.config_dir, trace=args.trace, seed=args.seed)
    for result in results:
        _print_result(result)
    all_passed = all(result.passed for result in results)
    if all_passed:
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
