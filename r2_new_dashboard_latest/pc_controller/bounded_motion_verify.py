"""Bounded real R2 verification for pivot direction and inner/outer commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .app import ControllerApp
from .controller_input import ControllerState, correct_controller_axis
from .wheel_pairing_check import PairingSession, _firmware_config_message


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WHEEL_NAMES = ("FL", "FR", "RL", "RR")


def summarize_pattern(
    name: str,
    command: Mapping[str, Any],
    count_before: list[int],
    count_after: list[int],
) -> dict[str, Any]:
    if len(count_before) != 4 or len(count_after) != 4:
        raise ValueError("encoder counts must contain 4 entries")
    targets = [int(round(float(value))) for value in command.get("drive_target", [])]
    steer = [float(value) for value in command.get("steer_deg", [])]
    if len(targets) != 4 or len(steer) != 4:
        raise ValueError("drive command must contain 4 targets and 4 steering angles")
    delta = [end - start for start, end in zip(count_before, count_after, strict=True)]
    moving_sign_match = [
        abs(delta[index]) < 20 or (delta[index] > 0) == (targets[index] > 0)
        for index in range(4)
        if targets[index] != 0
    ]
    summary: dict[str, Any] = {
        "name": name,
        "steer_deg": steer,
        "drive_target": targets,
        "count_before": count_before,
        "count_after": count_after,
        "count_delta": delta,
        "encoder_sign_matches_command": bool(moving_sign_match) and all(moving_sign_match),
    }
    if name == "right_pivot":
        summary["expected_target_signs"] = [-1, 1, 1, -1]
        summary["pivot_target_signs_ok"] = [(-1 if value < 0 else 1 if value > 0 else 0) for value in targets] == [-1, 1, 1, -1]
    if name == "forward_right_arc":
        magnitudes = [abs(value) for value in targets]
        summary["physical_inner_old_logical"] = ["FR", "RR"]
        summary["physical_outer_old_logical"] = ["FL", "RL"]
        summary["inner_outer_command_ok"] = magnitudes[1] < magnitudes[0] and magnitudes[3] < magnitudes[2]
    return summary


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _profile_command(config_dir: Path, name: str, max_pwm: int) -> dict[str, Any]:
    args = argparse.Namespace(
        config_dir=str(config_dir),
        simulate=True,
        port=None,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )
    app = ControllerApp(args)
    app.config["motion"]["open_loop_max_pwm"] = max_pwm
    app.config["motion"]["pivot_max_pwm"] = max_pwm
    now_ms = [0]
    app._now_ms = lambda: now_ms[0]  # type: ignore[method-assign]
    app.safety.apply_config()
    app.safety.arm(0)
    mapping = app.mapping
    deadzone = float(mapping.get("deadzone", 0.12))
    forward = correct_controller_axis(-1.0, bool(mapping.get("invert_vx", False)), deadzone)
    turn_right = correct_controller_axis(1.0, bool(mapping.get("invert_omega", False)), deadzone)
    state = (
        ControllerState(True, "bounded profile", omega=turn_right)
        if name == "right_pivot"
        else ControllerState(True, "bounded profile", vx=forward, omega=turn_right)
    )
    for step in range(45):
        now_ms[0] = step * 20
        app.tick_controller(state)
    command = dict(app.last_drive_command or {})
    targets = [float(value) for value in command.get("drive_target", [])]
    if len(targets) != 4:
        raise RuntimeError(f"failed to build {name} drive targets")
    command["drive_target"] = [max(-max_pwm, min(max_pwm, int(round(value)))) for value in targets]
    return command


def run_bounded_verification(
    *,
    port: str,
    max_pwm: int,
    duration_s: float,
    config_dir: Path,
) -> dict[str, Any]:
    if max_pwm < 20 or max_pwm > 60:
        raise ValueError("bounded verification requires max PWM 20..60")
    if duration_s < 0.8 or duration_s > 3.0:
        raise ValueError("bounded verification requires duration 0.8..3.0 s")

    vehicle_config = _load_json(config_dir / "vehicle_config.json")
    controller_mapping = _load_json(config_dir / "controller_mapping.json")
    profiles = [
        (name, _profile_command(config_dir, name, max_pwm))
        for name in ("right_pivot", "forward_right_arc")
    ]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    serial_log = PROJECT_ROOT / "logs" / f"bounded-motion-serial-{stamp}.jsonl"
    results: list[dict[str, Any]] = []
    final_telemetry: dict[str, Any] | None = None

    with PairingSession(port, vehicle_config, log_path=serial_log) as session:
        hello = session.handshake(_firmware_config_message(vehicle_config), arm_mode="normal")
        print(
            f"identity: firmware={hello.get('firmware')} board={hello.get('board')} "
            f"pca9685_ok={hello.get('pca9685_ok')}",
            flush=True,
        )
        for name, command in profiles:
            before, after = session.drive_profile(
                command["steer_deg"],
                command["drive_target"],
                duration_s=duration_s,
            )
            result = summarize_pattern(name, command, before, after)
            results.append(result)
            print(
                f"{name}: steer={[round(v, 1) for v in result['steer_deg']]} "
                f"target={result['drive_target']} delta={result['count_delta']}",
                flush=True,
            )
        final_telemetry = session.force_safe()

    return {
        "port": port,
        "max_pwm": max_pwm,
        "duration_s": duration_s,
        "controller_mapping": controller_mapping,
        "patterns": results,
        "final_telemetry": final_telemetry,
        "serial_log": str(serial_log),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run two bounded R2 live motion patterns")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--max-pwm", type=int, default=60)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--wheels-lifted", action="store_true", help="required physical safety confirmation")
    parser.add_argument("--config-dir", type=Path, default=PROJECT_ROOT / "config")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.wheels_lifted:
        raise SystemExit("refusing to move: pass --wheels-lifted after lifting all four wheels")
    result = run_bounded_verification(
        port=args.port,
        max_pwm=args.max_pwm,
        duration_s=args.duration,
        config_dir=args.config_dir,
    )
    output = args.output or PROJECT_ROOT / "logs" / f"bounded-motion-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {output}", flush=True)
    print(f"final: {result['final_telemetry']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
