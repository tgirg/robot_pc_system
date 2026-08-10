from __future__ import annotations

from dataclasses import dataclass

try:
    from .connection import ConnectionManager
except ImportError:
    from connection import ConnectionManager


@dataclass
class SerialStatus:
    connected: bool
    mock: bool
    message: str


class ESP32Serial:
    def __init__(self, config: dict, connection_manager: ConnectionManager | None = None, controller_name: str = "drive") -> None:
        self.port = str(config.get("port", "COM3"))
        self.baudrate = int(config.get("baudrate", 115200))
        self.timeout = float(config.get("timeout", 0.05))
        self.mock = bool(config.get("mock", True))
        self.reconnect_interval = int(config.get("reconnect_interval_ms", 2000)) / 1000.0
        self.controller_name = controller_name
        self.manager = connection_manager or ConnectionManager({"serial": config})
        connection = self.manager.get_connection(self.controller_name)
        connection.port = self.port
        connection.baudrate = self.baudrate
        connection.timeout = self.timeout
        connection.reconnect_interval_s = self.reconnect_interval
        self.last_error = "未接続"

    def connect(self, force: bool = False) -> SerialStatus:
        connection = self.manager.get_connection(self.controller_name)
        if connection.is_connected():
            return SerialStatus(True, False, f"Connected: {self.port}")
        if self.mock and not force:
            return SerialStatus(True, True, "Mock ESP32")
        result = self.manager.connect(self.controller_name, self.port, self.baudrate)
        if result.success:
            self.last_error = ""
            return SerialStatus(True, False, f"Connected: {self.port}")
        self.last_error = result.message
        if self.mock:
            return SerialStatus(True, True, "Mock ESP32")
        return SerialStatus(False, False, result.message)

    def connect_port(self, port: str, baudrate: int | None = None, mock: bool = False) -> SerialStatus:
        self.port = str(port)
        if baudrate is not None:
            self.baudrate = int(baudrate)
        self.mock = bool(mock)
        result = self.manager.connect(self.controller_name, self.port, self.baudrate)
        if result.success:
            self.last_error = ""
            return SerialStatus(True, False, f"Connected: {self.port}")
        self.last_error = result.message
        return SerialStatus(False, False, result.message)

    def status(self) -> SerialStatus:
        status = self.manager.status(self.controller_name)
        if status.connected:
            return SerialStatus(True, False, f"Connected: {status.port}")
        if self.mock:
            return SerialStatus(True, True, "Mock ESP32")
        return SerialStatus(False, False, status.message or self.last_error)

    def send_command(self, command: str) -> tuple[bool, str]:
        clean_command = command.strip()
        status = self.status()
        if status.mock:
            return True, f"MOCK TX: {clean_command}"
        if not status.connected:
            return False, f"ESP32 NG: {status.message}"
        result = self.manager.send_line(self.controller_name, clean_command)
        if result.success:
            return True, f"TX: {clean_command}"
        self.last_error = result.message
        return False, result.message

    def read_lines(self, max_lines: int = 20) -> list[str]:
        return self.manager.read_lines(self.controller_name, max_lines=max_lines)

    def disconnect(self) -> None:
        self.manager.disconnect(self.controller_name)
        self.last_error = "ユーザー操作で切断しました"

    def close(self) -> None:
        self.disconnect()
