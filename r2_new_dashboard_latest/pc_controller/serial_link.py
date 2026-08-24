"""Serial connection wrapper."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Iterable

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - depends on optional runtime package
    serial = None
    list_ports = None


class SerialLink:
    """Small pyserial NDJSON transport."""

    def __init__(
        self,
        port: str | None,
        baudrate: int = 115200,
        timeout: float = 0.01,
        open_settle_seconds: float = 1.5,
        trace: bool | None = None,
    ) -> None:
        if serial is None:
            raise RuntimeError("pyserial is required for real serial mode")
        self.port = port or self.auto_detect_port()
        self.trace = _env_flag("ROBOT_SERIAL_TRACE") if trace is None else trace
        self._rx_buffer = bytearray()
        try:
            self._serial = serial.Serial(self.port, baudrate=baudrate, timeout=timeout)
        except serial.SerialException as exc:
            ports = ", ".join(self.available_ports()) or "none"
            raise RuntimeError(
                f"could not open serial port {self.port}: {exc}. "
                "Close Arduino Serial Monitor, stop other pc_controller terminals with Ctrl+C, "
                f"then retry. Visible ports: {ports}"
            ) from exc
        time.sleep(max(0.0, open_settle_seconds))
        if self.trace:
            print(f"serial trace enabled: port={self.port} baudrate={baudrate}", flush=True)
        else:
            self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    @staticmethod
    def available_ports() -> list[str]:
        """Return visible serial port names."""
        if list_ports is None:
            return []
        return [port.device for port in list_ports.comports()]

    @classmethod
    def auto_detect_port(cls) -> str:
        """Pick the first USB-like serial port."""
        ports = cls.available_ports()
        for port in ports:
            upper = port.upper()
            if "COM" in upper:
                return port
        if ports:
            return ports[0]
        raise RuntimeError("no serial ports found")

    def write(self, payload: bytes) -> None:
        """Write bytes to the serial port."""
        self._trace("TX", payload)
        written = self._serial.write(payload)
        if written is not None and written != len(payload):
            raise RuntimeError(f"serial write incomplete: wrote {written} of {len(payload)} bytes")

    def read_lines(self) -> Iterable[bytes]:
        """Yield currently available complete lines."""
        waiting = int(getattr(self._serial, "in_waiting", 0))
        if waiting <= 0:
            return
        chunk = self._serial.read(waiting)
        if not chunk:
            return
        self._rx_buffer.extend(chunk)
        if len(self._rx_buffer) > 8192:
            self._rx_buffer.clear()
            raise RuntimeError("serial RX buffer overflow")
        while True:
            newline = self._rx_buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._rx_buffer[:newline]).rstrip(b"\r")
            del self._rx_buffer[: newline + 1]
            if line:
                self._trace("RX", line + b"\n")
                yield line

    def close(self) -> None:
        """Close the serial port."""
        time.sleep(0.02)
        self._serial.close()

    def _trace(self, direction: str, payload: bytes) -> None:
        if not self.trace:
            return
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        text = payload.decode("utf-8", errors="backslashreplace").rstrip("\r\n")
        text = _stdout_safe(text)
        print(f"serial {direction} {timestamp}: {text}", flush=True)


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _stdout_safe(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
