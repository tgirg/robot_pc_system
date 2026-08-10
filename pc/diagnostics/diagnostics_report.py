from __future__ import annotations

import json
from typing import Any

try:
    from .camera_check import check_cameras
    from .environment_check import check_environment
    from .serial_port_check import list_serial_ports
except ImportError:
    from camera_check import check_cameras
    from environment_check import check_environment
    from serial_port_check import list_serial_ports


def build_report() -> dict[str, Any]:
    return {
        "environment": check_environment(),
        "serial_ports": list_serial_ports(),
        "cameras": check_cameras(0, 3),
    }


def print_japanese_summary(report: dict[str, Any] | None = None) -> None:
    report = report or build_report()
    environment = report["environment"]
    serial_ports = report["serial_ports"]
    cameras = report["cameras"]

    print("=== 診断レポート ===")
    python = environment["python"]
    print(f"Python: {python['version']} ({'OK' if python['ok'] else 'NG'})")
    print(f"実行ファイル: {python['executable']}")
    print("")

    print("[ライブラリ]")
    for name, result in environment["imports"].items():
        print(f"{name}: {'OK' if result['available'] else 'NG'}")
    print("")

    print("[COMポート]")
    if not serial_ports["ok"]:
        print(f"NG: {serial_ports['error']}")
    elif not serial_ports["ports"]:
        print("COMポートは見つかりませんでした。")
    else:
        for port in serial_ports["ports"]:
            print(f"{port['device']}  {port['description']}  {port['hwid']}")
    print("")

    print("[カメラ]")
    if not cameras["ok"]:
        print(f"NG: {cameras['error']}")
    else:
        for camera in cameras["cameras"]:
            state = "使用可能" if camera["available"] else "未検出"
            size = f"{camera['width']}x{camera['height']}" if camera["available"] else "-"
            print(f"index {camera['index']}: {state} {size}")


def main() -> None:
    report = build_report()
    print_japanese_summary(report)
    print("")
    print("構造化データ(JSON):")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
