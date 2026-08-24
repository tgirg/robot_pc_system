from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
PC_DIR = ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from PySide6.QtWidgets import QApplication

from widgets.arduino_ide_widget import ArduinoIdeWidget, DEFAULT_FQBN, DEFAULT_SKETCH, get_sketch_choices, sketch_file_path


class _SerialStub:
    port = "COM10"


class _HostStub:
    def __init__(self) -> None:
        self.local_settings = {}
        self.serial = _SerialStub()

    def _save_local_settings(self) -> None:
        pass

    def switch_to_tab(self, _name: str) -> None:
        pass


def main() -> None:
    sketches = get_sketch_choices()
    required = {
        "drive_controller",
        "imu_9axis_test",
        "lidar_uart_test",
        "encoder_test",
        "optical_odometry_test",
        "optical_field_reflect_example",
        "distance_sensor_test",
        "lsb_sensor_node",
        "line_color_sensor_test",
        "field_sensor_demo_test",
        "neopixel_test",
        "serial_echo_test",
        "all_sensor_dummy_test",
    }
    missing = sorted(required - set(sketches))
    assert not missing, f"スケッチ一覧に不足があります: {missing}"
    assert DEFAULT_SKETCH == "drive_controller"
    assert DEFAULT_FQBN == "esp32:esp32:esp32"
    assert sketch_file_path(DEFAULT_SKETCH).exists(), f"初期スケッチが見つかりません: {sketch_file_path(DEFAULT_SKETCH)}"

    app = QApplication.instance() or QApplication([])
    widget = ArduinoIdeWidget(_HostStub())
    assert widget.easy_find_button.text() == "1 ESP32を探す"
    assert widget.easy_imu_button.text() == "9軸IMUテストを書き込む"
    assert widget.easy_neopixel_button.text() == "NeoPixelテストを書き込む"
    assert widget.easy_drive_button.text() == "通常制御を書き込む"
    assert widget.easy_selected_button.text() == "選択中を書き込む"
    widget.close()
    app.processEvents()
    print("Arduino IDE風タブ import test: OK")


if __name__ == "__main__":
    main()
