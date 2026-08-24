"""Deterministic no-hardware smoke test for the PC controller stack."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

from .app import ControllerApp
from .config_manager import validate_vehicle_config
from .protocol import arm_message, disarm_message, encode_message, hello_message
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


def _run_ticks(app: ControllerApp, clock: SimpleNamespace, vx: float, vy: float, omega: float, count: int) -> dict[str, object]:
    for _ in range(count):
        clock.ms += 20
        app.tick(vx, vy, omega)
    return dict(app.last_telemetry or {})


def run_demo(config_dir: str = "config", *, trace: bool = False) -> list[tuple[str, dict[str, object]]]:
    """Run forward, strafe, pivot, and stop through the fake serial stack."""
    clock = SimpleNamespace(ms=0)
    app = ControllerApp(_make_args(config_dir, trace), now_ms=lambda: int(clock.ms))
    if not isinstance(app.serial, VirtualSerialLink):
        raise RuntimeError("fake ESP32 transport was not created")

    validate_vehicle_config(app.config, require_armable=True)
    app.seq = 1
    app.safety.apply_config()
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()

    if not app.safety.config_accepted:
        raise RuntimeError(f"fake ESP32 rejected config: {app.safety.fault}")
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()
    if not app.safety.armed:
        raise RuntimeError(f"fake ESP32 rejected ARM: {app.safety.fault}")

    motion = app.config.get("motion", {})
    max_linear = float(motion.get("max_linear_speed_mps", 1.0))
    max_angular = float(motion.get("max_angular_speed_radps", 1.0))
    linear = max_linear * float(app.mapping.get("linear_scale", 0.12))
    angular = max_angular * float(app.mapping.get("angular_scale", 0.35))

    results: list[tuple[str, dict[str, object]]] = []
    results.append(("forward", _run_ticks(app, clock, linear, 0.0, 0.0, 20)))
    results.append(("stop_after_forward", _run_ticks(app, clock, 0.0, 0.0, 0.0, 5)))
    results.append(("strafe", _run_ticks(app, clock, 0.0, linear, 0.0, 20)))
    results.append(("stop_after_strafe", _run_ticks(app, clock, 0.0, 0.0, 0.0, 5)))
    results.append(("pivot", _run_ticks(app, clock, 0.0, 0.0, angular, 45)))
    results.append(("final_stop", _run_ticks(app, clock, 0.0, 0.0, 0.0, 5)))

    app.serial.write(encode_message(disarm_message()))
    app._read_serial_messages()
    app.serial.close()
    return results


def _format_row(name: str, telemetry: dict[str, object]) -> str:
    return (
        f"{name:18s} "
        f"state={telemetry.get('state', '?')} "
        f"armed={telemetry.get('armed', '?')} "
        f"pwm={telemetry.get('motor_pwm', '?')} "
        f"rpm={telemetry.get('wheel_rpm', '?')} "
        f"servo={telemetry.get('servo_deg', '?')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a no-hardware robot controller smoke test")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--trace", action="store_true", help="print virtual NDJSON TX/RX")
    args = parser.parse_args()

    results = run_demo(args.config_dir, trace=args.trace)
    print("fake robot smoke test", flush=True)
    for name, telemetry in results:
        print(_format_row(name, telemetry), flush=True)

    by_name = dict(results)
    forward_pwm = by_name.get("forward", {}).get("motor_pwm", [])
    pivot_pwm = by_name.get("pivot", {}).get("motor_pwm", [])
    final_pwm = by_name.get("final_stop", {}).get("motor_pwm", [])
    if not (isinstance(forward_pwm, list) and any(abs(int(v)) > 0 for v in forward_pwm)):
        raise SystemExit("FAIL: forward motion produced no PWM")
    if not (isinstance(pivot_pwm, list) and any(abs(int(v)) > 0 for v in pivot_pwm)):
        raise SystemExit("FAIL: pivot motion produced no PWM")
    if final_pwm != [0, 0, 0, 0]:
        raise SystemExit(f"FAIL: final stop PWM was {final_pwm}")
    print("PASS: PC control -> protocol -> fake ESP32 -> telemetry", flush=True)


if __name__ == "__main__":
    main()
