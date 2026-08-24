from __future__ import annotations

import argparse
import time
from pathlib import Path

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32 raw serial monitor")
    parser.add_argument("port", help="COM port, for example COM10")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate")
    parser.add_argument("--duration", type=float, default=10.0, help="Read duration in seconds")
    parser.add_argument("--save", action="store_true", help="Save raw log under logs/serial_monitor")
    args = parser.parse_args()

    lines: list[str] = []
    started = time.time()
    try:
        with serial.Serial(args.port, args.baud, timeout=0.1) as conn:
            print(f"接続しました: {args.port} / {args.baud} bps")
            while time.time() - started < args.duration:
                raw = conn.readline()
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                print(text)
                lines.append(text)
    except serial.SerialException as exc:
        print(f"接続または受信に失敗しました: {exc}")
        return 1

    if args.save:
        root = Path(__file__).resolve().parents[1]
        log_dir = root / "logs" / "serial_monitor"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = log_dir / f"simple_serial_monitor_{timestamp}.txt"
        content = "\n".join(
            [
                f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"COM port: {args.port}",
                f"baudrate: {args.baud}",
                "",
                "--- raw received text ---",
                "\n".join(lines),
                "",
            ]
        )
        path.write_text(content, encoding="utf-8")
        print(f"ログ保存: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
