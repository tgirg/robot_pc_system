from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


WHEEL_NAMES = ("FL", "FR", "RL", "RR")
SERVO_SWEEP_DEG = (-135, -90, -45, 0, 45, 90, 135, 90, 45, 0, -45, -90, -135, -90, -45, 0)
RAMP_PWM = (60, 80, 100, 120)
DEFAULT_BAUDRATE = 115200


def _project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "vehicle_config.json").exists() and (parent / "pc_controller").exists():
            return parent
    return here.parents[3] if len(here.parents) > 3 else here.parents[-1]


PROJECT_ROOT = _project_root_from_here()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc_controller.protocol import arm_message, debug_message, disarm_message, encode_message, hello_message  # noqa: E402


class NoiseTransport(Protocol):
    def write_line(self, line: str) -> None: ...

    def read_lines(self, max_lines: int = 80) -> list[str]: ...

    def close(self) -> None: ...


ProgressCallback = Callable[[str], None]
SleepFunc = Callable[[float], None]
TransportFactory = Callable[[str, int], NoiseTransport]
StopCallback = Callable[[], bool]


class SerialNoiseTransport:
    """Small pyserial wrapper used by the dashboard noise-measurement worker."""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout_s: float = 0.04) -> None:
        import serial

        self._serial = serial.Serial(port, baudrate=baudrate, timeout=timeout_s)
        time.sleep(1.1)
        try:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except Exception:
            pass

    def write_line(self, line: str) -> None:
        text = line if line.endswith("\n") else line + "\n"
        self._serial.write(text.encode("utf-8"))
        self._serial.flush()

    def read_lines(self, max_lines: int = 80) -> list[str]:
        lines: list[str] = []
        while len(lines) < max_lines:
            if lines and getattr(self._serial, "in_waiting", 0) <= 0:
                break
            raw = self._serial.readline()
            if not raw:
                break
            lines.append(raw.decode("utf-8", errors="replace").strip())
        return lines

    def close(self) -> None:
        self._serial.close()


class JsonlRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, payload: Mapping[str, Any]) -> None:
        self._fh.write(json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def parse_wheel(value: str | int) -> int:
    if isinstance(value, int):
        index = value
    else:
        text = str(value).strip().upper()
        if text in WHEEL_NAMES:
            index = WHEEL_NAMES.index(text)
        else:
            index = int(text)
    if index < 0 or index >= len(WHEEL_NAMES):
        raise ValueError("wheel must be FL/FR/RL/RR or 0..3")
    return index


def encode_line(message: Mapping[str, Any]) -> str:
    return encode_message(message).decode("utf-8").strip()


def build_hello_line() -> str:
    return encode_line(hello_message())


def build_debug_arm_line() -> str:
    return encode_line(arm_message("debug"))


def build_disarm_line() -> str:
    return encode_line(disarm_message())


def build_motor_test_line(wheel: int, pwm: int, *, forward: bool = True) -> str:
    limited_pwm = max(0, min(120, abs(int(pwm))))
    return encode_line(debug_message("motor_test", wheel=parse_wheel(wheel), pwm=limited_pwm, direction=bool(forward)))


def build_motor_stop_line() -> str:
    return encode_line(debug_message("motor_stop", wheel=0))


def build_servo_deg_line(wheel: int, angle_deg: float) -> str:
    angle = max(-135.0, min(135.0, float(angle_deg)))
    return encode_line(debug_message("servo_deg", wheel=parse_wheel(wheel), value=angle))


def default_log_dir() -> Path:
    return PROJECT_ROOT / "logs"


def make_log_path(mode: str, wheel: int, *, log_dir: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    name = f"noise-{mode.lower()}-{WHEEL_NAMES[wheel].lower()}-{stamp}.jsonl"
    return (log_dir or default_log_dir()) / name


def _json_message(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _message_label(message: Mapping[str, Any]) -> str:
    msg_type = str(message.get("type", "-"))
    if msg_type == "debug":
        action = str(message.get("action", "-"))
        wheel = int(message.get("wheel", 0))
        wheel_name = WHEEL_NAMES[wheel] if 0 <= wheel < 4 else str(wheel)
        if action == "motor_test":
            return f"debug motor_test {wheel_name} pwm={message.get('pwm')}"
        if action == "servo_deg":
            return f"debug servo_deg {wheel_name} value={float(message.get('value', 0.0)):+.1f}"
        return f"debug {action}"
    if msg_type == "arm":
        return f"arm mode={message.get('mode')}"
    return msg_type


def _record(
    recorder: JsonlRecorder | None,
    records: list[dict[str, Any]],
    *,
    start_mono: float,
    phase: str,
    direction: str,
    raw_line: str,
    message: Mapping[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "t_s": round(time.monotonic() - start_mono, 3),
        "phase": phase,
        "dir": direction,
        "line": raw_line.strip(),
    }
    if message is not None:
        payload["message"] = dict(message)
    records.append(payload)
    if recorder is not None:
        recorder.write(payload)


def _poll_rx(
    transport: NoiseTransport,
    recorder: JsonlRecorder | None,
    records: list[dict[str, Any]],
    *,
    start_mono: float,
    phase: str,
    progress: ProgressCallback | None,
) -> None:
    for raw in transport.read_lines(max_lines=120):
        if not raw:
            continue
        message = _json_message(raw)
        _record(recorder, records, start_mono=start_mono, phase=phase, direction="rx", raw_line=raw, message=message)
        if progress is not None and message is not None and message.get("type") in {"arm_ack", "config_ack", "fault"}:
            progress(f"RX {phase}: {message.get('type')} {message.get('reason', '')}".rstrip())


def _send_and_wait(
    transport: NoiseTransport,
    recorder: JsonlRecorder | None,
    records: list[dict[str, Any]],
    *,
    start_mono: float,
    phase: str,
    line: str,
    wait_s: float,
    progress: ProgressCallback | None,
    sleep_func: SleepFunc,
    should_stop: StopCallback | None = None,
) -> None:
    message = _json_message(line)
    _record(recorder, records, start_mono=start_mono, phase=phase, direction="tx", raw_line=line, message=message)
    if progress is not None and message is not None:
        progress(f"TX {phase}: {_message_label(message)}")
    transport.write_line(line)
    deadline = time.monotonic() + max(0.0, float(wait_s))
    while time.monotonic() < deadline and not (should_stop and should_stop()):
        _poll_rx(transport, recorder, records, start_mono=start_mono, phase=phase, progress=progress)
        sleep_func(0.03)
    _poll_rx(transport, recorder, records, start_mono=start_mono, phase=phase, progress=progress)


def _number_list(message: Mapping[str, Any], key: str, length: int = 4) -> list[float] | None:
    values = message.get(key)
    if not isinstance(values, list) or len(values) < length:
        return None
    parsed: list[float] = []
    for value in values[:length]:
        try:
            parsed.append(float(value))
        except (TypeError, ValueError):
            return None
    return parsed


def _fault_value_seen(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "none", "ok", "false"}
    if isinstance(value, (int, float)):
        return int(value) != 0
    if isinstance(value, list):
        return any(_fault_value_seen(item) for item in value)
    return bool(value)


def summarize_records(records: Iterable[Mapping[str, Any]], *, phase: str | None = None) -> dict[str, Any]:
    selected = [record for record in records if phase is None or str(record.get("phase", "")) == phase]
    messages = [record.get("message") for record in selected if isinstance(record.get("message"), dict)]
    telemetry = [message for message in messages if message.get("type") == "telemetry"]

    first_counts: list[float] | None = None
    last_counts: list[float] | None = None
    max_abs_rpm = [0.0, 0.0, 0.0, 0.0]
    max_abs_pwm = [0.0, 0.0, 0.0, 0.0]
    servo_min = [None, None, None, None]
    servo_max = [None, None, None, None]
    fault_reasons: list[str] = []

    for message in telemetry:
        counts = _number_list(message, "encoder_count")
        if counts is not None:
            if first_counts is None:
                first_counts = counts
            last_counts = counts
        rpm = _number_list(message, "wheel_rpm")
        if rpm is not None:
            max_abs_rpm = [max(current, abs(value)) for current, value in zip(max_abs_rpm, rpm, strict=True)]
        pwm = _number_list(message, "motor_pwm")
        if pwm is not None:
            max_abs_pwm = [max(current, abs(value)) for current, value in zip(max_abs_pwm, pwm, strict=True)]
        servo = _number_list(message, "servo_deg")
        if servo is not None:
            for index, value in enumerate(servo):
                servo_min[index] = value if servo_min[index] is None else min(float(servo_min[index]), value)
                servo_max[index] = value if servo_max[index] is None else max(float(servo_max[index]), value)
        if _fault_value_seen(message.get("fault_flags")):
            fault_reasons.append(f"fault_flags={message.get('fault_flags')}")

    for message in messages:
        if message.get("type") == "fault":
            fault_reasons.append(str(message.get("reason", "fault")))

    count_delta = None
    if first_counts is not None and last_counts is not None:
        count_delta = [int(round(last - first)) for first, last in zip(first_counts, last_counts, strict=True)]

    return {
        "phase": phase or "all",
        "rx_count": len(selected),
        "telemetry_count": len(telemetry),
        "count_delta": count_delta,
        "max_abs_rpm": max_abs_rpm,
        "max_abs_pwm": max_abs_pwm,
        "servo_min": servo_min,
        "servo_max": servo_max,
        "fault_seen": bool(fault_reasons),
        "fault_reasons": fault_reasons,
    }


def classify_motor_noise(
    summary: Mapping[str, Any],
    active_wheel: int,
    requested_pwm: int,
    *,
    min_active_count_delta: int = 20,
    min_active_rpm: float = 2.0,
    min_noise_count_delta: int = 1,
    min_noise_rpm: float = 0.5,
) -> dict[str, Any]:
    wheel = parse_wheel(active_wheel)
    count_delta = summary.get("count_delta")
    max_abs_rpm = list(summary.get("max_abs_rpm") or [0.0, 0.0, 0.0, 0.0])
    max_abs_pwm = list(summary.get("max_abs_pwm") or [0.0, 0.0, 0.0, 0.0])

    active_delta = 0
    if isinstance(count_delta, list) and len(count_delta) > wheel:
        active_delta = int(count_delta[wheel])
    active_rpm = float(max_abs_rpm[wheel]) if len(max_abs_rpm) > wheel else 0.0
    active_pwm = float(max_abs_pwm[wheel]) if len(max_abs_pwm) > wheel else 0.0
    pwm_reported = active_pwm >= max(1.0, abs(float(requested_pwm)) * 0.5)
    rotation_confirmed = abs(active_delta) >= min_active_count_delta or active_rpm >= min_active_rpm

    other_count_noise = 0
    if isinstance(count_delta, list):
        other_count_noise = max((abs(int(value)) for index, value in enumerate(count_delta) if index != wheel), default=0)
    other_rpm_noise = max((float(value) for index, value in enumerate(max_abs_rpm) if index != wheel), default=0.0)
    noise_observed = other_count_noise >= min_noise_count_delta or other_rpm_noise >= min_noise_rpm

    if summary.get("fault_seen"):
        status = "fault"
        reason = "fault/fault_flags が出ています"
    elif not rotation_confirmed:
        status = "rotation_unconfirmed" if pwm_reported or requested_pwm else "no_drive"
        reason = "PWMは出ていますが、対象ホイールの回転またはエンコーダ変化を確認できません"
    elif noise_observed:
        status = "noise_observed"
        reason = "対象外ホイールのカウントまたはRPMが動いています"
    else:
        status = "pass"
        reason = "対象ホイールだけが動き、対象外ホイールのノイズは見えていません"

    return {
        "status": status,
        "reason": reason,
        "active_wheel": wheel,
        "active_delta": active_delta,
        "active_max_rpm": active_rpm,
        "active_max_pwm": active_pwm,
        "pwm_reported": pwm_reported,
        "rotation_confirmed": rotation_confirmed,
        "stationary_count_noise": other_count_noise,
        "stationary_max_rpm": other_rpm_noise,
    }


def classify_servo_noise(
    summary: Mapping[str, Any],
    *,
    min_noise_count_delta: int = 1,
    min_noise_rpm: float = 0.5,
) -> dict[str, Any]:
    count_delta = summary.get("count_delta")
    max_abs_rpm = list(summary.get("max_abs_rpm") or [0.0, 0.0, 0.0, 0.0])
    count_noise = 0
    if isinstance(count_delta, list):
        count_noise = max((abs(int(value)) for value in count_delta), default=0)
    rpm_noise = max((float(value) for value in max_abs_rpm), default=0.0)

    if summary.get("fault_seen"):
        status = "fault"
        reason = "fault/fault_flags が出ています"
    elif count_noise >= min_noise_count_delta or rpm_noise >= min_noise_rpm:
        status = "noise_observed"
        reason = "サーボ動作だけでエンコーダ/RPMが動いています"
    else:
        status = "pass"
        reason = "サーボ動作中のエンコーダ/RPMノイズは見えていません"

    return {
        "status": status,
        "reason": reason,
        "max_count_noise": count_noise,
        "max_rpm_noise": rpm_noise,
    }


def _status_label(status: str) -> str:
    return {
        "pass": "OK",
        "noise_observed": "ノイズ検出",
        "rotation_unconfirmed": "回転未確認",
        "no_drive": "駆動なし",
        "fault": "FAULT",
    }.get(status, status)


def _format_vector(values: Any, precision: int = 1) -> str:
    if not isinstance(values, list):
        return "-"
    formatted = []
    for value in values:
        try:
            formatted.append(f"{float(value):+.{precision}f}")
        except (TypeError, ValueError):
            formatted.append(str(value))
    return "[" + ", ".join(formatted) + "]"


def format_result_text(result: Mapping[str, Any]) -> str:
    mode = str(result.get("mode", "-"))
    wheel = int(result.get("wheel", 0))
    wheel_name = WHEEL_NAMES[wheel] if 0 <= wheel < 4 else str(wheel)
    classification = result.get("classification", {})
    status = str(classification.get("status", "-")) if isinstance(classification, dict) else "-"

    lines = [
        f"測定: {mode} / {wheel_name} / COM={result.get('port', '-')}",
        f"判定: {_status_label(status)} - {classification.get('reason', '-') if isinstance(classification, dict) else '-'}",
        f"ログ: {result.get('log_path', '-')}",
    ]

    summary = result.get("summary")
    if isinstance(summary, dict):
        lines.append(f"count_delta: {_format_vector(summary.get('count_delta'), precision=0)}")
        lines.append(f"max_abs_rpm: {_format_vector(summary.get('max_abs_rpm'), precision=2)}")
        lines.append(f"max_abs_pwm: {_format_vector(summary.get('max_abs_pwm'), precision=0)}")

    if isinstance(classification, dict) and mode in {"combined", "ramp"}:
        lines.append(
            "active: "
            f"delta={classification.get('active_delta', '-')} "
            f"rpm={float(classification.get('active_max_rpm', 0.0)):.2f} "
            f"pwm={float(classification.get('active_max_pwm', 0.0)):.0f} "
            f"rotation_confirmed={classification.get('rotation_confirmed', '-')}"
        )
        lines.append(
            "stationary_noise: "
            f"count={classification.get('stationary_count_noise', '-')} "
            f"rpm={float(classification.get('stationary_max_rpm', 0.0)):.2f}"
        )

    steps = result.get("steps")
    if isinstance(steps, list):
        lines.append("PWMランプ:")
        for step in steps:
            step_class = step.get("classification", {}) if isinstance(step, dict) else {}
            lines.append(
                f"  PWM {step.get('pwm', '-')}: "
                f"{_status_label(str(step_class.get('status', '-')))} / "
                f"delta={step_class.get('active_delta', '-')} "
                f"rpm={float(step_class.get('active_max_rpm', 0.0)):.2f}"
            )

    return "\n".join(lines)


def _run_session(
    *,
    mode: str,
    port: str,
    wheel: int,
    pwm: int,
    baudrate: int,
    transport_factory: TransportFactory,
    log_dir: Path | None,
    progress: ProgressCallback | None,
    sleep_func: SleepFunc,
    should_stop: StopCallback | None = None,
    servo_sweep: Iterable[float] = SERVO_SWEEP_DEG,
    servo_step_s: float = 0.45,
) -> dict[str, Any]:
    wheel = parse_wheel(wheel)
    log_path = make_log_path(mode, wheel, log_dir=log_dir)
    records: list[dict[str, Any]] = []
    start_mono = time.monotonic()
    recorder = JsonlRecorder(log_path)
    transport: NoiseTransport | None = None
    steps: list[dict[str, Any]] = []

    def send(phase: str, line: str, wait_s: float) -> None:
        _send_and_wait(
            transport,  # type: ignore[arg-type]
            recorder,
            records,
            start_mono=start_mono,
            phase=phase,
            line=line,
            wait_s=wait_s,
            progress=progress,
            sleep_func=sleep_func,
            should_stop=should_stop,
        )

    try:
        recorder.write(
            {
                "t_s": 0.0,
                "phase": "session",
                "dir": "meta",
                "mode": mode,
                "port": port,
                "baudrate": baudrate,
                "wheel": WHEEL_NAMES[wheel],
                "pwm": int(pwm),
            }
        )
        transport = transport_factory(port, baudrate)
        send("hello", build_hello_line(), 0.35)
        send("debug_arm", build_debug_arm_line(), 0.8)

        if mode == "servo":
            for angle in servo_sweep:
                if should_stop and should_stop():
                    break
                send("servo_sweep", build_servo_deg_line(wheel, angle), servo_step_s)
            send("servo_center", build_servo_deg_line(wheel, 0.0), 0.35)
        elif mode == "combined":
            send("motor_start", build_motor_test_line(wheel, pwm), 0.35)
            for angle in servo_sweep:
                if should_stop and should_stop():
                    break
                send("combined", build_servo_deg_line(wheel, angle), servo_step_s)
            send("motor_stop", build_motor_stop_line(), 0.45)
            send("servo_center", build_servo_deg_line(wheel, 0.0), 0.35)
        elif mode == "ramp":
            for level in RAMP_PWM:
                if should_stop and should_stop():
                    break
                phase = f"pwm_{level}"
                start_index = len(records)
                send(phase, build_motor_test_line(wheel, level), 0.95)
                send(phase, build_motor_stop_line(), 0.45)
                phase_records = records[start_index:]
                summary = summarize_records(phase_records)
                classification = classify_motor_noise(summary, wheel, level)
                steps.append({"pwm": level, "summary": summary, "classification": classification})
        else:
            raise ValueError(f"unknown noise test mode: {mode}")
    finally:
        if transport is not None:
            try:
                send("safe_stop", build_motor_stop_line(), 0.25)
                send("safe_center", build_servo_deg_line(wheel, 0.0), 0.2)
                send("safe_disarm", build_disarm_line(), 0.35)
            finally:
                transport.close()
        recorder.close()

    summary = summarize_records(records)
    if mode == "servo":
        classification = classify_servo_noise(summary)
    elif mode == "ramp":
        if steps:
            first_ok = next(
                (
                    step["classification"]
                    for step in steps
                    if step["classification"]["status"] in {"pass", "noise_observed"}
                    and step["classification"]["rotation_confirmed"]
                ),
                None,
            )
            classification = first_ok or steps[-1]["classification"]
        else:
            classification = classify_motor_noise(summary, wheel, pwm)
    else:
        classification = classify_motor_noise(summary, wheel, pwm)

    result: dict[str, Any] = {
        "mode": mode,
        "port": port,
        "baudrate": baudrate,
        "wheel": wheel,
        "pwm": int(pwm),
        "log_path": str(log_path),
        "summary": summary,
        "classification": classification,
    }
    if steps:
        result["steps"] = steps
    return result


def run_combined_noise_test(
    port: str,
    wheel: int,
    pwm: int = 40,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    transport_factory: TransportFactory = SerialNoiseTransport,
    log_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    sleep_func: SleepFunc = time.sleep,
    should_stop: StopCallback | None = None,
) -> dict[str, Any]:
    return _run_session(
        mode="combined",
        port=port,
        wheel=wheel,
        pwm=pwm,
        baudrate=baudrate,
        transport_factory=transport_factory,
        log_dir=log_dir,
        progress=progress,
        sleep_func=sleep_func,
        should_stop=should_stop,
    )


def run_servo_sweep_test(
    port: str,
    wheel: int,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    transport_factory: TransportFactory = SerialNoiseTransport,
    log_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    sleep_func: SleepFunc = time.sleep,
    should_stop: StopCallback | None = None,
) -> dict[str, Any]:
    return _run_session(
        mode="servo",
        port=port,
        wheel=wheel,
        pwm=0,
        baudrate=baudrate,
        transport_factory=transport_factory,
        log_dir=log_dir,
        progress=progress,
        sleep_func=sleep_func,
        should_stop=should_stop,
    )


def run_motor_ramp_test(
    port: str,
    wheel: int,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    transport_factory: TransportFactory = SerialNoiseTransport,
    log_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    sleep_func: SleepFunc = time.sleep,
    should_stop: StopCallback | None = None,
) -> dict[str, Any]:
    return _run_session(
        mode="ramp",
        port=port,
        wheel=wheel,
        pwm=max(RAMP_PWM),
        baudrate=baudrate,
        transport_factory=transport_factory,
        log_dir=log_dir,
        progress=progress,
        sleep_func=sleep_func,
        should_stop=should_stop,
    )


def send_stop_disarm(
    port: str,
    wheel: int = 0,
    *,
    baudrate: int = DEFAULT_BAUDRATE,
    transport_factory: TransportFactory = SerialNoiseTransport,
    log_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    sleep_func: SleepFunc = time.sleep,
) -> dict[str, Any]:
    wheel = parse_wheel(wheel)
    log_path = make_log_path("stop-disarm", wheel, log_dir=log_dir)
    records: list[dict[str, Any]] = []
    start_mono = time.monotonic()
    recorder = JsonlRecorder(log_path)
    transport = transport_factory(port, baudrate)
    try:
        _send_and_wait(
            transport,
            recorder,
            records,
            start_mono=start_mono,
            phase="safe_stop",
            line=build_motor_stop_line(),
            wait_s=0.25,
            progress=progress,
            sleep_func=sleep_func,
            should_stop=None,
        )
        _send_and_wait(
            transport,
            recorder,
            records,
            start_mono=start_mono,
            phase="safe_center",
            line=build_servo_deg_line(wheel, 0.0),
            wait_s=0.2,
            progress=progress,
            sleep_func=sleep_func,
            should_stop=None,
        )
        _send_and_wait(
            transport,
            recorder,
            records,
            start_mono=start_mono,
            phase="safe_disarm",
            line=build_disarm_line(),
            wait_s=0.35,
            progress=progress,
            sleep_func=sleep_func,
            should_stop=None,
        )
    finally:
        transport.close()
        recorder.close()

    summary = summarize_records(records)
    return {
        "mode": "stop-disarm",
        "port": port,
        "baudrate": baudrate,
        "wheel": wheel,
        "pwm": 0,
        "log_path": str(log_path),
        "summary": summary,
        "classification": classify_servo_noise(summary),
    }
