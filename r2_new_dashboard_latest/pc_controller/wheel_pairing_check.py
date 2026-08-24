"""Bounded real-hardware motor/encoder pairing diagnostic.

This command intentionally uses DEBUG mode, drives only one logical wheel at a
time, and always attempts motor-stop plus DISARM before closing the serial port.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .protocol import arm_message, debug_message, disarm_message, drive_message, encode_message, hello_message
from .serial_link import SerialLink


WHEEL_NAMES = ("FL", "FR", "RL", "RR")
DEFAULT_PORT = "COM7"
DEFAULT_PWM = 40
DEFAULT_DURATION_S = 0.75
KEEPALIVE_INTERVAL_S = 0.18
MIN_PAIRING_COUNT = 20


@dataclass(frozen=True)
class PairingObservation:
    commanded_logical: int
    commanded_name: str
    commanded_motor_physical: int
    direction: str
    count_before: list[int]
    count_after: list[int]
    count_delta: list[int]
    dominant_encoder_logical: int | None
    dominant_encoder_name: str | None
    dominant_encoder_physical: int | None
    dominant_delta: int
    second_abs_delta: int
    pairing_confirmed: bool


def analyze_pairing_observation(
    *,
    commanded_logical: int,
    direction: str,
    count_before: Iterable[int],
    count_after: Iterable[int],
    vehicle_config: Mapping[str, Any],
    min_pairing_count: int = MIN_PAIRING_COUNT,
) -> PairingObservation:
    before = [int(value) for value in count_before]
    after = [int(value) for value in count_after]
    if len(before) != 4 or len(after) != 4:
        raise ValueError("encoder_count must contain 4 entries")
    if commanded_logical < 0 or commanded_logical >= 4:
        raise ValueError("commanded logical wheel must be 0..3")

    motors = list(vehicle_config.get("motors") or [])
    encoders = list(vehicle_config.get("encoders") or [])
    if len(motors) != 4 or len(encoders) != 4:
        raise ValueError("vehicle config must contain 4 motors and 4 encoders")

    delta = [end - start for start, end in zip(before, after, strict=True)]
    ranked = sorted(range(4), key=lambda index: abs(delta[index]), reverse=True)
    dominant = ranked[0]
    dominant_delta = delta[dominant]
    second_abs_delta = abs(delta[ranked[1]])
    confirmed = abs(dominant_delta) >= int(min_pairing_count) and (
        second_abs_delta == 0 or abs(dominant_delta) >= second_abs_delta * 4
    )
    dominant_logical = dominant if confirmed else None

    return PairingObservation(
        commanded_logical=commanded_logical,
        commanded_name=WHEEL_NAMES[commanded_logical],
        commanded_motor_physical=int(motors[commanded_logical]["physical"]),
        direction=direction,
        count_before=before,
        count_after=after,
        count_delta=delta,
        dominant_encoder_logical=dominant_logical,
        dominant_encoder_name=WHEEL_NAMES[dominant] if confirmed else None,
        dominant_encoder_physical=int(encoders[dominant]["physical"]) if confirmed else None,
        dominant_delta=dominant_delta,
        second_abs_delta=second_abs_delta,
        pairing_confirmed=confirmed,
    )


def propose_encoder_mapping(
    observations: Iterable[PairingObservation],
    vehicle_config: Mapping[str, Any],
) -> list[dict[str, Any]] | None:
    positive = {item.commanded_logical: item for item in observations if item.direction == "forward"}
    if set(positive) != {0, 1, 2, 3} or not all(item.pairing_confirmed for item in positive.values()):
        return None
    dominant_logicals = [int(positive[index].dominant_encoder_logical) for index in range(4)]
    if len(set(dominant_logicals)) != 4:
        return None

    current = list(vehicle_config.get("encoders") or [])
    proposal: list[dict[str, Any]] = []
    for commanded in range(4):
        observed = positive[commanded]
        source_logical = int(observed.dominant_encoder_logical)
        source = current[source_logical]
        source_inverted = bool(source.get("inverted", False))
        proposal.append(
            {
                "logical": commanded,
                "name": WHEEL_NAMES[commanded],
                "physical": int(source["physical"]),
                "inverted": source_inverted ^ (observed.dominant_delta < 0),
            }
        )
    return proposal


class PairingSession:
    def __init__(self, port: str, vehicle_config: Mapping[str, Any], *, log_path: Path) -> None:
        self.port = port
        self.vehicle_config = dict(vehicle_config)
        self.log_path = log_path
        self.link: SerialLink | None = None
        self.latest_telemetry: dict[str, Any] | None = None
        self.arm_mode: str | None = None
        self.drive_seq = 0
        self.last_steer = [0.0, 0.0, 0.0, 0.0]
        self._log_file = None

    def __enter__(self) -> "PairingSession":
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_path.open("w", encoding="utf-8")
        self.link = SerialLink(self.port, timeout=0.02, open_settle_seconds=1.5, trace=False)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.force_safe()
        finally:
            if self.link is not None:
                self.link.close()
            if self._log_file is not None:
                self._log_file.close()

    def _record(self, direction: str, message: Mapping[str, Any]) -> None:
        payload = {"timestamp": datetime.now().isoformat(timespec="milliseconds"), "dir": direction, "message": dict(message)}
        assert self._log_file is not None
        self._log_file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._log_file.flush()

    def send(self, message: Mapping[str, Any]) -> None:
        assert self.link is not None
        self._record("tx", message)
        self.link.write(encode_message(message))

    def poll(self) -> list[dict[str, Any]]:
        assert self.link is not None
        messages: list[dict[str, Any]] = []
        for raw in self.link.read_lines():
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            self._record("rx", message)
            messages.append(message)
            if message.get("type") == "telemetry":
                self.latest_telemetry = message
                if _fault_seen(message):
                    raise RuntimeError(f"telemetry fault_flags={message.get('fault_flags')}")
            elif message.get("type") == "fault":
                raise RuntimeError(f"ESP32 fault: {message.get('reason', 'unknown')}")
        return messages

    def wait_for(self, message_type: str, *, timeout_s: float = 1.5, predicate: Any = None) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for message in self.poll():
                if message.get("type") == message_type and (predicate is None or predicate(message)):
                    return message
            time.sleep(0.02)
        raise RuntimeError(f"timeout waiting for {message_type}")

    def wait_for_telemetry(self, *, timeout_s: float = 1.0) -> dict[str, Any]:
        previous_seq = None if self.latest_telemetry is None else self.latest_telemetry.get("seq")
        return self.wait_for(
            "telemetry",
            timeout_s=timeout_s,
            predicate=lambda message: message.get("seq") != previous_seq,
        )

    def handshake(self, config_message: Mapping[str, Any], *, arm_mode: str = "debug") -> dict[str, Any]:
        normalized_mode = str(arm_mode).strip().lower()
        if normalized_mode not in {"debug", "normal"}:
            raise ValueError("arm_mode must be debug or normal")
        self.send(disarm_message())
        self.wait_for("arm_ack", predicate=lambda message: message.get("armed") is False)
        self.send(hello_message())
        hello = self.wait_for("hello_ack")
        if hello.get("firmware") != "mcb44_4wis":
            raise RuntimeError(f"unexpected firmware identity: {hello}")
        if hello.get("pca9685_ok") is False:
            raise RuntimeError("ESP32 reports PCA9685 not ready")
        self.send(config_message)
        ack = self.wait_for("config_ack")
        if ack.get("ok") is not True:
            raise RuntimeError(f"config rejected: {ack.get('reason', 'unknown')}")
        expected_state = normalized_mode.upper()
        self.send(arm_message(normalized_mode))
        arm_ack = self.wait_for("arm_ack", predicate=lambda message: message.get("state") == expected_state)
        if arm_ack.get("ok") is not True or arm_ack.get("armed") is not True:
            raise RuntimeError(f"{expected_state} arm rejected: {arm_ack.get('reason', 'unknown')}")
        self.arm_mode = normalized_mode
        return hello

    def sample_counts(self) -> list[int]:
        telemetry = self.wait_for_telemetry()
        values = telemetry.get("encoder_count")
        if not isinstance(values, list) or len(values) != 4:
            raise RuntimeError("telemetry encoder_count is missing")
        return [int(value) for value in values]

    def drive_one(self, wheel: int, pwm: int, *, forward: bool, duration_s: float) -> tuple[list[int], list[int]]:
        if self.arm_mode != "debug":
            raise RuntimeError("individual wheel drive requires DEBUG arm")
        before = self.sample_counts()
        deadline = time.monotonic() + duration_s
        command = debug_message("motor_test", wheel=wheel, pwm=abs(int(pwm)), direction=forward)
        while time.monotonic() < deadline:
            self.send(command)
            keepalive_deadline = min(deadline, time.monotonic() + KEEPALIVE_INTERVAL_S)
            while time.monotonic() < keepalive_deadline:
                self.poll()
                time.sleep(0.02)
        self.send(debug_message("motor_stop", wheel=wheel))
        self.wait_for_telemetry(timeout_s=1.0)
        after = self.sample_counts()
        return before, after

    def drive_profile(
        self,
        steer_deg: Iterable[float],
        drive_target: Iterable[int],
        *,
        duration_s: float,
    ) -> tuple[list[int], list[int]]:
        if self.arm_mode != "normal":
            raise RuntimeError("motion profile requires NORMAL arm")
        steer = [float(value) for value in steer_deg]
        target = [int(value) for value in drive_target]
        if len(steer) != 4 or len(target) != 4:
            raise ValueError("motion profile requires 4 steering angles and 4 drive targets")
        self.last_steer = steer
        before = self.sample_counts()
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            self.drive_seq += 1
            self.send(drive_message(self.drive_seq, "pwm", steer, target, True))
            keepalive_deadline = min(deadline, time.monotonic() + 0.05)
            while time.monotonic() < keepalive_deadline:
                self.poll()
                time.sleep(0.01)
        self.drive_seq += 1
        self.send(drive_message(self.drive_seq, "pwm", steer, [0, 0, 0, 0], True))
        self.wait_for_telemetry(timeout_s=1.0)
        time.sleep(0.15)
        self.poll()
        after = self.sample_counts()
        return before, after

    def force_safe(self) -> dict[str, Any] | None:
        if self.link is None:
            return None
        try:
            if self.arm_mode == "debug":
                self.send(debug_message("motor_stop", wheel=0))
                time.sleep(0.08)
                self.poll()
            elif self.arm_mode == "normal":
                self.drive_seq += 1
                self.send(drive_message(self.drive_seq, "pwm", self.last_steer, [0, 0, 0, 0], True))
                time.sleep(0.08)
                self.poll()
        finally:
            self.send(disarm_message())
        ack = self.wait_for("arm_ack", timeout_s=1.0, predicate=lambda message: message.get("armed") is False)
        self.arm_mode = None
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                telemetry = self.wait_for_telemetry(timeout_s=0.25)
            except RuntimeError:
                continue
            pwm = telemetry.get("motor_pwm")
            if telemetry.get("state") == "SAFE" and telemetry.get("armed") is False and pwm == [0, 0, 0, 0]:
                return telemetry
        raise RuntimeError(f"final SAFE/PWM-zero telemetry not confirmed after {ack}")


def _fault_seen(message: Mapping[str, Any]) -> bool:
    value = message.get("fault_flags", 0)
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def _load_vehicle_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("vehicle config must be a JSON object")
    return value


def _firmware_config_message(vehicle_config: Mapping[str, Any]) -> dict[str, Any]:
    motion_keys = (
        "wheelbase_m",
        "track_width_m",
        "wheel_diameter_m",
        "max_wheel_rpm",
        "max_linear_speed_mps",
        "max_angular_speed_radps",
        "translation_deadzone",
        "candidate_switch_hysteresis_deg",
        "servo_end_margin_deg",
        "realign_threshold_deg",
        "alignment_servo_rate_deg_per_sec",
        "alignment_tolerance_deg",
        "alignment_settle_time_ms",
        "alignment_timeout_ms",
        "decel_time_ms",
        "accel_time_ms",
    )
    motor_keys = ("physical", "inverted", "pid_enabled", "counts_per_wheel_rev")
    encoder_keys = ("physical", "inverted", "counts_per_wheel_rev")
    servo_keys = (
        "channel",
        "center_us",
        "min_us",
        "max_us",
        "min_angle_deg",
        "max_angle_deg",
        "trim_deg",
        "direction_inverted",
        "calibrated",
        "max_rate_deg_per_sec",
    )

    def items(name: str, keys: Iterable[str]) -> list[dict[str, Any]]:
        return [
            {key: item[key] for key in keys if key in item}
            for item in vehicle_config.get(name, [])
            if isinstance(item, Mapping)
        ]

    motion = vehicle_config.get("motion", {})
    message: dict[str, Any] = {
        "v": 1,
        "type": "config",
        "schema_version": int(vehicle_config.get("schema_version", 1)),
        "config_revision": int(vehicle_config.get("config_revision", 1)),
        "pid_enabled": bool(vehicle_config.get("pid_enabled", False)),
        "pca9685_address": int(vehicle_config.get("pca9685_address", 64)),
        "motion": {key: motion[key] for key in motion_keys if isinstance(motion, Mapping) and key in motion},
        "motors": items("motors", motor_keys),
        "encoders": items("encoders", encoder_keys),
        "servos": items("servos", servo_keys),
    }
    return message


def run_pairing_check(
    *,
    port: str,
    pwm: int,
    duration_s: float,
    vehicle_config: Mapping[str, Any],
    log_path: Path,
    wheels: Iterable[int] = range(4),
) -> dict[str, Any]:
    if pwm < 20 or pwm > 60:
        raise ValueError("bounded pairing check requires PWM 20..60")
    if duration_s < 0.2 or duration_s > 0.9:
        raise ValueError("bounded pairing check requires duration 0.2..0.9 s")

    selected_wheels = [int(wheel) for wheel in wheels]
    if not selected_wheels or any(wheel < 0 or wheel >= 4 for wheel in selected_wheels):
        raise ValueError("wheels must contain one or more logical indexes in 0..3")
    if len(set(selected_wheels)) != len(selected_wheels):
        raise ValueError("wheels must not contain duplicates")

    observations: list[PairingObservation] = []
    final_telemetry: dict[str, Any] | None = None
    with PairingSession(port, vehicle_config, log_path=log_path) as session:
        hello = session.handshake(_firmware_config_message(vehicle_config), arm_mode="debug")
        print(f"identity: firmware={hello.get('firmware')} board={hello.get('board')} pca9685_ok={hello.get('pca9685_ok')}", flush=True)
        for wheel in selected_wheels:
            for forward, label in ((True, "forward"), (False, "reverse")):
                before, after = session.drive_one(wheel, pwm, forward=forward, duration_s=duration_s)
                observation = analyze_pairing_observation(
                    commanded_logical=wheel,
                    direction=label,
                    count_before=before,
                    count_after=after,
                    vehicle_config=vehicle_config,
                )
                observations.append(observation)
                print(
                    f"{WHEEL_NAMES[wheel]} motor_p={observation.commanded_motor_physical} {label}: "
                    f"delta={observation.count_delta} dominant={observation.dominant_encoder_name}/p{observation.dominant_encoder_physical} "
                    f"confirmed={observation.pairing_confirmed}",
                    flush=True,
                )
        final_telemetry = session.force_safe()

    proposal = propose_encoder_mapping(observations, vehicle_config)
    return {
        "port": port,
        "pwm": pwm,
        "duration_s": duration_s,
        "wheels": selected_wheels,
        "observations": [asdict(item) for item in observations],
        "proposed_encoders": proposal,
        "final_telemetry": final_telemetry,
        "log_path": str(log_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely identify motor/encoder pairings one wheel at a time")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--pwm", type=int, default=DEFAULT_PWM)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--wheels-lifted", action="store_true", help="required physical safety confirmation")
    parser.add_argument("--wheel", choices=WHEEL_NAMES, default=None, help="limit the check to one logical wheel")
    parser.add_argument("--config", type=Path, default=Path("config/vehicle_config.json"))
    parser.add_argument("--log", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.wheels_lifted:
        raise SystemExit("refusing to move: pass --wheels-lifted after lifting all four wheels")
    config = _load_vehicle_config(args.config)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = args.log or Path("logs") / f"wheel-pairing-{stamp}.jsonl"
    result = run_pairing_check(
        port=args.port,
        pwm=args.pwm,
        duration_s=args.duration,
        vehicle_config=config,
        log_path=log_path,
        wheels=range(4) if args.wheel is None else [WHEEL_NAMES.index(args.wheel)],
    )
    result_path = log_path.with_suffix(".summary.json")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {result_path}", flush=True)
    print(f"final: {result['final_telemetry']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
