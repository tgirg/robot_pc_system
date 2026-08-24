from __future__ import annotations

import re
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from arduino_tools import (
    ArduinoCliResult,
    choose_esp32_port,
    compile_drive_controller,
    compile_sketch,
    find_arduino_cli,
    has_cached_build,
    is_likely_esp32_port,
    is_non_esp_port,
    normalize_port_name,
    run_arduino_version,
    run_board_list,
    run_core_list,
    upload_drive_controller,
    upload_cached_sketch,
    upload_sketch,
)

from .ui_helpers import boxed, make_button, make_notice
from .ui_feedback import clear_busy, format_elapsed_time, set_busy, show_error, show_info, show_success


SKETCH_CHOICES = [
    ("drive_controller", "drive_controller"),
    ("imu_9axis_test", "imu_9axis_test"),
    ("lidar_uart_test", "lidar_uart_test"),
    ("encoder_test", "encoder_test"),
    ("optical_odometry_test", "optical_odometry_test"),
    ("optical_field_reflect_example", "optical_field_reflect_example"),
    ("distance_sensor_test", "distance_sensor_test"),
    ("lsb_sensor_node", "lsb_sensor_node"),
    ("line_color_sensor_test", "line_color_sensor_test"),
    ("field_sensor_demo_test", "field_sensor_demo_test"),
    ("neopixel_test", "neopixel_test"),
    ("serial_echo_test", "serial_echo_test"),
    ("all_sensor_dummy_test", "all_sensor_dummy_test"),
]

SENSOR_SHORTCUTS = [
    ("9軸IMUテスト", "imu_9axis_test", "9軸IMUのI2CアドレスとIMU/GYRO出力を確認します。"),
    ("LiDARテスト", "lidar_uart_test", "UART LiDARの準備用ダミー出力を確認します。"),
    ("エンコーダテスト", "encoder_test", "左右エンコーダのカウント形式を確認します。"),
    ("光学式オドメトリテスト", "optical_odometry_test", "光学式オドメトリ確認用スケッチです。I2Cアドレス: 0x17 / SDA: GPIO21 / SCL: GPIO22。書き込み後はシリアルモニタで OPTICAL_STATUS,OK と OPTICAL,dx,dy を確認してください。"),
    ("光学式反映例", "optical_field_reflect_example", "FCアプリのテストフィールド反映確認用です。実センサを使わず OPTICAL_STATUS,OK と OPTICAL,dx,dy を出します。"),
    ("距離センサテスト", "distance_sensor_test", "前後左右の距離センサ形式を確認します。"),
    ("LSB基板テスト", "lsb_sensor_node", "LSB/ユニバーサル基板用です。USBシリアルで LSB,ID / LSB,I2C / LSB,SENS を出力します。"),
    ("ライン/カラーセンサテスト", "line_color_sensor_test", "ライン反射値とカラー判定形式を確認します。"),
    ("フィールド反映デモ", "field_sensor_demo_test", "ODOM/OPTICAL/IMU/LiDAR/ENCをOK出力し、R2のフィールド表示を確認します。"),
    ("NeoPixel LED\u30c6\u30b9\u30c8", "neopixel_test", "GPIO15\u306eNeoPixel 1\u500b\u3092\u8d64\u3001\u7dd1\u3001\u9752\u306e\u9806\u306b\u70b9\u706f\u78ba\u8a8d\u3057\u307e\u3059\u3002"),
    ("シリアル通信テスト", "serial_echo_test", "RX/ECHOでシリアル送受信を確認します。"),
    ("全センサダミーテスト", "all_sensor_dummy_test", "PC側UI/パーサ確認用に全センサ形式をまとめて出します。"),
]


class ArduinoCliWorker(QThread):
    result_ready = Signal(str, object)
    error_ready = Signal(str, str)

    def __init__(self, mode: str, fqbn: str = "esp32:esp32:esp32", port: str = "", sketch_name: str = "drive_controller") -> None:
        super().__init__()
        self.mode = mode
        self.fqbn = fqbn
        self.port = port
        self.sketch_name = sketch_name

    def run(self) -> None:
        try:
            if self.mode == "check":
                result = {
                    "version": run_arduino_version(),
                    "core_list": run_core_list(),
                    "board_list": run_board_list(),
                    "cli_path": find_arduino_cli(),
                }
            elif self.mode == "board_list":
                result = run_board_list()
            elif self.mode == "compile":
                result = compile_sketch(self.sketch_name, self.fqbn)
            elif self.mode == "upload":
                result = upload_sketch(self.sketch_name, self.port, self.fqbn)
            elif self.mode == "fast_upload":
                result = upload_cached_sketch(self.sketch_name, self.port, self.fqbn)
            else:
                raise ValueError(f"未対応のArduino CLI処理です: {self.mode}")
            self.result_ready.emit(self.mode, result)
        except Exception as exc:
            self.error_ready.emit(self.mode, str(exc))


class ArduinoUploadWidget(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.worker: ArduinoCliWorker | None = None
        self.running = False
        self.last_cli_path = find_arduino_cli() or "-"
        self.cli_ok = False
        self.core_ok = False
        self.board_checked = False
        self.compile_ok: bool | None = None
        self.upload_ok: bool | None = None

        self.status_label = QLabel("Arduino CLI状態: 未確認")
        self.status_label.setObjectName("diagnosticLabel")
        self.cli_path_label = QLabel(f"使用Arduino CLIパス: {self.last_cli_path}")
        self.cli_path_label.setObjectName("diagnosticLabel")
        self.sketch_combo = QComboBox()
        for label, sketch_name in SKETCH_CHOICES:
            self.sketch_combo.addItem(label, sketch_name)
        last_sketch = str(host.local_settings.get("last_upload_sketch", "drive_controller"))
        sketch_index = self.sketch_combo.findData(last_sketch)
        self.sketch_combo.setCurrentIndex(sketch_index if sketch_index >= 0 else 0)
        self.fqbn_edit = QLineEdit(str(host.local_settings.get("last_upload_fqbn", "esp32:esp32:esp32")))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(220)
        self._set_initial_port()
        self.confirm_checkbox = QCheckBox("安全確認しました")
        self.confirm_checkbox.setObjectName("diagnosticLabel")
        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumBlockCount(1200)
        self.output_log.setPlaceholderText("Arduino CLIの出力を表示します。")
        self.operation_label = QLabel("状態: 待機中")
        self.operation_label.setObjectName("diagnosticLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.busy_started_at = 0.0
        self.active_button = None
        self.guided_imu_upload_pending = False
        self.last_uploaded_port = ""

        self.workflow_labels: dict[str, QLabel] = {}
        self.next_after_upload_label = QLabel("")
        self.next_after_upload_label.setObjectName("modeNoticeLabel")
        self.next_after_upload_label.setWordWrap(True)

        self.check_button = make_button("Arduino CLI確認", self.run_cli_check)
        self.board_button = make_button("ボード一覧更新", self.run_board_list)
        self.compile_button = make_button("コンパイル確認", self.run_compile)
        self.upload_button = make_button("ESP32へ書き込み", self.confirm_and_upload)
        self.fast_upload_check = QCheckBox("高速書き込み")
        self.fast_upload_check.setToolTip("前回コンパイル済みのビルドを再利用して、コンパイルを省略します。")
        self.imu_select_button = make_button("9軸IMUテストを書き込む", self.select_imu_test_sketch)
        self.imu_compile_upload_button = make_button("9軸IMUテストをコンパイルして書き込み", self.compile_and_upload_imu_test)
        self.open_serial_monitor_button = make_button("シリアルモニタで確認する", self.open_serial_monitor_for_uploaded_imu)
        self.open_serial_monitor_button.hide()
        self.move_machine_button = make_button("実機接続タブへ移動", lambda: host.switch_to_tab("実機接続"))
        self.clear_button = make_button("ログ消去", self.output_log.clear)
        self.copy_button = make_button("ログをコピー", self.copy_log)
        self.sensor_shortcut_buttons = [
            make_button(label, lambda _checked=False, sketch=sketch, description=description: self.select_sensor_test_sketch(sketch, description), 42)
            for label, sketch, description in SENSOR_SHORTCUTS
        ]
        self.confirm_checkbox.stateChanged.connect(self._update_upload_enabled)

        self._build()
        self._update_workflow_labels()
        self._update_upload_enabled()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(make_notice(
            "モータ出力は既定で無効です。書き込み前にESP32接続を一時切断します。Arduino IDEのシリアルモニタを閉じてください。"
        ))
        layout.addWidget(self._workflow_box())
        layout.addWidget(self.status_label)
        layout.addWidget(self.operation_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.cli_path_label)

        form = QWidget()
        form_layout = QGridLayout(form)
        form_layout.addWidget(QLabel("スケッチ選択"), 0, 0)
        form_layout.addWidget(self.sketch_combo, 0, 1)
        form_layout.addWidget(QLabel("FQBN入力"), 1, 0)
        form_layout.addWidget(self.fqbn_edit, 1, 1)
        form_layout.addWidget(QLabel("COMポート入力"), 2, 0)
        form_layout.addWidget(self.port_combo, 2, 1)
        form_layout.setColumnStretch(1, 1)
        layout.addWidget(form)
        layout.addWidget(self._imu_help_box())
        layout.addWidget(self._sensor_shortcut_box())
        layout.addWidget(self._checklist_box())

        imu_buttons = QWidget()
        imu_button_layout = QHBoxLayout(imu_buttons)
        imu_button_layout.addWidget(self.imu_select_button)
        imu_button_layout.addWidget(self.imu_compile_upload_button)
        imu_button_layout.addWidget(self.open_serial_monitor_button)
        imu_button_layout.addStretch(1)
        layout.addWidget(imu_buttons)

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        for button in [
            self.check_button,
            self.board_button,
            self.compile_button,
            self.upload_button,
            self.move_machine_button,
            self.clear_button,
            self.copy_button,
        ]:
            button_layout.addWidget(button)
        button_layout.addWidget(self.fast_upload_check)
        button_layout.addStretch(1)
        layout.addWidget(buttons)
        layout.addWidget(self.next_after_upload_label)
        layout.addWidget(boxed("出力ログ", self.output_log), 1)

    def _imu_help_box(self) -> QWidget:
        guide = QLabel(
            "9軸IMU確認手順:\n"
            "1. 9軸IMUを 3.3V / GND / SDA / SCL に接続\n"
            "2. スケッチ選択で imu_9axis_test を選択\n"
            "3. コンパイル確認\n"
            "4. ESP32へ書き込み\n"
            "5. シリアルモニタを 115200bps で接続\n"
            "6. I2C device found at 0x68 / 0x69 / 0x28 を確認\n"
            "7. IMU_STATUS,OK と IMU/GYRO の値を確認"
        )
        guide.setWordWrap(True)
        guide.setObjectName("diagnosticLabel")
        return boxed("9軸IMU確認手順", guide)

    def _sensor_shortcut_box(self) -> QWidget:
        box = QWidget()
        layout = QGridLayout(box)
        for index, button in enumerate(self.sensor_shortcut_buttons):
            layout.addWidget(button, index // 4, index % 4)
        return boxed("センサテスト近道", box)

    def _workflow_box(self) -> QWidget:
        box = QWidget()
        layout = QGridLayout(box)
        rows = [
            ("cli", "1 Arduino CLI確認"),
            ("board", "2 ボード一覧更新"),
            ("compile", "3 コンパイル確認"),
            ("safety", "4 安全確認"),
            ("upload", "5 ESP32へ書き込み"),
            ("move", "6 実機接続へ移動"),
        ]
        for index, (key, title) in enumerate(rows):
            title_label = QLabel(title)
            status_label = QLabel("未確認")
            status_label.setObjectName("quickCheckItem")
            self.workflow_labels[key] = status_label
            layout.addWidget(title_label, index, 0)
            layout.addWidget(status_label, index, 1)
        return boxed("書き込み作業ナビ", box)

    def _checklist_box(self) -> QWidget:
        checklist = QWidget()
        layout = QVBoxLayout(checklist)
        layout.addWidget(QLabel("書き込み前チェック:"))
        for text in [
            "Arduino IDEのシリアルモニタを閉じた",
            "COMポートを確認した",
            "FQBNを確認した",
            "モータ出力が無効である",
        ]:
            label = QLabel(f"- {text}")
            label.setObjectName("diagnosticLabel")
            layout.addWidget(label)
        layout.addWidget(self.confirm_checkbox)
        return boxed("書き込み前チェック", checklist)

    def _set_initial_port(self) -> None:
        port = choose_esp32_port(
            list_ports.comports(),
            [
                "COM10",
                str(self.host.local_settings.get("last_upload_port") or ""),
                str(self.host.local_settings.get("last_com_port") or ""),
                str(self.host.serial.port or ""),
            ],
        )
        self.port_combo.addItem(port)
        self.port_combo.setCurrentText(port)

    def _update_upload_enabled(self) -> None:
        self.upload_button.setEnabled(self.confirm_checkbox.isChecked() and not self.running and self.worker is None)
        self._update_workflow_labels()

    def _set_running(self, running: bool, status: str) -> None:
        self.running = running
        self.status_label.setText(f"Arduino CLI状態: {status}")
        for button in [self.board_button, self.check_button, self.compile_button, self.upload_button, self.imu_select_button, self.imu_compile_upload_button]:
            button.setEnabled(not running)
        if running:
            self.progress.show()
            show_info(self.operation_label, status)
        else:
            self.progress.hide()
        self._update_upload_enabled()

    def _current_fqbn(self) -> str:
        return self.fqbn_edit.text().strip() or "esp32:esp32:esp32"

    def _current_sketch(self) -> str:
        return str(self.sketch_combo.currentData() or "drive_controller")

    def _current_port(self) -> str:
        return normalize_port_name(self.port_combo.currentText().strip() or "COM10")

    def _set_sketch(self, sketch_name: str) -> None:
        index = self.sketch_combo.findData(sketch_name)
        if index >= 0:
            self.sketch_combo.setCurrentIndex(index)

    def _remember_inputs(self) -> None:
        self.host.local_settings["last_upload_port"] = self._current_port()
        self.host.local_settings["last_upload_fqbn"] = self._current_fqbn()
        self.host.local_settings["last_upload_sketch"] = self._current_sketch()
        if self.last_cli_path and self.last_cli_path != "-":
            self.host.local_settings["last_arduino_cli_path"] = self.last_cli_path
        self.host._save_local_settings()

    def run_cli_check(self) -> None:
        self.host._log("Arduino CLI確認を実行しました")
        self._start_worker("check", "確認中")

    def run_board_list(self) -> None:
        self.host._log("ボード一覧更新を開始しました")
        self._start_worker("board_list", "ボード一覧取得中")

    def run_compile(self) -> None:
        self._remember_inputs()
        self.host._log("ESP32コンパイル確認を開始しました")
        self._start_worker("compile", "コンパイル中")

    def select_imu_test_sketch(self) -> None:
        self.select_sensor_test_sketch("imu_9axis_test", "9軸IMUのI2CアドレスとIMU/GYRO出力を確認します。")

    def select_sensor_test_sketch(self, sketch_name: str, description: str = "") -> None:
        self._set_sketch(sketch_name)
        self.fqbn_edit.setText("esp32:esp32:esp32")
        port = self._preferred_sensor_port()
        if port:
            self.port_combo.setCurrentText(port)
        self._remember_inputs()
        message = (
            f"{sketch_name} を選択しました。\n"
            f"{description}\n"
            "次に「コンパイル確認」または「ESP32へ書き込み」を押してください。"
        )
        show_success(self.operation_label, f"{sketch_name} を選択しました")
        self.append_log(message)
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"{sketch_name} を選択しました", "success")

    def compile_and_upload_imu_test(self) -> None:
        self.select_imu_test_sketch()
        port = self._current_port()
        if not port or not self._selected_port_is_available():
            message = "ESP32のCOMポートが見つかりません。ESP32をUSB接続してから「ボード一覧更新」を押してください。"
            QMessageBox.warning(self, "COMポート未検出", message)
            show_error(self.operation_label, message)
            self.guided_imu_upload_pending = False
            clear_busy(self.imu_compile_upload_button)
            return
        self.guided_imu_upload_pending = True
        self._remember_inputs()
        self.append_log("9軸IMUテストのコンパイルを開始します。")
        self._start_worker("compile", "9軸IMUテストをコンパイル中")

    def confirm_and_upload(self) -> None:
        if not self.confirm_checkbox.isChecked():
            QMessageBox.warning(self, "安全確認", "書き込み前に「安全確認しました」にチェックしてください。")
            return
        message = (
            "ESP32へ書き込みますか？\n\n"
            "現在のESP32接続は一時切断されます。\n"
            "モータ出力は既定で無効です。\n"
            "書き込み後は、実機接続タブでESP32へ再接続してください。"
        )
        answer = QMessageBox.question(
            self,
            "ESP32書き込み確認",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.append_log("書き込みをキャンセルしました。")
            return
        status = self.host.serial.status()
        if status.connected and not status.mock:
            self.host.disconnect_esp32_from_ui()
            self.host._log("書き込み前にESP32接続を切断しました")
            self.append_log("書き込み前にESP32接続を切断しました。")
        self._remember_inputs()
        self.host._log("ESP32書き込みを開始しました")
        if self.fast_upload_check.isChecked() and has_cached_build(self._current_sketch(), self._current_fqbn()):
            self.append_log("高速書き込み: 前回コンパイル済みビルドを使います。")
            self._start_worker("fast_upload", "高速書き込み中")
        else:
            if self.fast_upload_check.isChecked():
                self.append_log("高速書き込み: キャッシュがないため通常書き込みを実行します。先にコンパイル確認を押すと次回から高速化できます。")
            self._start_worker("upload", "書き込み中")

    def _confirm_and_start_guided_imu_upload(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            from PySide6.QtCore import QTimer

            QTimer.singleShot(100, self._confirm_and_start_guided_imu_upload)
            return
        port = self._current_port()
        if not port or not self._selected_port_is_available():
            message = "ESP32のCOMポートが見つかりません。ESP32をUSB接続してから「ボード一覧更新」を押してください。"
            QMessageBox.warning(self, "COMポート未検出", message)
            show_error(self.operation_label, message)
            self.guided_imu_upload_pending = False
            clear_busy(self.imu_compile_upload_button)
            return
        answer = QMessageBox.question(
            self,
            "9軸IMUテスト書き込み確認",
            "9軸IMUテストを書き込みますか？\nモータは未接続想定ですが、Arduino IDEのシリアルモニタは閉じてください。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.append_log("9軸IMUテストの書き込みをキャンセルしました。")
            show_info(self.operation_label, "9軸IMUテストの書き込みをキャンセルしました")
            self.guided_imu_upload_pending = False
            clear_busy(self.imu_compile_upload_button)
            return
        self.confirm_checkbox.setChecked(True)
        status = self.host.serial.status()
        if status.connected and not status.mock:
            self.host.disconnect_esp32_from_ui()
            self.append_log("書き込み前にESP32接続を切断しました。")
        self._remember_inputs()
        self._start_worker("upload", "9軸IMUテストを書き込み中")

    def _start_worker(self, mode: str, status: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.append_log("Arduino CLI処理中です。完了までお待ちください。")
            show_info(self.operation_label, "現在処理中です。完了までお待ちください。")
            return
        self.busy_started_at = time.time()
        self.active_button = {
            "check": self.check_button,
            "board_list": self.board_button,
            "compile": self.compile_button,
            "upload": self.upload_button,
            "fast_upload": self.upload_button,
        }.get(mode)
        busy_text = {
            "check": "確認中...",
            "board_list": "更新中...",
            "compile": "コンパイル中...",
            "upload": "書き込み中...",
            "fast_upload": "高速書き込み中...",
        }.get(mode, "処理中...")
        if self.active_button is not None:
            set_busy(self.active_button, busy_text)
        if self.guided_imu_upload_pending and mode == "compile":
            set_busy(self.imu_compile_upload_button, "コンパイル中...")
        elif self.guided_imu_upload_pending and mode == "upload":
            set_busy(self.imu_compile_upload_button, "書き込み中...")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(status, "busy")
        self._set_running(True, status)
        self.append_log(f"=== {status} ===")
        self.worker = ArduinoCliWorker(mode, fqbn=self._current_fqbn(), port=self._current_port(), sketch_name=self._current_sketch())
        self.worker.result_ready.connect(self._handle_result)
        self.worker.error_ready.connect(self._handle_error)
        self.worker.finished.connect(self._clear_worker)
        self.worker.start()

    def _clear_worker(self) -> None:
        if self.active_button is not None:
            clear_busy(self.active_button)
            self.active_button = None
        if not self.guided_imu_upload_pending:
            clear_busy(self.imu_compile_upload_button)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self._update_upload_enabled()

    def _handle_error(self, mode: str, message: str) -> None:
        self._set_running(False, "失敗")
        show_error(self.operation_label, f"失敗: {message}")
        self.append_log(f"エラー: {message}")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"Arduino CLI処理失敗: {message}", "error")
        self.host._log(f"Arduino CLI処理失敗: {message}")
        self._write_file_log(mode, None, message)

    def _handle_result(self, mode: str, result) -> None:
        self._set_running(False, "成功" if self._result_success(result) else "失敗")
        elapsed = format_elapsed_time(time.time() - self.busy_started_at) if self.busy_started_at else "-"
        success = self._result_success(result)
        if success:
            show_success(self.operation_label, f"成功（{elapsed}）")
        else:
            show_error(self.operation_label, f"失敗（{elapsed}）。ログを確認してください。")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"Arduino CLI {'成功' if success else '失敗'}: {mode}", "success" if success else "error")
        if mode == "check":
            self._append_check_result(result)
            success = self._result_success(result)
            self.host.arduino_cli_checked = True
            self.host.arduino_cli_ok = success
            self.host._log(f"Arduino CLI確認{'成功' if success else '失敗'}")
        elif isinstance(result, ArduinoCliResult):
            label = {
                "board_list": "ボード一覧更新",
                "compile": "コンパイル",
                "upload": "書き込み",
                "fast_upload": "高速書き込み",
            }.get(mode, mode)
            self.append_log(self._format_result(label, result))
            if mode == "board_list":
                self.board_checked = True
                self.host.board_list_checked = True
                self._append_readable_board_list(result.stdout)
                self._maybe_set_port_from_board_list(result.stdout)
            if mode == "compile":
                self.compile_ok = result.success
                self.host.compile_checked = True
                self.host.compile_ok = result.success
                self.host._log("コンパイル成功" if result.success else "コンパイル失敗")
                if self.guided_imu_upload_pending:
                    if result.success:
                        from PySide6.QtCore import QTimer

                        QTimer.singleShot(100, self._confirm_and_start_guided_imu_upload)
                    else:
                        self.guided_imu_upload_pending = False
                        clear_busy(self.imu_compile_upload_button)
            if mode in {"upload", "fast_upload"}:
                self.upload_ok = result.success
                self.host.upload_checked = True
                self.host.upload_ok = result.success
                if result.success:
                    self.last_uploaded_port = self._current_port()
                    if self._current_sketch() in {"imu_9axis_test", "optical_odometry_test"}:
                        self.next_after_upload_label.setText("書き込み完了。シリアルモニタへ移動すると115200bpsで接続を開始します。")
                        self.open_serial_monitor_button.show()
                    else:
                        self.next_after_upload_label.setText("書き込み完了。次は実機接続タブでESP32へ再接続してください。")
                    self.host._log("書き込み成功")
                else:
                    self.host._log("書き込み失敗")
                self.guided_imu_upload_pending = False
                clear_busy(self.imu_compile_upload_button)
            self._write_file_log(mode, result, "")
        self._update_workflow_labels()
        if hasattr(self.host, "_update_workflow_state"):
            self.host._update_workflow_state()

    def _result_success(self, result) -> bool:
        if isinstance(result, dict):
            return all(isinstance(item, ArduinoCliResult) and item.success for key, item in result.items() if key != "cli_path")
        return isinstance(result, ArduinoCliResult) and result.success

    def _append_check_result(self, result: dict) -> None:
        cli_path = result.get("cli_path") or "-"
        self.last_cli_path = cli_path
        self.cli_path_label.setText(f"使用Arduino CLIパス: {cli_path}")
        version = result.get("version")
        core_list = result.get("core_list")
        board_list = result.get("board_list")
        self.cli_ok = isinstance(version, ArduinoCliResult) and version.success
        self.core_ok = isinstance(core_list, ArduinoCliResult) and "esp32:esp32" in core_list.stdout
        self.host.esp32_core_ok = self.core_ok
        self.append_log("=== Arduino CLI確認結果 ===")
        self.append_log(f"Arduino CLI: {'OK' if self.cli_ok else 'NG'}")
        self.append_log(f"ESP32 core: {'OK' if self.core_ok else 'NG'}")
        if isinstance(version, ArduinoCliResult):
            self.append_log(self._format_result("version", version))
        if isinstance(core_list, ArduinoCliResult):
            self.append_log(self._format_result("core list", core_list))
        if isinstance(board_list, ArduinoCliResult):
            self.board_checked = True
            self._append_readable_board_list(board_list.stdout)
            self._maybe_set_port_from_board_list(board_list.stdout)
        self._write_file_log("check", None, self.output_log.toPlainText())

    def _format_result(self, title: str, result: ArduinoCliResult) -> str:
        return "\n".join(
            [
                f"=== {title} ===",
                f"結果: {'成功' if result.success else '失敗'}",
                f"開始: {result.started_at}",
                f"終了: {result.finished_at}",
                f"経過秒: {result.elapsed_seconds}",
                f"戻り値: {result.return_code}",
                "コマンド:",
                " ".join(result.command),
                "--- stdout ---",
                result.stdout.strip() or "(なし)",
                "--- stderr ---",
                result.stderr.strip() or "(なし)",
                "",
            ]
        )

    def _append_readable_board_list(self, text: str) -> None:
        lines = [line for line in text.splitlines() if line.strip()]
        self.append_log("=== ボード一覧（読みやすい表示） ===")
        self.append_log("COMポート / 種類 / Board Name / FQBN")
        for line in lines[1:] if lines and "Port" in lines[0] else lines:
            self.append_log(line)
        found = self._find_esp32_like_port(text)
        if found:
            self.append_log(f"ESP32候補: {found}")
            show_success(self.operation_label, f"ESP32候補: {found}")
        else:
            self.append_log("ESP32が見つかりません。USB接続を確認してください。")
            self.append_log("Arduino IDEのシリアルモニタ、シリアルモニタ、実機接続がCOMを使用中の可能性があります。")
            show_error(self.operation_label, "ESP32が見つかりません。USB接続を確認してください。")

    def _find_esp32_like_port(self, text: str) -> str:
        preferred = ""
        fallback = ""
        for line in text.splitlines():
            upper = line.upper()
            lower = line.lower()
            match = re.search(r"\bCOM\d+\b", upper)
            if not match:
                continue
            port = match.group(0)
            if any(keyword in lower for keyword in ["bluetooth", "bthenum", "active management", "intel"]):
                continue
            if port == "COM10":
                preferred = port
            if any(keyword in upper for keyword in ["ESP32", "CP210", "CH340", "CH910", "USB SERIAL", "USB TO UART", "SILICON LABS", "WCH"]):
                fallback = port
        return preferred or fallback

    def _maybe_set_port_from_board_list(self, text: str) -> None:
        port = self._find_esp32_like_port(text)
        if not port:
            return
        self.port_combo.setCurrentText(port)
        self.append_log(f"ESP32候補をCOMポート欄へ設定しました: {port}")

    def _preferred_sensor_port(self) -> str:
        ports = list(list_ports.comports())
        chosen = choose_esp32_port(
            ports,
            [
                "COM10",
                str(self.host.local_settings.get("last_upload_port") or ""),
                str(self.host.local_settings.get("last_com_port") or ""),
                self._current_port(),
            ],
        )
        known = {normalize_port_name(port.device): port for port in ports}
        info = known.get(chosen)
        if info is not None and (is_likely_esp32_port(info) or chosen == "COM10"):
            return chosen
        if chosen == "COM10":
            return chosen
        for candidate in [
            str(self.host.local_settings.get("last_upload_port") or ""),
            str(self.host.local_settings.get("last_com_port") or ""),
            self._current_port(),
        ]:
            normalized = normalize_port_name(candidate)
            info = known.get(normalized)
            if info is not None and not is_non_esp_port(info):
                return normalized
        return chosen

    def _selected_port_is_available(self) -> bool:
        port = self._current_port()
        if not port:
            return False
        return port.upper() in {normalize_port_name(item.device) for item in list_ports.comports()}

    def open_serial_monitor_for_uploaded_imu(self) -> None:
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is None:
            self.host.switch_to_tab("シリアル")
            monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is None:
            show_error(self.operation_label, "シリアルモニタが見つかりません")
            return
        port = self.last_uploaded_port or self._current_port()
        monitor.refresh_ports(log=False)
        if port:
            index = monitor.port_combo.findData(port)
            if index >= 0:
                monitor.port_combo.setCurrentIndex(index)
            else:
                monitor.port_combo.setCurrentText(port)
        monitor.baud_combo.setCurrentText("115200")
        if hasattr(monitor, "reset_on_connect_checkbox"):
            monitor.reset_on_connect_checkbox.setChecked(True)
        self.host.switch_to_tab("シリアル")
        message = "COMポートと115200bpsを設定しました。シリアルタブで接続を開始します。"
        show_success(self.operation_label, message)
        monitor.append_log(message)
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(message, "success")

    def _update_workflow_labels(self) -> None:
        values = {
            "cli": "OK" if self.cli_ok else "未確認",
            "board": "OK" if self.board_checked else "未確認",
            "compile": "成功" if self.compile_ok is True else "失敗" if self.compile_ok is False else "未実行",
            "safety": "OK" if self.confirm_checkbox.isChecked() else "未確認",
            "upload": "成功" if self.upload_ok is True else "失敗" if self.upload_ok is False else "未実行",
            "move": "書き込み後に実行" if self.upload_ok else "待機中",
        }
        for key, text in values.items():
            label = self.workflow_labels.get(key)
            if label:
                label.setText(text)

    def append_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.output_log.appendPlainText(f"[{timestamp}] {text}")

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.output_log.toPlainText())
        self.host._log("Arduino CLIログをクリップボードへコピーしました")

    def _write_file_log(self, mode: str, result: ArduinoCliResult | None, extra: str) -> None:
        try:
            log_dir = self.host._project_root() / "logs"
            log_dir.mkdir(exist_ok=True)
            path = log_dir / "arduino_upload.log"
            with path.open("a", encoding="utf-8") as file:
                file.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] mode={mode}\n")
                if result is not None:
                    file.write(f"command={' '.join(result.command)}\n")
                    file.write(f"success={result.success} return_code={result.return_code}\n")
                    file.write("--- stdout ---\n")
                    file.write(result.stdout)
                    file.write("\n--- stderr ---\n")
                    file.write(result.stderr)
                    file.write("\n")
                if extra:
                    file.write(str(extra))
                    file.write("\n")
        except Exception:
            pass


def create_arduino_upload_panel(host) -> QWidget:
    return boxed("ESP32書き込み", ArduinoUploadWidget(host))
