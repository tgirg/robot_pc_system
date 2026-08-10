from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from PySide6.QtWidgets import QApplication

from main_ui import MainWindow


def assert_card_zero(window: MainWindow, key: str) -> None:
    cards = window.machine_cards.get(key, [])
    if not cards:
        raise SystemExit(f"失敗: {key}カードが見つかりません")
    for card in cards:
        status = card["状態"].text()
        value = card["値"].text()
        data_type = card["データ種別"].text()
        if status != "未接続":
            raise SystemExit(f"失敗: {key}状態が未接続ではありません: {status}")
        if "0" not in value:
            raise SystemExit(f"失敗: {key}値が0表示ではありません: {value}")
        if data_type not in {"0表示", "信号なし"}:
            raise SystemExit(f"失敗: {key}データ種別が信号なし扱いではありません: {data_type}")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.update_loop()
    app.processEvents()

    assert_card_zero(window, "imu")
    assert_card_zero(window, "lidar")
    assert_card_zero(window, "encoder")

    lidar_text = window.sensor_panel.values["LiDAR distance"].text()
    encoder_text = window.sensor_panel.values["Encoder left/right"].text()
    imu_text = window.sensor_panel.values["IMU yaw/pitch/roll"].text()
    if "前: 0 mm" not in lidar_text or "左: 0 mm" not in lidar_text:
        raise SystemExit(f"失敗: LiDAR概要が0表示ではありません: {lidar_text}")
    if "未接続" not in encoder_text or "左 0" not in encoder_text or "右 0" not in encoder_text:
        raise SystemExit(f"失敗: エンコーダ概要が未接続・0表示ではありません: {encoder_text}")
    if "0.0" not in imu_text:
        raise SystemExit(f"失敗: IMU概要が0表示ではありません: {imu_text}")

    if hasattr(window, "test_field_widget"):
        if window.test_field_widget.sensor_statuses.get("lidar") != "未接続":
            raise SystemExit("失敗: テストフィールドのLiDAR状態が未接続ではありません")
        if any(window.test_field_widget.lidar_values):
            raise SystemExit("失敗: テストフィールドのLiDAR値が0ではありません")

    window.close()
    print("no signal display test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
