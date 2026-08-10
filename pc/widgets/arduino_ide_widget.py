from __future__ import annotations

import re
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arduino_tools import (
    ArduinoCliResult,
    choose_esp32_port,
    compile_sketch,
    find_arduino_cli,
    has_cached_build,
    is_likely_esp32_port,
    is_non_esp_port,
    normalize_port_name,
    port_score,
    run_board_list,
    upload_cached_sketch,
    upload_sketch,
)

from .ui_helpers import boxed, make_button, make_notice, set_monospace


DEFAULT_BOARD_LABEL = "ESP32 Dev Module"
DEFAULT_FQBN = "esp32:esp32:esp32"
DEFAULT_SKETCH = "drive_controller"
BAUDRATES = ["9600", "57600", "115200", "230400", "921600"]
NEWLINES = {"なし": "", "LF": "\n", "CRLF": "\r\n"}

SKETCH_CHOICES: list[tuple[str, str]] = [
    ("drive_controller", "通常制御（安全ダミー）"),
    ("imu_9axis_test", "9軸IMUテスト"),
    ("lidar_uart_test", "LiDAR UARTテスト"),
    ("encoder_test", "エンコーダテスト"),
    ("optical_odometry_test", "光学式オドメトリテスト"),
    ("optical_field_reflect_example", "光学式反映例"),
    ("distance_sensor_test", "距離センサテスト"),
    ("line_color_sensor_test", "ライン/カラーセンサテスト"),
    ("field_sensor_demo_test", "フィールド反映デモ"),
    ("neopixel_test", "NeoPixel LED\u30c6\u30b9\u30c8"),
    ("serial_echo_test", "シリアル送受信テスト"),
    ("all_sensor_dummy_test", "全センサDUMMY受信テスト"),
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_sketch_choices() -> list[str]:
    return [name for name, _label in SKETCH_CHOICES]


def sketch_directory(sketch_name: str) -> Path:
    safe_name = str(sketch_name).strip().replace("/", "").replace("\\", "")
    return project_root() / "esp32" / (safe_name or DEFAULT_SKETCH)


def sketch_file_path(sketch_name: str) -> Path:
    directory = sketch_directory(sketch_name)
    preferred = directory / f"{directory.name}.ino"
    if preferred.exists():
        return preferred
    ino_files = sorted(directory.glob("*.ino"))
    if ino_files:
        return ino_files[0]
    return preferred


class ArduinoIdeWorker(QThread):
    result_ready = Signal(str, object)
    error_ready = Signal(str, str)

    def __init__(self, mode: str, sketch_name: str = DEFAULT_SKETCH, fqbn: str = DEFAULT_FQBN, port: str = "") -> None:
        super().__init__()
        self.mode = mode
        self.sketch_name = sketch_name
        self.fqbn = fqbn
        self.port = port

    def run(self) -> None:
        try:
            if self.mode == "board_list":
                result = run_board_list()
            elif self.mode in {"compile", "compile_for_upload"}:
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


class ArduinoSerialMonitorPanel(QWidget):
    def __init__(self, host, parent_ide: "ArduinoIdeWidget") -> None:
        super().__init__()
        self.host = host
        self.parent_ide = parent_ide
        self.conn: serial.Serial | None = None
        self.receiving = False
        self.raw_text = ""

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(180)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(BAUDRATES)
        self.baud_combo.setCurrentText("115200")
        self.auto_scroll_checkbox = QCheckBox("自動スクロール")
        self.auto_scroll_checkbox.setChecked(True)
        self.reset_on_connect_checkbox = QCheckBox("接続時にESP32をリセット")
        self.reset_on_connect_checkbox.setChecked(True)
        self.status_label = QLabel("状態: 未接続")
        self.i2c_label = QLabel("検出されたI2Cアドレス: 未検出")
        self.imu_label = QLabel("IMU状態: 未検出")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMinimumHeight(220)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setStyleSheet("QPlainTextEdit { background:#050505; color:#e5e7eb; }")

        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("ESP32へ送信する文字列を入力します。例: DRIVE STOP")
        self.newline_combo = QComboBox()
        self.newline_combo.addItems(list(NEWLINES.keys()))
        self.newline_combo.setCurrentText("LF")

        self.refresh_button = make_button("COM更新", self.refresh_ports, 34)
        self.connect_button = make_button("接続", self.connect_monitor, 34)
        self.disconnect_button = make_button("切断", self.disconnect_monitor, 34)
        self.reset_button = make_button("ESP32リセット", self.reset_esp32, 34)
        self.clear_button = make_button("ログ消去", self.clear_log, 34)
        self.copy_button = make_button("ログコピー", self.copy_log, 34)
        self.save_button = make_button("ログ保存", self.save_log, 34)
        self.send_button = make_button("送信", self.send_text, 34)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_serial)

        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(make_notice("この欄はArduino IDEのシリアルモニタ代わりです。モータ接続時は送信コマンドに注意してください。"))

        form = QWidget()
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addWidget(QLabel("COM"), 0, 0)
        form_layout.addWidget(self.port_combo, 0, 1)
        form_layout.addWidget(QLabel("ボーレート"), 1, 0)
        form_layout.addWidget(self.baud_combo, 1, 1)
        form_layout.addWidget(self.status_label, 2, 0, 1, 2)
        form_layout.addWidget(self.i2c_label, 3, 0, 1, 2)
        form_layout.addWidget(self.imu_label, 4, 0, 1, 2)
        form_layout.setColumnStretch(1, 1)
        layout.addWidget(form)

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        for button in [
            self.refresh_button,
            self.connect_button,
            self.disconnect_button,
            self.reset_button,
            self.clear_button,
            self.copy_button,
            self.save_button,
        ]:
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        layout.addWidget(buttons)
        layout.addWidget(self.reset_on_connect_checkbox)
        layout.addWidget(self.auto_scroll_checkbox)

        send_row = QWidget()
        send_layout = QHBoxLayout(send_row)
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.addWidget(QLabel("送信"))
        send_layout.addWidget(self.send_edit, 1)
        send_layout.addWidget(QLabel("改行"))
        send_layout.addWidget(self.newline_combo)
        send_layout.addWidget(self.send_button)
        layout.addWidget(send_row)

        expected = QLabel(
            "9軸IMUテスト成功例:\n"
            "BOOT,IMU_9AXIS_TEST_READY\n"
            "I2C scan start\n"
            "I2C device found at 0x68\n"
            "IMU_STATUS,OK\n"
            "IMU,... / GYRO,...\n"
            "STATUS,OK"
        )
        expected.setWordWrap(True)
        layout.addWidget(boxed("確認例", expected))
        layout.addWidget(boxed("シリアル出力", self.log_view), 1)

    def current_port(self) -> str:
        data = self.port_combo.currentData()
        if data:
            return str(data).strip()
        text = self.port_combo.currentText().strip()
        return text.split(" - ")[0].strip()

    def set_port_and_baud(self, port: str, baudrate: int = 115200) -> None:
        if port:
            index = self.port_combo.findData(port)
            if index < 0:
                self.port_combo.addItem(port, port)
                index = self.port_combo.findData(port)
            self.port_combo.setCurrentIndex(index)
        self.baud_combo.setCurrentText(str(baudrate))

    def refresh_ports(self) -> None:
        current = self.current_port()
        self.port_combo.clear()
        ports = list(list_ports.comports())
        for port in ports:
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)
        if not ports:
            fallback = current or "COM10"
            self.port_combo.addItem(fallback, fallback)
        if self.port_combo.findData("COM10") < 0:
            self.port_combo.addItem("COM10 - 手入力候補（ESP32）", "COM10")
        self.parent_ide.select_preferred_port(self.port_combo, current)

    def uses_port(self, port: str | None = None) -> bool:
        if self.conn is None or not self.conn.is_open:
            return False
        if port is None:
            return True
        return str(self.conn.port).upper() == str(port).upper()

    def connect_monitor(self) -> None:
        port = self.current_port()
        if not port:
            QMessageBox.warning(self, "COMポート未選択", "COMポートを選択してください。")
            return
        if self._other_monitor_uses_port(port):
            QMessageBox.warning(
                self,
                "COMポート使用中",
                "診断タブのシリアルモニタがCOMポートを使用中です。\n先にシリアルモニタを切断してください。",
            )
            return
        status = self.host.serial.status()
        if status.connected and not status.mock and str(self.host.serial.port).upper() == port.upper():
            QMessageBox.warning(
                self,
                "COMポート使用中",
                "現在、実機接続でCOMポートを使用中です。\nArduinoタブで使用するには、実機接続を切断してください。",
            )
            return
        if self.uses_port(port):
            self.append_log(f"すでに接続中です: {port}")
            return
        if self.conn is not None:
            self.disconnect_monitor()
        try:
            self.conn = serial.Serial(port, int(self.baud_combo.currentText()), timeout=0.02, write_timeout=0.2)
        except serial.SerialException as exc:
            self.status_label.setText("状態: 接続失敗")
            self.append_log(f"接続失敗: {exc}")
            QMessageBox.warning(
                self,
                "COMポートを開けません",
                "COMポートを開けませんでした。\nArduino IDEのシリアルモニタ、診断タブ、実機接続が使用中でないか確認してください。",
            )
            return
        self.status_label.setText(f"状態: 接続中 {port} / {self.baud_combo.currentText()} bps")
        self.append_log(f"接続しました: {port} / {self.baud_combo.currentText()} bps")
        if self.reset_on_connect_checkbox.isChecked():
            self.reset_esp32()
        self.start_receive()

    def disconnect_monitor(self) -> None:
        self.stop_receive()
        if self.conn is not None:
            try:
                if self.conn.is_open:
                    self.conn.close()
            except serial.SerialException as exc:
                self.append_log(f"切断エラー: {exc}")
        self.conn = None
        self.status_label.setText("状態: 未接続")
        self.append_log("切断しました")

    def start_receive(self) -> None:
        if self.conn is None or not self.conn.is_open:
            return
        self.receiving = True
        self.timer.start(50)

    def stop_receive(self) -> None:
        self.receiving = False
        self.timer.stop()

    def poll_serial(self) -> None:
        if not self.receiving or self.conn is None or not self.conn.is_open:
            return
        try:
            waiting = self.conn.in_waiting
            data = self.conn.read(waiting or 1)
        except serial.SerialException as exc:
            self.append_log(f"受信エラー: {exc}")
            self.disconnect_monitor()
            return
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        self.raw_text += text
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertPlainText(text)
        if self.auto_scroll_checkbox.isChecked():
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self._update_detected_status()

    def send_text(self) -> None:
        if self.conn is None or not self.conn.is_open:
            QMessageBox.warning(self, "未接続", "シリアルモニタを接続してから送信してください。")
            return
        text = self.send_edit.text()
        newline = NEWLINES.get(self.newline_combo.currentText(), "\n")
        try:
            self.conn.write((text + newline).encode("utf-8"))
            self.conn.flush()
        except serial.SerialException as exc:
            self.append_log(f"送信エラー: {exc}")
            return
        self.append_log(f"> {text}")
        self.send_edit.clear()

    def reset_esp32(self) -> None:
        if self.conn is None or not self.conn.is_open:
            self.append_log("ESP32リセット: 未接続のためスキップ")
            return
        try:
            self.conn.setDTR(False)
            self.conn.setRTS(True)
            time.sleep(0.05)
            self.conn.setRTS(False)
            time.sleep(0.05)
            self.conn.setDTR(True)
            self.append_log("ESP32リセットを実行しました")
        except serial.SerialException as exc:
            self.append_log(f"ESP32リセット失敗: {exc}")

    def clear_log(self) -> None:
        self.raw_text = ""
        self.log_view.clear()
        self._update_detected_status()

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())

    def save_log(self) -> None:
        try:
            log_dir = project_root() / "logs" / "arduino_serial_monitor"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = log_dir / f"arduino_serial_{timestamp}.txt"
            body = "\n".join(
                [
                    f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"COM port: {self.current_port() or '-'}",
                    f"baudrate: {self.baud_combo.currentText()}",
                    "",
                    self.log_view.toPlainText(),
                ]
            )
            path.write_text(body, encoding="utf-8")
            (log_dir / "latest_arduino_serial.txt").write_text(body, encoding="utf-8")
            self.append_log(f"ログ保存: {path}")
        except OSError as exc:
            self.append_log(f"ログ保存失敗: {exc}")

    def append_log(self, text: str) -> None:
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertPlainText(f"{text}\n")
        if self.auto_scroll_checkbox.isChecked():
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.raw_text = self.log_view.toPlainText()
        self._update_detected_status()

    def _other_monitor_uses_port(self, port: str) -> bool:
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is None or not hasattr(monitor, "uses_port"):
            return False
        return bool(monitor.uses_port(port))

    def _update_detected_status(self) -> None:
        text = self.log_view.toPlainText()
        matches = sorted(set(re.findall(r"I2C device found at 0x([0-9A-Fa-f]{2})", text)))
        if matches:
            addresses = ", ".join(f"0x{item.upper()}" for item in matches)
            self.i2c_label.setText(f"検出されたI2Cアドレス: {addresses}")
        else:
            self.i2c_label.setText("検出されたI2Cアドレス: 未検出")

        if re.search(r"^IMU_STATUS,OK", text, flags=re.MULTILINE):
            self.imu_label.setText("IMU状態: OK")
        elif re.search(r"^IMU_STATUS,ERROR", text, flags=re.MULTILINE):
            self.imu_label.setText("IMU状態: ERROR")
        else:
            self.imu_label.setText("IMU状態: 未検出")


class ArduinoIdeWidget(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.worker: ArduinoIdeWorker | None = None
        self.current_file: Path | None = None
        self.loading_editor = False
        self.unsaved = False
        self.last_upload_port = ""
        self.pending_upload_after_compile = False
        self.upload_confirmation_needed = False
        self.fast_upload_pending = False
        self.current_operation = ""
        self.port_metadata = {}

        self.board_combo = QComboBox()
        self.board_combo.addItem(DEFAULT_BOARD_LABEL, DEFAULT_FQBN)
        self.board_combo.setCurrentIndex(0)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(220)
        self.sketch_combo = QComboBox()
        for sketch, description in SKETCH_CHOICES:
            self.sketch_combo.addItem(f"{sketch} - {description}", sketch)
        last_sketch = str(host.local_settings.get("last_upload_sketch", DEFAULT_SKETCH))
        sketch_index = self.sketch_combo.findData(last_sketch)
        self.sketch_combo.setCurrentIndex(sketch_index if sketch_index >= 0 else 0)
        self.fqbn_edit = QLineEdit(str(host.local_settings.get("last_upload_fqbn", DEFAULT_FQBN)))

        self.status_label = QLabel("状態: 待機中")
        self.easy_status_label = QLabel("手順: ESP32をUSB接続して「ESP32を探す」を押してください。")
        self.easy_status_label.setWordWrap(True)
        self.file_label = QLabel("ファイル: -")
        self.unsaved_label = QLabel("保存済み")
        self.safety_label = QLabel("")
        self.port_hint_label = QLabel("ESP32候補: 未確認")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        self.verify_button = make_button("✓ 検証", self.run_verify, 42)
        self.upload_button = make_button("→ 書き込み", self.confirm_compile_then_upload, 42)
        self.easy_find_button = make_button("1 ESP32を探す", self.easy_find_esp32, 54)
        self.easy_imu_button = make_button("9軸IMUテストを書き込む", lambda: self.easy_upload_sketch("imu_9axis_test"), 54)
        self.easy_field_demo_button = make_button("フィールド反映デモを書き込む", lambda: self.easy_upload_sketch("field_sensor_demo_test"), 54)
        self.easy_optical_button = make_button("光学式テストを書き込む", lambda: self.easy_upload_sketch("optical_odometry_test"), 54)
        self.easy_optical_example_button = make_button("光学式反映例を書き込む", lambda: self.easy_upload_sketch("optical_field_reflect_example"), 54)
        self.easy_lidar_button = make_button("LiDARテストを書き込む", lambda: self.easy_upload_sketch("lidar_uart_test"), 54)
        self.easy_neopixel_button = make_button("NeoPixel\u30c6\u30b9\u30c8\u3092\u66f8\u304d\u8fbc\u3080", lambda: self.easy_upload_sketch("neopixel_test"), 54)
        self.easy_drive_button = make_button("通常制御を書き込む", lambda: self.easy_upload_sketch("drive_controller"), 54)
        self.easy_selected_button = make_button("選択中を書き込む", self.easy_upload_selected_sketch, 54)
        self.stop_button = make_button("■ 停止/切断", self.stop_or_disconnect, 42)
        self.serial_focus_button = make_button("シリアルへ移動", self.focus_serial_monitor, 42)
        self.refresh_button = make_button("更新", self.refresh_board_and_ports, 42)
        self.save_button = make_button("保存", self.save_current_sketch, 38)
        self.output_copy_button = make_button("ログコピー", self.copy_output_log, 34)
        self.output_clear_button = make_button("ログ消去", self.output_log_clear, 34)
        self.output_save_button = make_button("ログ保存", self.save_output_log, 34)
        self.open_serial_after_upload_button = make_button("シリアルで確認", self.prepare_serial_monitor_after_upload, 42)
        self.open_serial_after_upload_button.hide()
        self.fast_upload_check = QCheckBox("高速書き込み")
        self.fast_upload_check.setToolTip("前回コンパイル済みのビルドを再利用して、コンパイルを省略します。")

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setMinimumHeight(360)
        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumBlockCount(3000)
        self.output_log.setMinimumHeight(180)
        self.output_log.setStyleSheet("QPlainTextEdit { background:#050505; color:#e5e7eb; }")
        set_monospace(self.output_log)
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save_current_sketch)
        self.editor.textChanged.connect(self._mark_unsaved)
        self.sketch_combo.currentIndexChanged.connect(self.load_selected_sketch)

        self._build()
        self.refresh_ports(log=False)
        self.load_selected_sketch()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        safety = make_notice("安全: 実モータ出力は無効です。書き込みは確認後のみ実行します。")
        layout.addWidget(safety)
        layout.addWidget(self._easy_write_box())

        toolbar = QWidget()
        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.addWidget(self.verify_button, 0, 0)
        toolbar_layout.addWidget(self.upload_button, 0, 1)
        toolbar_layout.addWidget(self.stop_button, 0, 2)
        toolbar_layout.addWidget(self.serial_focus_button, 0, 3)
        toolbar_layout.addWidget(self.refresh_button, 0, 4)
        toolbar_layout.addWidget(self.save_button, 0, 5)
        toolbar_layout.addWidget(self.fast_upload_check, 0, 6)
        toolbar_layout.addWidget(QLabel("スケッチ"), 1, 0)
        toolbar_layout.addWidget(self.sketch_combo, 1, 1, 1, 3)
        toolbar_layout.addWidget(QLabel("書き込み先"), 1, 4)
        toolbar_layout.addWidget(self.port_combo, 1, 5, 1, 4)
        toolbar_layout.setColumnStretch(8, 1)
        layout.addWidget(toolbar)

        detail_box = QWidget()
        detail_layout = QGridLayout(detail_box)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("ボード"), 0, 0)
        detail_layout.addWidget(self.board_combo, 0, 1)
        detail_layout.addWidget(QLabel("FQBN"), 0, 2)
        detail_layout.addWidget(self.fqbn_edit, 0, 3)
        detail_layout.setColumnStretch(3, 1)
        detail_group = boxed("詳細設定", detail_box)
        detail_group.setCheckable(True)
        detail_group.setChecked(False)
        detail_box.setVisible(False)
        detail_group.toggled.connect(detail_box.setVisible)
        layout.addWidget(detail_group)

        status_row = QWidget()
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.port_hint_label)
        status_layout.addWidget(self.open_serial_after_upload_button)
        status_layout.addStretch(1)
        layout.addWidget(status_row)
        layout.addWidget(self.safety_label)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_top = QWidget()
        editor_top_layout = QHBoxLayout(editor_top)
        editor_top_layout.setContentsMargins(0, 0, 0, 0)
        editor_top_layout.addWidget(self.file_label, 1)
        editor_top_layout.addWidget(self.unsaved_label)
        editor_layout.addWidget(editor_top)
        editor_layout.addWidget(self.editor, 1)
        layout.addWidget(editor_panel, 1)

        output_buttons = QWidget()
        output_button_layout = QHBoxLayout(output_buttons)
        output_button_layout.setContentsMargins(0, 0, 0, 0)
        output_button_layout.addWidget(QLabel("出力"))
        output_button_layout.addStretch(1)
        output_button_layout.addWidget(self.output_copy_button)
        output_button_layout.addWidget(self.output_clear_button)
        output_button_layout.addWidget(self.output_save_button)
        layout.addWidget(output_buttons)
        layout.addWidget(self.output_log)

    def _easy_write_box(self) -> QWidget:
        body = QWidget()
        layout = QGridLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.easy_status_label, 0, 0, 1, 4)
        layout.addWidget(self.easy_find_button, 1, 0)
        layout.addWidget(self.easy_imu_button, 1, 1)
        layout.addWidget(self.easy_neopixel_button, 1, 2)
        layout.addWidget(self.easy_drive_button, 1, 3)
        layout.addWidget(self.easy_selected_button, 1, 4)
        layout.addWidget(self.easy_field_demo_button, 2, 1)
        layout.addWidget(self.easy_optical_button, 2, 2)
        layout.addWidget(self.easy_lidar_button, 2, 3)
        layout.addWidget(self.easy_optical_example_button, 3, 1)
        layout.setColumnStretch(4, 1)
        return boxed("かんたん書き込み", body)

    def current_sketch(self) -> str:
        return str(self.sketch_combo.currentData() or DEFAULT_SKETCH)

    def current_port(self) -> str:
        data = self.port_combo.currentData()
        if data:
            return normalize_port_name(data)
        text = self.port_combo.currentText().strip()
        return normalize_port_name(text.split(" - ")[0].strip())

    def current_fqbn(self) -> str:
        text = self.fqbn_edit.text().strip()
        return text or DEFAULT_FQBN

    def uses_port(self, port: str | None = None) -> bool:
        return False

    def easy_find_esp32(self) -> None:
        self.easy_status_label.setText("ESP32を探しています。USB接続、ケーブル、Arduino IDEのシリアルモニタを確認してください。")
        self.refresh_board_and_ports()

    def easy_upload_selected_sketch(self) -> None:
        self.easy_upload_sketch(self.current_sketch())

    def easy_upload_sketch(self, sketch_name: str) -> None:
        if self.worker is not None:
            self.append_output("書き込みツール処理中です。完了まで待ってください。")
            return
        if not self._select_sketch(sketch_name):
            return
        self.fqbn_edit.setText(DEFAULT_FQBN)
        self.refresh_ports(log=True)
        port = self.current_port()
        if not self._detected_upload_port_ready(port):
            self.easy_status_label.setText("ESP32がまだ見つかっていません。ESP32をUSB接続して「ESP32を探す」を押してください。")
            QMessageBox.warning(
                self,
                "ESP32未検出",
                "ESP32のUSBシリアルが見つかっていません。\nESP32をUSB接続してから「ESP32を探す」を押してください。",
            )
            return
        self.easy_status_label.setText(f"{sketch_name} を {port} へ書き込みます。コンパイル後に確認ダイアログを表示します。")
        self.confirm_compile_then_upload()

    def refresh_board_and_ports(self) -> None:
        self.refresh_ports(log=True)
        if self.worker is None:
            self.append_output("ボード一覧を更新します。")
            self._start_worker("board_list")

    def refresh_ports(self, log: bool = True) -> None:
        current = self.current_port()
        self.port_combo.clear()
        self.port_metadata = {}
        ports = list(list_ports.comports())
        preferred_names = [
            "COM10",
            str(self.host.local_settings.get("last_upload_port") or ""),
            str(self.host.local_settings.get("last_com_port") or ""),
            current,
            str(getattr(self.host.serial, "port", "") or ""),
        ]
        for port in ports:
            device = normalize_port_name(port.device)
            self.port_metadata[device] = port
            marker = ""
            if is_likely_esp32_port(port) or device == "COM10":
                marker = " / ESP32候補"
            elif is_non_esp_port(port):
                marker = " / ESP書き込み対象外"
            self.port_combo.addItem(f"{device} - {port.description}{marker}", device)

        preferred = choose_esp32_port(ports, preferred_names)
        if preferred and self.port_combo.findData(preferred) < 0:
            self.port_combo.addItem(f"{preferred} - 手入力候補（ESP32未検出）", preferred)
        self.select_preferred_port(self.port_combo, current)
        self._update_port_hint(ports, preferred)
        if log:
            self.append_output(f"COMポートを更新しました: {len(ports)}件")
            self._append_port_summary(ports, preferred)
        self._update_easy_status()

    def select_preferred_port(self, combo: QComboBox, current: str = "") -> None:
        ports = list(list_ports.comports())
        preferred = choose_esp32_port(
            ports,
            [
                "COM10",
                str(self.host.local_settings.get("last_upload_port") or ""),
                str(self.host.local_settings.get("last_com_port") or ""),
                current,
                str(getattr(self.host.serial, "port", "") or ""),
            ],
        )
        if preferred and combo.findData(preferred) < 0:
            combo.addItem(f"{preferred} - 手入力候補（ESP32未検出）", preferred)
        candidates = [
            preferred,
            "COM10",
            str(self.host.local_settings.get("last_upload_port") or ""),
            str(self.host.local_settings.get("last_com_port") or ""),
            current,
            str(getattr(self.host.serial, "port", "") or ""),
        ]
        for candidate in [item for item in candidates if item]:
            index = combo.findData(candidate)
            if index >= 0:
                combo.setCurrentIndex(index)
                return
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def _update_port_hint(self, ports, preferred: str) -> None:
        known = {normalize_port_name(port.device): port for port in ports}
        port = known.get(preferred)
        if port is not None and (is_likely_esp32_port(port) or preferred == "COM10"):
            self.port_hint_label.setText(f"ESP32候補: {preferred}")
        elif preferred == "COM10":
            self.port_hint_label.setText("ESP32未検出: USB接続後に更新してください（COM10を手入力候補にしています）")
        elif ports:
            self.port_hint_label.setText("ESP32が見つかりません。Bluetooth/管理ポートは書き込み先にしません。")
        else:
            self.port_hint_label.setText("COMポートなし。ESP32をUSB接続して更新してください。")

    def _append_port_summary(self, ports, preferred: str) -> None:
        if not ports:
            self.append_output("ESP32のCOMポートが見つかりません。USB接続してから更新してください。")
            return
        for port in ports:
            device = normalize_port_name(port.device)
            score = port_score(port, [preferred])
            if is_likely_esp32_port(port) or device == "COM10":
                label = "ESP32候補"
            elif is_non_esp_port(port):
                label = "対象外"
            else:
                label = "未判定"
            self.append_output(f"{device}: {label} / {port.description} / score={score}")
        if preferred == "COM10" and preferred not in {normalize_port_name(port.device) for port in ports}:
            self.append_output("ESP32候補が未検出のため、COM10を手入力候補として表示しました。ESP32を挿してから更新してください。")

    def _update_easy_status(self) -> None:
        port = self.current_port()
        if self._detected_upload_port_ready(port):
            self.easy_status_label.setText(f"ESP32候補: {port}。書き込みたいボタンを押してください。")
        else:
            self.easy_status_label.setText("ESP32未検出。USB接続後に「ESP32を探す」を押してください。")

    def _detected_upload_port_ready(self, port: str) -> bool:
        info = self.port_metadata.get(normalize_port_name(port))
        if info is None:
            return False
        return not is_non_esp_port(info)

    def _select_sketch(self, sketch_name: str) -> bool:
        index = self.sketch_combo.findData(sketch_name)
        if index < 0:
            QMessageBox.warning(self, "スケッチ未検出", f"{sketch_name} が見つかりません。")
            return False
        if self.sketch_combo.currentIndex() == index:
            return True
        self.sketch_combo.setCurrentIndex(index)
        return self.current_sketch() == sketch_name

    def load_selected_sketch(self) -> None:
        if self.unsaved and self.current_file is not None:
            answer = QMessageBox.question(
                self,
                "未保存の変更",
                "未保存の変更があります。保存してからスケッチを切り替えますか？",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                old_index = self.sketch_combo.findData(self.current_file.parent.name)
                if old_index >= 0:
                    self.sketch_combo.blockSignals(True)
                    self.sketch_combo.setCurrentIndex(old_index)
                    self.sketch_combo.blockSignals(False)
                return
            if answer == QMessageBox.StandardButton.Save and not self.save_current_sketch():
                return
        sketch = self.current_sketch()
        path = sketch_file_path(sketch)
        self.current_file = path
        self.loading_editor = True
        try:
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            self.editor.setPlainText(text)
            self.append_output(f"スケッチを読み込みました: {sketch}")
        except OSError as exc:
            self.editor.setPlainText("")
            self.append_output(f"スケッチ読み込み失敗: {exc}")
        finally:
            self.loading_editor = False
        self.unsaved = False
        self._update_file_labels()
        self._update_safety_label()

    def save_current_sketch(self) -> bool:
        if self.current_file is None:
            return False
        try:
            self.current_file.parent.mkdir(parents=True, exist_ok=True)
            new_text = self.editor.toPlainText()
            old_text = self.current_file.read_text(encoding="utf-8", errors="replace") if self.current_file.exists() else ""
            if self.current_file.exists() and old_text != new_text:
                backup_dir = project_root() / "backups" / "firmware" / "arduino_ide_tab"
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"{timestamp}_{self.current_file.name}"
                backup_path.write_text(old_text, encoding="utf-8")
                self.append_output(f"バックアップ作成: {backup_path}")
            self.current_file.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "保存失敗", f"スケッチを保存できませんでした。\n{exc}")
            self.append_output(f"保存失敗: {exc}")
            return False
        self.unsaved = False
        self._update_file_labels()
        self._update_safety_label()
        self._remember_settings()
        self.append_output(f"保存しました: {self.current_file}")
        return True

    def run_verify(self) -> None:
        if self.worker is not None:
            self.append_output("書き込みツール処理中です。完了まで待ってください。")
            return
        if not self._validate_board():
            return
        if not self.save_current_sketch():
            return
        self.pending_upload_after_compile = False
        self.append_output("コンパイル開始")
        self.append_output(f"スケッチ: {self.current_sketch()}")
        self.append_output(f"FQBN: {self.current_fqbn()}")
        self._start_worker("compile")

    def confirm_compile_then_upload(self) -> None:
        if self.worker is not None:
            self.append_output("書き込みツール処理中です。完了まで待ってください。")
            return
        if not self._validate_board() or not self._validate_port():
            return
        if self._port_is_busy_for_upload():
            return
        if not self.save_current_sketch():
            return
        if self.fast_upload_check.isChecked():
            if has_cached_build(self.current_sketch(), self.current_fqbn()):
                self.fast_upload_pending = True
                self.append_output("高速書き込み: 前回コンパイル済みビルドを使います。")
                self.start_upload_after_confirmation()
                return
            self.append_output("高速書き込み: キャッシュがないため、今回はコンパイルしてから書き込みます。")
        self.pending_upload_after_compile = True
        self.append_output("書き込み前のコンパイルを開始します。")
        self._start_worker("compile_for_upload")

    def start_upload_after_confirmation(self) -> None:
        port = self.current_port()
        answer = QMessageBox.question(
            self,
            "ESP32へ書き込み",
            "ESP32へ書き込みますか？\nArduino IDE、シリアルタブ、実機接続が同じCOMポートを使っていないか確認してください。\n自動アップロードではなく、この確認後にだけ書き込みます。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.append_output("書き込みをキャンセルしました。")
            self.status_label.setText("状態: 書き込みキャンセル")
            return
        status = self.host.serial.status()
        if status.connected and not status.mock and str(self.host.serial.port).upper() == port.upper():
            self.host.disconnect_esp32_from_ui()
            self.append_output("書き込み前に実機接続を切断しました。")
            self.host._log("書き込み前にESP32接続を切断しました")
        self.append_output(f"書き込み開始: {port}")
        self.last_upload_port = port
        mode = "fast_upload" if self.fast_upload_pending else "upload"
        self.fast_upload_pending = False
        self._start_worker(mode)

    def stop_or_disconnect(self) -> None:
        if self.worker is not None:
            self.append_output("書き込みツール処理中です。処理は完了まで待機します。")
            return
        self.status_label.setText("状態: 待機中")
        self.append_output("書き込み処理は待機中です。シリアル通信はシリアルタブで操作してください。")

    def focus_serial_monitor(self) -> None:
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "set_port_and_baud"):
            monitor.set_port_and_baud(self.last_upload_port or self.current_port(), 115200)
        self.host.switch_to_tab("シリアル")
        self.append_output("シリアルタブへ移動しました。")

    def prepare_serial_monitor_after_upload(self) -> None:
        port = self.last_upload_port or self.current_port()
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "set_port_and_baud"):
            monitor.set_port_and_baud(port, 115200)
            monitor.reset_on_connect_checkbox.setChecked(True)
        self.host.switch_to_tab("シリアル")
        self.append_output("COMポートと115200bpsを設定しました。シリアルタブで接続を開始します。")
        QMessageBox.information(self, "シリアル", "COMポートと115200bpsを設定しました。\nシリアルタブで接続を開始します。")

    def append_output(self, text: str) -> None:
        prefix = time.strftime("[%H:%M:%S] ")
        self.output_log.moveCursor(QTextCursor.MoveOperation.End)
        self.output_log.insertPlainText(prefix + text.rstrip() + "\n")
        self.output_log.moveCursor(QTextCursor.MoveOperation.End)

    def copy_output_log(self) -> None:
        QApplication.clipboard().setText(self.output_log.toPlainText())

    def output_log_clear(self) -> None:
        self.output_log.clear()

    def save_output_log(self) -> None:
        try:
            log_dir = project_root() / "logs" / "arduino_ide"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = log_dir / f"arduino_ide_{timestamp}.txt"
            path.write_text(self.output_log.toPlainText(), encoding="utf-8")
            self.append_output(f"出力ログを保存しました: {path}")
        except OSError as exc:
            self.append_output(f"出力ログ保存失敗: {exc}")

    def _start_worker(self, mode: str) -> None:
        self.worker = ArduinoIdeWorker(mode, self.current_sketch(), self.current_fqbn(), self.current_port())
        self.current_operation = mode
        self.worker.result_ready.connect(self._handle_worker_result)
        self.worker.error_ready.connect(self._handle_worker_error)
        self.worker.finished.connect(self._worker_finished)
        self._set_busy(True, mode)
        self.worker.start()

    def _handle_worker_result(self, mode: str, result: object) -> None:
        if isinstance(result, ArduinoCliResult):
            self._append_cli_result(mode, result)
            if mode == "compile_for_upload":
                if result.success:
                    self.status_label.setText("状態: コンパイル成功")
                    self.easy_status_label.setText("コンパイル成功。確認ダイアログで承認すると書き込みます。")
                    self.upload_confirmation_needed = True
                else:
                    self.upload_confirmation_needed = False
                    self.status_label.setText("状態: コンパイル失敗")
                    self.easy_status_label.setText("コンパイル失敗。出力ログを確認してください。")
                    QMessageBox.warning(self, "コンパイル失敗", "コンパイルに失敗しました。下の出力ログを確認してください。")
            elif mode == "compile":
                self.status_label.setText("状態: コンパイル成功" if result.success else "状態: コンパイル失敗")
                if result.success:
                    QMessageBox.information(self, "検証成功", "コンパイル成功")
            elif mode in {"upload", "fast_upload"}:
                self.status_label.setText("状態: 書き込み成功" if result.success else "状態: 書き込み失敗")
                if result.success:
                    self.last_upload_port = self.current_port()
                    self.host.local_settings["last_upload_port"] = self.last_upload_port
                    self.host.local_settings["last_upload_fqbn"] = self.current_fqbn()
                    self.host.local_settings["last_upload_sketch"] = self.current_sketch()
                    self.host._save_local_settings()
                    self.open_serial_after_upload_button.show()
                    QTimer.singleShot(800, self.prepare_serial_monitor_after_upload)
                    done_text = "高速書き込み完了。" if mode == "fast_upload" else "書き込み完了。"
                    self.easy_status_label.setText(f"{done_text}シリアル確認へ進めます。")
                    QMessageBox.information(self, "書き込み完了", f"{done_text}次は「シリアルで確認」を押すと115200bpsで接続を開始します。")
                else:
                    self.easy_status_label.setText("書き込み失敗。COMポート、BOOTボタン、シリアル使用中を確認してください。")
                    self._append_upload_failure_hint(result)
                    QMessageBox.warning(self, "書き込み失敗", "書き込みに失敗しました。COMポートと接続状態を確認してください。")
            elif mode == "board_list":
                self.status_label.setText("状態: ボード一覧更新完了" if result.success else "状態: ボード一覧更新失敗")
                self._maybe_set_port_from_board_list(result.stdout)
                self._update_easy_status()
        else:
            self.append_output(str(result))

    def _handle_worker_error(self, mode: str, message: str) -> None:
        self.status_label.setText("状態: エラー")
        self.append_output(f"エラー: {mode}: {message}")
        QMessageBox.warning(self, "書き込みツールエラー", message)

    def _worker_finished(self) -> None:
        finished_operation = self.current_operation
        self._set_busy(False, finished_operation)
        self.worker = None
        self.current_operation = ""
        if finished_operation == "compile_for_upload" and self.upload_confirmation_needed:
            self.upload_confirmation_needed = False
            QTimer.singleShot(0, self.start_upload_after_confirmation)

    def _append_cli_result(self, mode: str, result: ArduinoCliResult) -> None:
        title_map = {
            "board_list": "ボード一覧更新",
            "compile": "検証",
            "compile_for_upload": "書き込み前コンパイル",
            "upload": "書き込み",
            "fast_upload": "高速書き込み",
        }
        self.append_output(f"=== {title_map.get(mode, mode)} ===")
        self.append_output("コマンド: " + " ".join(result.command))
        self.append_output(f"終了コード: {result.return_code}")
        self.append_output(f"経過時間: {result.elapsed_seconds} 秒")
        if result.stdout.strip():
            self.append_output("--- stdout ---")
            self.output_log.insertPlainText(result.stdout.rstrip() + "\n")
        if result.stderr.strip():
            self.append_output("--- stderr ---")
            self.output_log.insertPlainText(result.stderr.rstrip() + "\n")
        self.append_output("結果: 成功" if result.success else "結果: 失敗")

    def _set_busy(self, busy: bool, mode: str) -> None:
        self.progress.setVisible(busy)
        for button in [
            self.verify_button,
            self.upload_button,
            self.refresh_button,
            self.save_button,
            self.easy_find_button,
            self.easy_imu_button,
            self.easy_field_demo_button,
            self.easy_optical_button,
            self.easy_optical_example_button,
            self.easy_lidar_button,
            self.easy_neopixel_button,
            self.easy_drive_button,
            self.easy_selected_button,
        ]:
            button.setEnabled(not busy)
        if busy:
            labels = {
                "board_list": "状態: ボード一覧更新中...",
                "compile": "状態: コンパイル中...",
                "compile_for_upload": "状態: 書き込み前コンパイル中...",
                "upload": "状態: 書き込み中...",
                "fast_upload": "状態: 高速書き込み中...",
            }
            self.status_label.setText(labels.get(mode, "状態: 処理中..."))
        else:
            self.progress.hide()

    def _mark_unsaved(self) -> None:
        if self.loading_editor:
            return
        self.unsaved = True
        self._update_file_labels()
        self._update_safety_label()

    def _update_file_labels(self) -> None:
        self.file_label.setText(f"ファイル: {self.current_file.name}" if self.current_file else "ファイル: -")
        self.file_label.setToolTip(str(self.current_file) if self.current_file else "")
        self.unsaved_label.setText("未保存の変更あり" if self.unsaved else "保存済み")

    def _update_safety_label(self) -> None:
        text = self.editor.toPlainText()
        motor_enabled = bool(re.search(r"^\s*#\s*define\s+MOTOR_OUTPUT_ENABLED\s+1\b", text, flags=re.MULTILINE))
        real_lidar = bool(re.search(r"^\s*#\s*define\s+USE_REAL_LIDAR\s+1\b", text, flags=re.MULTILINE))
        real_imu = bool(re.search(r"^\s*#\s*define\s+USE_REAL_IMU\s+1\b", text, flags=re.MULTILINE))
        sketch = self.current_sketch()
        if motor_enabled:
            safety = "注意: 実モータ出力が有効になっています。"
        elif sketch == "drive_controller":
            safety = "通常制御用 / 実モータ出力なし"
        elif sketch == "optical_odometry_test":
            safety = "光学式オドメトリ確認用 / I2C 0x17 / SDA GPIO21 / SCL GPIO22 / ロボットは動きません"
        elif sketch == "optical_field_reflect_example":
            safety = "光学式反映例 / OPTICAL,dx,dyのみ出力 / ロボットは動きません"
        else:
            safety = "センサ確認用 / ロボットは動きません"
        options = []
        if real_lidar:
            options.append("LiDAR実入力")
        if real_imu:
            options.append("IMU実入力")
        suffix = f" / {', '.join(options)}" if options else ""
        self.safety_label.setText(f"安全確認: {safety}{suffix}")

    def _validate_board(self) -> bool:
        if not self.current_fqbn():
            QMessageBox.warning(self, "ボード未選択", "ボードを選択してください。")
            return False
        return True

    def _validate_port(self) -> bool:
        port = self.current_port()
        if not port:
            QMessageBox.warning(self, "ポート未選択", "ポートを選択してください。ESP32をUSB接続して更新を押してください。")
            return False
        info = self.port_metadata.get(port)
        if info is not None and is_non_esp_port(info):
            QMessageBox.warning(
                self,
                "ESP32ではないCOMポート",
                "選択中のCOMポートはBluetoothまたは管理用ポートです。\nESP32をUSB接続し、「更新」を押してESP32候補を選んでください。",
            )
            self.append_output(f"書き込み中止: {port} はESP32書き込み対象外です。")
            return False
        if info is None:
            QMessageBox.warning(
                self,
                "COMポート未検出",
                f"{port} は現在のCOM一覧にありません。\nESP32をUSB接続してから「更新」を押してください。",
            )
            self.append_output(f"書き込み中止: {port} は現在検出されていません。")
            return False
        return True

    def _port_is_busy_for_upload(self) -> bool:
        port = self.current_port()
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "uses_port") and monitor.uses_port(port):
            QMessageBox.warning(self, "COMポート使用中", "シリアルタブがCOMポートを使用中です。先に切断してください。")
            return True
        status = self.host.serial.status()
        if status.connected and not status.mock and str(self.host.serial.port).upper() == port.upper():
            self.append_output("実機接続が同じCOMポートを使用中です。確認後、書き込み前に自動で切断します。")
        return False

    def _remember_settings(self) -> None:
        self.host.local_settings["last_upload_port"] = self.current_port()
        self.host.local_settings["last_upload_fqbn"] = self.current_fqbn()
        self.host.local_settings["last_upload_sketch"] = self.current_sketch()
        self.host._save_local_settings()

    def _maybe_set_port_from_board_list(self, text: str) -> None:
        preferred = self._find_esp32_like_port_from_text(text)
        if not preferred:
            self.append_output("ボード一覧からESP32候補を検出できませんでした。ESP32をUSB接続し直して更新してください。")
            return
        if self.port_combo.findData(preferred) < 0:
            self.port_combo.addItem(f"{preferred} - ボード一覧候補", preferred)
        self.port_combo.setCurrentIndex(self.port_combo.findData(preferred))
        self.port_hint_label.setText(f"ESP32候補: {preferred}")
        self.append_output(f"ESP32候補を選択しました: {preferred}")

    def _find_esp32_like_port_from_text(self, text: str) -> str:
        preferred = ""
        fallback = ""
        for line in text.splitlines():
            port = normalize_port_name(line)
            if not re.fullmatch(r"COM\d+", port):
                continue
            upper = line.upper()
            lower = line.lower()
            if any(keyword in lower for keyword in ["bluetooth", "bthenum", "active management", "intel"]):
                continue
            if port == "COM10":
                preferred = port
            if any(keyword in upper for keyword in ["ESP32", "CP210", "CH340", "CH910", "USB SERIAL", "USB TO UART", "SILICON LABS", "WCH"]):
                fallback = port
        return preferred or fallback

    def _append_upload_failure_hint(self, result: ArduinoCliResult) -> None:
        text = f"{result.stdout}\n{result.stderr}".lower()
        hints = []
        if "access is denied" in text or "permission" in text or "busy" in text:
            hints.append("COMポートが使用中です。Arduino IDE、シリアルタブ、実機接続を閉じてください。")
        if "no serial port" in text or "not found" in text or "cannot open" in text:
            hints.append("ESP32が見つかりません。USBケーブル、COM番号、ドライバを確認してください。")
        if "timed out" in text or "failed to connect" in text:
            hints.append("ESP32のBOOTボタンを押しながら書き込み開始を試してください。")
        if hints:
            self.append_output("対処ヒント:")
            for hint in hints:
                self.append_output(f"- {hint}")


def create_arduino_ide_tab(host) -> QWidget:
    widget = ArduinoIdeWidget(host)
    host.arduino_ide_widget = widget
    return widget
