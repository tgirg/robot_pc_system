from __future__ import annotations

from typing import Any


def list_serial_ports() -> dict[str, Any]:
    try:
        from connection import detect_ports
    except ImportError as exc:
        return {"ok": False, "error": f"接続ライブラリを読み込めません: {exc}", "ports": []}

    ports = [
        {
            "device": port.port,
            "description": port.description,
            "hwid": port.hwid,
            "likely_device_type": port.likely_device_type,
        }
        for port in detect_ports()
    ]
    return {
        "ok": True,
        "error": "",
        "ports": ports,
    }
