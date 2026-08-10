from __future__ import annotations

from .connection_result import PortInfo


ESP32_KEYWORDS = (
    "silicon labs cp210x",
    "cp210x",
    "ch340",
    "usb serial",
    "usb to uart",
    "uart bridge",
)


def detect_ports() -> list[PortInfo]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    ports: list[PortInfo] = []
    for port in list_ports.comports():
        description = port.description or ""
        hwid = port.hwid or ""
        ports.append(
            PortInfo(
                port=port.device,
                description=description,
                hwid=hwid,
                likely_device_type=_likely_device_type(description, hwid),
            )
        )
    return ports


def _likely_device_type(description: str, hwid: str) -> str:
    text = f"{description} {hwid}".lower()
    if any(keyword in text for keyword in ESP32_KEYWORDS):
        return "ESP32候補"
    return ""
