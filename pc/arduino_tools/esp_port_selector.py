from __future__ import annotations

import re
from typing import Iterable, Protocol


class SerialPortLike(Protocol):
    device: str
    description: str
    hwid: str


ESP32_KEYWORDS = (
    "esp32",
    "cp210",
    "ch340",
    "ch910",
    "usb serial",
    "usb-serial",
    "usb to uart",
    "uart bridge",
    "silicon labs",
    "wch",
    "ftdi",
)

NON_ESP_KEYWORDS = (
    "bluetooth",
    "bthenum",
    "active management",
    "intel(r) active management",
    "pci\\ven_8086",
    "sol",
)


def normalize_port_name(value: object) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"\bCOM\d+\b", text)
    return match.group(0) if match else text


def port_text(port: SerialPortLike) -> str:
    return f"{getattr(port, 'device', '')} {getattr(port, 'description', '')} {getattr(port, 'hwid', '')}".lower()


def is_non_esp_port(port: SerialPortLike) -> bool:
    text = port_text(port)
    return any(keyword in text for keyword in NON_ESP_KEYWORDS)


def is_likely_esp32_port(port: SerialPortLike) -> bool:
    if is_non_esp_port(port):
        return False
    text = port_text(port)
    return any(keyword in text for keyword in ESP32_KEYWORDS)


def port_score(port: SerialPortLike, preferred_names: Iterable[str] = ()) -> int:
    device = normalize_port_name(getattr(port, "device", ""))
    preferred = {normalize_port_name(name) for name in preferred_names if str(name or "").strip()}
    if is_non_esp_port(port):
        return -100

    score = 0
    if is_likely_esp32_port(port):
        score += 90
    if "usb" in port_text(port) or "uart" in port_text(port):
        score += 20
    if device in preferred:
        score += 35
    return score


def choose_esp32_port(ports: Iterable[SerialPortLike], preferred_names: Iterable[str] = (), default: str = "COM6") -> str:
    candidates = list(ports)
    scored = sorted(
        ((port_score(port, preferred_names), normalize_port_name(getattr(port, "device", ""))) for port in candidates),
        reverse=True,
    )
    for score, device in scored:
        if score > 0 and device:
            return device

    preferred = [normalize_port_name(name) for name in preferred_names if str(name or "").strip()]
    for name in preferred:
        if name:
            return name
    return normalize_port_name(default)
