"""Read one encoder from ESP32 telemetry over serial."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Any

from .protocol import ProtocolError, decode_line, encode_message, hello_message
from .serial_discovery import open_discovered_serial_link
from .serial_link import SerialLink

WHEEL_NAMES = ("FL", "FR", "RL", "RR")


@dataclass
class EncoderSample:
    timestamp_s: float
    state: str
    armed: bool
    count: int
    delta_count: int | None
    rpm: float
    pwm: int
    servo_deg: float
    fault_flags: int


def parse_wheel(value: str) -> int:
    """Parse FL/FR/RL/RR or 0..3 into a logical wheel index."""
    text = value.strip().upper()
    if text in WHEEL_NAMES:
        return WHEEL_NAMES.index(text)
    try:
        index = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("wheel must be FL, FR, RL, RR, or 0..3") from exc
    if 0 <= index < len(WHEEL_NAMES):
        return index
    raise argparse.ArgumentTypeError("wheel must be FL, FR, RL, RR, or 0..3")


def extract_encoder_sample(
    message: dict[str, Any],
    wheel: int,
    timestamp_s: float,
    previous_count: int | None = None,
) -> EncoderSample | None:
    """Extract one wheel's encoder fields from a telemetry message."""
    if message.get("type") != "telemetry":
        return None
    encoder_count = message.get("encoder_count")
    wheel_rpm = message.get("wheel_rpm")
    motor_pwm = message.get("motor_pwm")
    servo_deg = message.get("servo_deg")
    if not (
        isinstance(encoder_count, list)
        and isinstance(wheel_rpm, list)
        and isinstance(motor_pwm, list)
        and isinstance(servo_deg, list)
        and len(encoder_count) > wheel
        and len(wheel_rpm) > wheel
        and len(motor_pwm) > wheel
        and len(servo_deg) > wheel
    ):
        return None

    count = int(encoder_count[wheel])
    return EncoderSample(
        timestamp_s=timestamp_s,
        state=str(message.get("state", "?")),
        armed=bool(message.get("armed", False)),
        count=count,
        delta_count=None if previous_count is None else count - previous_count,
        rpm=float(wheel_rpm[wheel]),
        pwm=int(float(motor_pwm[wheel])),
        servo_deg=float(servo_deg[wheel]),
        fault_flags=int(message.get("fault_flags", 0)),
    )


def format_sample(sample: EncoderSample, wheel_name: str) -> str:
    """Format one sample for console logging."""
    delta = "----" if sample.delta_count is None else f"{sample.delta_count:+d}"
    return (
        f"{sample.timestamp_s:8.3f}s {wheel_name} "
        f"count={sample.count:+11d} delta={delta:>7} "
        f"rpm={sample.rpm:+8.2f} pwm={sample.pwm:+5d} "
        f"servo={sample.servo_deg:+7.2f} "
        f"state={sample.state} armed={int(sample.armed)} fault={sample.fault_flags}"
    )


def monitor_encoder(
    port: str | None,
    wheel: int,
    duration_s: float,
    print_hz: float,
    trace_serial: bool = False,
    discovery_timeout: float = 1.2,
) -> None:
    """Open serial and print one encoder until duration expires."""
    wheel_name = WHEEL_NAMES[wheel]
    interval_s = 1.0 / max(0.1, print_hz)
    if port:
        serial = SerialLink(port, timeout=0.02, trace=trace_serial)
        node_text = ""
    else:
        probe = open_discovered_serial_link(role="drive", timeout=discovery_timeout, trace=trace_serial)
        serial = probe.link
        if serial is None:
            raise RuntimeError("serial discovery did not return an open link")
        node_text = (
            f" node_id={(probe.identity or {}).get('node_id', '?')}"
            f" role={(probe.identity or {}).get('role', '?')}"
        )
    start = time.monotonic()
    deadline = start + max(0.1, duration_s)
    next_print_s = start
    previous_count: int | None = None
    latest: EncoderSample | None = None

    print(f"encoder monitor started: port={serial.port}{node_text} wheel={wheel_name} duration={duration_s:g}s", flush=True)
    print("rotate the selected wheel by hand, or run a separate motor test. This command does not ARM motors.", flush=True)
    serial.write(encode_message(hello_message()))
    try:
        while time.monotonic() < deadline:
            for line in serial.read_lines():
                try:
                    message = decode_line(line)
                except ProtocolError:
                    continue
                sample = extract_encoder_sample(message, wheel, time.monotonic() - start, previous_count)
                if sample is None:
                    continue
                previous_count = sample.count
                latest = sample

            now = time.monotonic()
            if latest is not None and now >= next_print_s:
                print(format_sample(latest, wheel_name), flush=True)
                next_print_s = now + interval_s
            time.sleep(0.005)
    finally:
        serial.close()
    print("encoder monitor finished", flush=True)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the encoder monitor CLI parser."""
    parser = argparse.ArgumentParser(description="Read one ESP32 encoder from serial telemetry")
    parser.add_argument("--port", default=None, help="serial port, for example COM7")
    parser.add_argument("--wheel", required=True, type=parse_wheel, help="FL, FR, RL, RR, or 0..3")
    parser.add_argument("--duration", type=float, default=20.0, help="monitor duration in seconds")
    parser.add_argument("--hz", type=float, default=10.0, help="print rate in Hz")
    parser.add_argument("--trace-serial", action="store_true", help="also print raw serial TX/RX lines")
    parser.add_argument("--discovery-timeout", type=float, default=1.2, help="seconds to wait for each serial identity reply")
    return parser


def main() -> None:
    """Run the encoder monitor command."""
    args = build_arg_parser().parse_args()
    try:
        monitor_encoder(args.port, args.wheel, args.duration, args.hz, args.trace_serial, args.discovery_timeout)
    except KeyboardInterrupt:
        print("stopped by Ctrl+C", flush=True)


if __name__ == "__main__":
    main()
