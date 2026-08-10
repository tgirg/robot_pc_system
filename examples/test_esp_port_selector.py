from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from arduino_tools import choose_esp32_port, is_likely_esp32_port, is_non_esp_port, normalize_port_name  # noqa: E402


def port(device: str, description: str, hwid: str = ""):
    return SimpleNamespace(device=device, description=description, hwid=hwid)


def main() -> int:
    bluetooth = port("COM4", "Bluetooth リンク経由の標準シリアル", "BTHENUM\\dummy")
    intel_sol = port("COM3", "Intel(R) Active Management Technology - SOL", "PCI\\VEN_8086")
    cp210 = port("COM8", "Silicon Labs CP210x USB to UART Bridge", "USB VID:PID=10C4:EA60")
    ch340 = port("COM11", "USB-SERIAL CH340", "USB VID:PID=1A86:7523")
    com10 = port("COM10", "USB Serial Device", "USB VID:PID=303A:1001")

    assert is_non_esp_port(bluetooth)
    assert is_non_esp_port(intel_sol)
    assert not is_likely_esp32_port(bluetooth)
    assert is_likely_esp32_port(cp210)
    assert is_likely_esp32_port(ch340)
    assert normalize_port_name("COM10 - USB Serial") == "COM10"

    assert choose_esp32_port([bluetooth, intel_sol], default="COM6") == "COM6"
    assert choose_esp32_port([bluetooth, cp210], default="COM10") == "COM8"
    assert choose_esp32_port([cp210, com10], default="COM10") == "COM8"
    assert choose_esp32_port([cp210, com10], preferred_names=["COM8"], default="COM10") == "COM8"
    assert choose_esp32_port([bluetooth, ch340], preferred_names=["COM11"], default="COM10") == "COM11"
    print("esp port selector test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
