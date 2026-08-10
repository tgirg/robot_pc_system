from __future__ import annotations

from .connection_result import ConnectionResult, ConnectionStatus
from .serial_connection import SerialConnection


class ConnectionManager:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.connections: dict[str, SerialConnection] = {}

    def get_connection(self, controller_name: str = "drive") -> SerialConnection:
        if controller_name not in self.connections:
            serial_cfg = self._controller_serial_config(controller_name)
            timeout = float(serial_cfg.get("timeout", 0.05))
            reconnect_ms = int(serial_cfg.get("reconnect_interval_ms", 2000))
            conn = SerialConnection(timeout=timeout, reconnect_interval_s=reconnect_ms / 1000.0)
            conn.port = str(serial_cfg.get("port", ""))
            conn.baudrate = int(serial_cfg.get("baudrate", 115200))
            self.connections[controller_name] = conn
        return self.connections[controller_name]

    def connect(self, controller_name: str, port: str, baudrate: int) -> ConnectionResult:
        return self.get_connection(controller_name).connect(port, baudrate)

    def connect_drive(self, port: str, baudrate: int) -> ConnectionResult:
        return self.connect("drive", port, baudrate)

    def disconnect(self, controller_name: str) -> ConnectionResult:
        return self.get_connection(controller_name).disconnect()

    def disconnect_drive(self) -> ConnectionResult:
        return self.disconnect("drive")

    def send_line(self, controller_name: str, text: str) -> ConnectionResult:
        return self.get_connection(controller_name).send_line(text)

    def send_drive_command(self, text: str) -> ConnectionResult:
        return self.send_line("drive", text)

    def read_lines(self, controller_name: str, max_lines: int = 50) -> list[str]:
        return self.get_connection(controller_name).read_lines(max_lines)

    def read_drive_lines(self, max_lines: int = 50) -> list[str]:
        return self.read_lines("drive", max_lines)

    def status(self, controller_name: str) -> ConnectionStatus:
        return self.get_connection(controller_name).get_status()

    def drive_status(self) -> ConnectionStatus:
        return self.status("drive")

    def reconnect_if_needed(self, controller_name: str) -> ConnectionResult:
        connection = self.get_connection(controller_name)
        if connection.is_connected():
            status = connection.get_status()
            return ConnectionResult(True, "接続中です", status.port, status.baudrate)
        return connection.reconnect()

    def _controller_serial_config(self, controller_name: str) -> dict:
        serial_cfg = dict((self.config.get("serial") or {}))
        controllers = self.config.get("controllers") or {}
        controller_cfg = controllers.get(controller_name) or {}
        communication = self.config.get("communication") or {}
        usb_cfg = communication.get("usb") or {}
        for key in ("port", "baudrate"):
            if key in usb_cfg and key not in serial_cfg:
                serial_cfg[key] = usb_cfg[key]
            if key in controller_cfg:
                serial_cfg[key] = controller_cfg[key]
        return serial_cfg
