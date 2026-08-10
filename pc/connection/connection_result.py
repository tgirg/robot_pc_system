from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionResult:
    success: bool
    message: str
    port: str = ""
    baudrate: int = 0
    error: str = ""


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    message: str
    port: str = ""
    baudrate: int = 0
    last_received_line: str = ""
    last_received_time: float = 0.0
    received_line_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class PortInfo:
    port: str
    description: str = ""
    hwid: str = ""
    likely_device_type: str = ""

    @property
    def is_likely_esp32(self) -> bool:
        return self.likely_device_type == "ESP32候補"

    def display_name(self) -> str:
        label = f"{self.port} - {self.description}" if self.description else self.port
        if self.is_likely_esp32:
            label += "（ESP32候補）"
        return label
