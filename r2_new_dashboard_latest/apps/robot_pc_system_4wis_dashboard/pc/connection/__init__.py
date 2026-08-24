from __future__ import annotations

from .connection_manager import ConnectionManager
from .connection_result import ConnectionResult, ConnectionStatus, PortInfo
from .port_detector import detect_ports
from .serial_connection import SerialConnection

__all__ = [
    "ConnectionManager",
    "ConnectionResult",
    "ConnectionStatus",
    "PortInfo",
    "SerialConnection",
    "detect_ports",
]
