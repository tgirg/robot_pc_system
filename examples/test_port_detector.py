from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from connection import detect_ports  # noqa: E402


def main() -> None:
    print("COMポート検出を実行します。")
    ports = detect_ports()
    if not ports:
        print("COMポートが見つかりません。USBケーブルを確認してください。")
        return
    for port in ports:
        marker = "ESP32候補" if port.is_likely_esp32 else "通常"
        print(f"{port.port} - {port.description} / {marker} / {port.hwid}")


if __name__ == "__main__":
    main()
