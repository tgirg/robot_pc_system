from __future__ import annotations

import re
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QTextCursor
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

from .ui_feedback import clear_busy, set_busy, show_error, show_info, show_success
from .ui_helpers import boxed, make_button, make_notice
from arduino_tools import choose_esp32_port, is_non_esp_port, normalize_port_name


BAUDRATES = ["9600", "57600", "115200", "230400", "921600"]
NEWLINES = {"なし": "", "LF": "\n", "CRLF": "\r\n"}


class SerialMonitorWidget(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.conn: serial.Serial | None = None
        self.receiving = False
        self.raw_text = ""

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(220)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(BAUDRATES)
        self.baud_combo.setCurrentText("115200")
        self.status_label = QLabel("状態: 未接続")
        self.status_label.setObjectName("diagnosticLabel")
        self.auto_scroll_checkbox = QCheckBox("自動スクロール")
        self.auto_scroll_checkbox.setChecked(True)
        self.reset_on_connect_checkbox = QCheckBox("接続時にESP32をリセット")
        self.reset_on_connect_checkbox.setChecked(True)
        self.address_label = QLabel("検出されたI2Cアドレス: 未検出")
        self.address_label.setObjectName("diagnosticLabel")
        self.firmware_label = QLabel("ファームウェア: 未確認")
        self.firmware_label.setObjectName("diagnosticLabel")
        self.imu_i2c_status_label = QLabel("I2C認識: 未確認")
        self.imu_i2c_status_label.setObjectName("diagnosticLabel")
        self.boot_check_label = QLabel("動作確認: 待機中")
        self.boot_check_label.setObjectName("diagnosticLabel")
        self.imu_detail_label = QLabel("IMU種別: 未確認 / IMUアドレス: 未確認")
        self.imu_detail_label.setObjectName("diagnosticLabel")
        self.sensor_status_labels: dict[str, QLabel] = {}
        for key, title in [
            ("IMU_STATUS", "IMU状態"),
            ("LIDAR_STATUS", "LiDAR状態"),
            ("ENC_STATUS", "エンコーダ状態"),
            ("ODOM_STATUS", "オドメトリ状態"),
            ("DIST_STATUS", "距離センサ状態"),
            ("LINE_STATUS", "ライン状態"),
            ("COLOR_STATUS", "カラー状態"),
        ]:
            label = QLabel(f"{title}: 未確認")
            label.setObjectName("diagnosticLabel")
            self.sensor_status_labels[key] = label
        self.operation_label = QLabel("状態: 待機中")
        self.operation_label.setObjectName("diagnosticLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setMinimumHeight(300)
        self.log_view.setMaximumBlockCount(5000)
        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("送信する文字列を入力します。例: DRIVE STOP")
        self.newline_combo = QComboBox()
        self.newline_combo.addItems(list(NEWLINES.keys()))
        self.newline_combo.setCurrentText("LF")
        self.refresh_button = make_button("COM更新", self.refresh_ports)
        self.connect_button = make_button("接続", self.connect_monitor)
        self.disconnect_button = make_button("切断", self.disconnect_monitor)
        self.receive_start_button = make_button("受信開始", self.start_receive)
        self.receive_stop_button = make_button("受信停止", self.stop_receive)
        self.clear_button = make_button("ログ消去", self.clear_log)
        self.copy_button = make_button("ログコピー", self.copy_log)
        self.save_button = make_button("ログ保存", self.save_log)
        self.reset_button = make_button("ESP32リセット", self.reset_esp32)
        self.replay_button = make_button("ログ再生", self.replay_saved_log)
        self.send_button = make_button("送信", self.send_text)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_serial)

        self._build()
        self.refresh_ports(log=False)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(make_notice("この画面は直接シリアル通信を行います。モータ接続時は送信コマンドに注意してください。"))

        top = QWidget()
        top_layout = QGridLayout(top)
        top_layout.addWidget(QLabel("COMポート選択"), 0, 0)
        top_layout.addWidget(self.port_combo, 0, 1)
        top_layout.addWidget(QLabel("ボーレート選択"), 0, 2)
        top_layout.addWidget(self.baud_combo, 0, 3)
        top_layout.addWidget(self.status_label, 1, 0, 1, 4)
        top_layout.addWidget(self.operation_label, 2, 0, 1, 4)
        top_layout.addWidget(self.progress, 3, 0, 1, 4)
        top_layout.setColumnStretch(1, 1)
        layout.addWidget(top)

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        for button in [
            self.refresh_button,
            self.connect_button,
            self.disconnect_button,
            self.receive_start_button,
            self.receive_stop_button,
            self.clear_button,
            self.copy_button,
            self.save_button,
            self.replay_button,
            self.reset_button,
        ]:
            button_layout.addWidget(button)
        button_layout.addWidget(self.auto_scroll_checkbox)
        button_layout.addWidget(self.reset_on_connect_checkbox)
        button_layout.addStretch(1)
        layout.addWidget(buttons)

        send_row = QWidget()
        send_layout = QHBoxLayout(send_row)
        send_layout.addWidget(QLabel("送信欄"))
        send_layout.addWidget(self.send_edit, 1)
        send_layout.addWidget(QLabel("改行設定"))
        send_layout.addWidget(self.newline_combo)
        send_layout.addWidget(self.send_button)
        layout.addWidget(send_row)

        layout.addWidget(self._guide_box())
        layout.addWidget(self._expected_output_box())
        layout.addWidget(self.firmware_label)
        layout.addWidget(self.address_label)
        layout.addWidget(self.imu_i2c_status_label)
        layout.addWidget(self.boot_check_label)
        layout.addWidget(self.imu_detail_label)
        status_grid = QGridLayout()
        for index, label in enumerate(self.sensor_status_labels.values()):
            status_grid.addWidget(label, index // 2, index % 2)
        layout.addLayout(status_grid)
        layout.addWidget(boxed("Rawログ", self.log_view), 1)

    def _guide_box(self) -> QWidget:
        guide = QLabel(
            "I2Cスキャナ確認:\n"
            "1. ESP32プログラム編集で I2Cスキャナテンプレートを挿入\n"
            "2. コンパイル\n"
            "3. ESP32へ書き込み\n"
            "4. シリアルモニタを115200bpsで接続\n"
            "5. 0x68 / 0x69 / 0x28 などが表示されるか確認"
        )
        guide.setWordWrap(True)
        guide.setObjectName("diagnosticLabel")
        return boxed("I2Cスキャナ確認", guide)

    def _expected_output_box(self) -> QWidget:
        guide = QLabel(
            "9軸IMUテスト成功例:\n"
            "BOOT,IMU_9AXIS_TEST_READY\n"
            "I2C scan start\n"
            "I2C device found at 0x68\n"
            "I2C scan done\n"
            "IMU_STATUS,OK\n"
            "IMU,...\n"
            "GYRO,...\n"
            "STATUS,OK\n\n"
            "I2Cアドレスが出ない場合: 配線、SDA/SCL、3.3V、GNDを確認してください。"
        )
        guide.setWordWrap(True)
        guide.setObjectName("diagnosticLabel")
        return boxed("9軸IMUテスト成功例", guide)

    def refresh_ports(self, log: bool = True) -> None:
        show_info(self.operation_label, "COMポート更新中...")
        current = self.current_port()
        self.port_combo.clear()
        ports = list(list_ports.comports())
        port_by_name = {normalize_port_name(port.device): port for port in ports}
        for port in ports:
            label = f"{port.device} - {port.description}"
            self.port_combo.addItem(label, port.device)
        if not ports:
            fallback = current or getattr(self.host.serial, "port", "") or "COM10"
            self.port_combo.addItem(fallback, fallback)
        if self.port_combo.findData("COM10") < 0:
            self.port_combo.addItem("COM10 - 手入力候補（ESP32）", "COM10")
        preferred = choose_esp32_port(
            ports,
            [
                str(getattr(self.host, "local_settings", {}).get("last_com_port", "") if hasattr(self.host, "local_settings") else ""),
                str(getattr(self.host, "local_settings", {}).get("last_upload_port", "") if hasattr(self.host, "local_settings") else ""),
                current,
                str(getattr(self.host.serial, "port", "") or ""),
            ],
        )
        preferred_index = self.port_combo.findData(preferred)
        if preferred_index >= 0 and preferred in port_by_name:
            self.port_combo.setCurrentIndex(preferred_index)
        elif preferred_index >= 0 and not ports:
            self.port_combo.setCurrentIndex(preferred_index)
        elif preferred_index >= 0 and preferred == "COM10" and "COM10" in port_by_name:
            self.port_combo.setCurrentIndex(preferred_index)
        elif current:
            index = self.port_combo.findData(current)
            info = port_by_name.get(normalize_port_name(current))
            if index >= 0 and info is not None and not is_non_esp_port(info):
                self.port_combo.setCurrentIndex(index)
            else:
                com10_index = self.port_combo.findData("COM10")
                if com10_index >= 0:
                    self.port_combo.setCurrentIndex(com10_index)
        if log:
            self.append_log("COMポートを更新しました。")
            show_success(self.operation_label, f"COMポート更新完了（{len(ports)}件）")
        else:
            show_info(self.operation_label, "待機中")

    def connect_monitor(self) -> None:
        port = self.current_port()
        self.progress.show()
        set_busy(self.connect_button, "接続中...")
        show_info(self.operation_label, f"{port or '-'} へ接続中...")
        if not port:
            self.progress.hide()
            clear_busy(self.connect_button)
            show_error(self.operation_label, "COMポート未選択")
            QMessageBox.warning(self, "COMポート未選択", "COMポートを選択してください。")
            return
        if not self._handle_normal_connection_conflict(port):
            self.progress.hide()
            clear_busy(self.connect_button)
            show_info(self.operation_label, "接続をキャンセルしました")
            return
        if self.is_connected():
            self.disconnect_monitor()
        try:
            self.conn = serial.Serial(port, int(self.baud_combo.currentText()), timeout=0.02, write_timeout=0.2)
        except serial.SerialException as exc:
            self.progress.hide()
            clear_busy(self.connect_button)
            show_error(self.operation_label, "接続失敗")
            self.status_label.setText(f"状態: 接続失敗（{exc}）")
            self.append_log(f"接続失敗: {exc}")
            if hasattr(self.host, "notify_operation"):
                self.host.notify_operation(f"シリアルモニタ接続失敗: {exc}", "error")
            return
        self.status_label.setText(f"状態: 接続中 {port} / {self.baud_combo.currentText()} bps")
        self.append_log(f"接続しました: {port} / {self.baud_combo.currentText()} bps")
        self.progress.hide()
        clear_busy(self.connect_button)
        show_success(self.operation_label, "接続完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"シリアルモニタ接続: {port}", "success")
        if self.reset_on_connect_checkbox.isChecked():
            self.reset_esp32()
        self.start_receive()

    def disconnect_monitor(self) -> None:
        show_info(self.operation_label, "切断中...")
        self.stop_receive()
        if self.conn is not None:
            try:
                self.conn.close()
            except serial.SerialException as exc:
                self.append_log(f"切断エラー: {exc}")
            finally:
                self.conn = None
        self.status_label.setText("状態: 未接続")
        self.append_log("切断しました。")
        show_success(self.operation_label, "切断完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation("シリアルモニタを切断しました", "info")

    def start_receive(self) -> None:
        if not self.is_connected():
            show_error(self.operation_label, "未接続です")
            QMessageBox.warning(self, "未接続", "先にシリアルモニタを接続してください。")
            return
        self.receiving = True
        if not self.timer.isActive():
            self.timer.start(50)
        self.append_log("受信開始")
        show_success(self.operation_label, "受信中")

    def stop_receive(self) -> None:
        self.receiving = False
        if self.timer.isActive():
            self.timer.stop()
        show_info(self.operation_label, "受信停止")

    def poll_serial(self) -> None:
        if not self.receiving or self.conn is None:
            return
        try:
            waiting = self.conn.in_waiting
            if waiting <= 0:
                return
            data = self.conn.read(waiting)
        except (OSError, serial.SerialException) as exc:
            self.append_log(f"受信エラー: {exc}")
            self.disconnect_monitor()
            return
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        self.raw_text += text
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertPlainText(text)
        if hasattr(self.host, "handle_external_serial_text"):
            self.host.handle_external_serial_text(text, source="シリアルモニタ")
        self._update_i2c_addresses()
        if self.auto_scroll_checkbox.isChecked():
            bar = self.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())

    def send_text(self) -> None:
        if not self.is_connected() or self.conn is None:
            show_error(self.operation_label, "未接続です")
            QMessageBox.warning(self, "未接続", "先にシリアルモニタを接続してください。")
            return
        text = self.send_edit.text()
        newline = NEWLINES.get(self.newline_combo.currentText(), "\n")
        try:
            self.conn.write((text + newline).encode("utf-8"))
        except serial.SerialException as exc:
            show_error(self.operation_label, "送信失敗")
            self.append_log(f"送信エラー: {exc}")
            return
        self.append_log(f"> {text}")
        show_success(self.operation_label, "送信完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"シリアル送信: {text}", "success")

    def reset_esp32(self) -> None:
        if not self.is_connected() or self.conn is None:
            show_error(self.operation_label, "未接続です")
            QMessageBox.warning(self, "未接続", "先にシリアルモニタを接続してください。")
            return
        self.progress.show()
        set_busy(self.reset_button, "リセット中...")
        show_info(self.operation_label, "ESP32リセット中...")
        try:
            self.conn.setDTR(False)
            self.conn.setRTS(True)
            time.sleep(0.08)
            self.conn.setRTS(False)
            self.conn.setDTR(True)
            time.sleep(0.08)
            self.conn.reset_input_buffer()
        except (OSError, serial.SerialException) as exc:
            self.progress.hide()
            clear_busy(self.reset_button)
            show_error(self.operation_label, "ESP32リセット失敗")
            self.append_log(f"ESP32リセット失敗: {exc}")
            return
        self.progress.hide()
        clear_busy(self.reset_button)
        self.append_log("ESP32リセットを実行しました。起動ログを待っています。")
        show_success(self.operation_label, "ESP32リセット完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation("ESP32リセットを実行しました", "success")

    def clear_log(self) -> None:
        self.raw_text = ""
        self.log_view.clear()
        self._update_i2c_addresses()
        self._update_serial_status_summary()
        show_info(self.operation_label, "ログを消去しました")

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.append_log("ログをクリップボードへコピーしました。")
        show_success(self.operation_label, "ログコピー完了")

    def save_log(self) -> None:
        self.progress.show()
        set_busy(self.save_button, "保存中...")
        show_info(self.operation_label, "ログ保存中...")
        try:
            log_dir = self.host._project_root() / "logs" / "serial_monitor"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = log_dir / f"serial_monitor_{timestamp}.txt"
            latest = log_dir / "latest_serial_monitor.txt"
            content = self._log_file_content()
            path.write_text(content, encoding="utf-8")
            latest.write_text(content, encoding="utf-8")
        except OSError as exc:
            self.progress.hide()
            clear_busy(self.save_button)
            show_error(self.operation_label, "ログ保存失敗")
            QMessageBox.warning(self, "保存失敗", f"ログ保存に失敗しました。\n{exc}")
            return
        self.progress.hide()
        clear_busy(self.save_button)
        self.append_log(f"ログ保存: {path}")
        show_success(self.operation_label, "ログ保存完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"シリアルモニタログを保存しました: {path.name}", "success")

    def replay_saved_log(self) -> None:
        start_dir = self.host._project_root() / "logs" / "serial_monitor"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "センサログを再生",
            str(start_dir),
            "テキストファイル (*.txt *.log);;すべてのファイル (*)",
        )
        if not path:
            return
        if hasattr(self.host, "start_sensor_log_replay"):
            self.host.start_sensor_log_replay(Path(path))
            show_success(self.operation_label, "センサログ再生を開始しました")
        else:
            show_error(self.operation_label, "ログ再生機能が見つかりません")

    def current_port(self) -> str:
        data = self.port_combo.currentData()
        if data:
            return str(data)
        return self.port_combo.currentText().split(" - ")[0].strip()

    def set_port_and_baud(self, port: str, baudrate: int = 115200) -> None:
        if port:
            index = self.port_combo.findData(port)
            if index < 0:
                self.port_combo.addItem(port, port)
                index = self.port_combo.findData(port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        self.baud_combo.setCurrentText(str(baudrate))
        show_info(self.operation_label, "COMポートとボーレートを設定しました。シリアルタブ表示時に接続を開始します。")

    def prepare_for_immediate_start(self, auto_connect: bool = True) -> None:
        self.refresh_ports(log=False)
        self.baud_combo.setCurrentText("115200")
        self.reset_on_connect_checkbox.setChecked(True)
        port = self.current_port()
        if not port:
            show_error(self.operation_label, "COMポートが見つかりません。ESP32をUSB接続してください。")
            return

        if self.is_connected():
            if not self.receiving:
                self.start_receive()
            show_success(self.operation_label, f"{port} は接続済みです。受信できます。")
            return

        status = self.host.serial.status()
        if status.connected and not status.mock and str(self.host.serial.port).upper() == str(port).upper():
            message = "実機接続が同じCOMポートを使用中です。シリアルを使うには実機接続を切断してください。"
            show_error(self.operation_label, message)
            self.append_log(message)
            return

        show_info(self.operation_label, f"{port} / 115200 bps を選択しました。接続を開始します。")
        if auto_connect:
            QTimer.singleShot(0, self.connect_monitor)

    def is_connected(self) -> bool:
        return bool(self.conn and self.conn.is_open)

    def uses_port(self, port: str | None = None) -> bool:
        if not self.is_connected():
            return False
        if port is None:
            return True
        return self.current_port().upper() == str(port).upper()

    def append_log(self, text: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {text}\n"
        self.raw_text += line
        self.log_view.appendPlainText(line.rstrip("\n"))
        if self.auto_scroll_checkbox.isChecked():
            bar = self.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _handle_normal_connection_conflict(self, port: str) -> bool:
        status = self.host.serial.status()
        if not (status.connected and not status.mock and str(self.host.serial.port).upper() == str(port).upper()):
            return True
        box = QMessageBox(self)
        box.setWindowTitle("COMポート使用中")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("現在、実機接続でCOMポートを使用中です。\nシリアルモニタで使用するには、実機接続を切断してください。")
        disconnect_button = box.addButton("実機接続を切断してシリアルモニタを開く", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() != disconnect_button:
            return False
        self.host.disconnect_esp32_from_ui()
        return True

    def _update_i2c_addresses(self) -> None:
        matches = sorted(set(re.findall(r"I2C device found at 0x([0-9A-Fa-f]{2})", self.log_view.toPlainText())))
        if matches:
            self.address_label.setText("検出されたI2Cアドレス: " + ", ".join(f"0x{item.upper()}" for item in matches))
            self.imu_i2c_status_label.setText(f"I2C認識: OK（0x{matches[0].upper()}）")
            self.imu_i2c_status_label.setStyleSheet("color:#86efac; font-weight:700;")
        else:
            self.address_label.setText("検出されたI2Cアドレス: 未検出")
            self.imu_i2c_status_label.setText("I2C認識: 未検出")
            self.imu_i2c_status_label.setStyleSheet("color:#fef08a; font-weight:700;")
        self._update_serial_status_summary()

    def _update_serial_status_summary(self) -> None:
        text = self.log_view.toPlainText()
        if re.search(r"^BOOT,", text, flags=re.MULTILINE) and re.search(r"^STATUS,OK", text, flags=re.MULTILINE):
            self.boot_check_label.setText("動作確認: OK（BOOT / STATUS,OK）")
            self.boot_check_label.setStyleSheet("color:#86efac; font-weight:700;")
        elif re.search(r"^BOOT,", text, flags=re.MULTILINE):
            self.boot_check_label.setText("動作確認: 起動ログ受信")
            self.boot_check_label.setStyleSheet("color:#fef08a; font-weight:700;")
        else:
            self.boot_check_label.setText("動作確認: 待機中")
            self.boot_check_label.setStyleSheet("color:#dbeafe; font-weight:700;")
        firmware_match = re.findall(r"^FW,([^,\r\n]+),([^,\r\n]+)", text, flags=re.MULTILINE)
        if firmware_match:
            name, version = firmware_match[-1]
            self.firmware_label.setText(f"ファームウェア: {name} {version}")
            self.firmware_label.setStyleSheet("color:#86efac; font-weight:700;")
        else:
            self.firmware_label.setText("ファームウェア: 未確認")
            self.firmware_label.setStyleSheet("color:#fef08a; font-weight:700;")

        type_match = re.findall(r"^IMU_TYPE,([^,\r\n]+)", text, flags=re.MULTILINE)
        addr_match = re.findall(r"^IMU_ADDR,(0x[0-9A-Fa-f]{2})", text, flags=re.MULTILINE)
        imu_type = type_match[-1].upper() if type_match else "未確認"
        imu_addr = addr_match[-1].upper() if addr_match else "未確認"
        self.imu_detail_label.setText(f"IMU種別: {imu_type} / IMUアドレス: {imu_addr}")
        self.imu_detail_label.setStyleSheet("color:#86efac; font-weight:700;" if type_match and imu_type != "NONE" else "color:#fef08a; font-weight:700;")

        titles = {
            "IMU_STATUS": "IMU状態",
            "LIDAR_STATUS": "LiDAR状態",
            "ENC_STATUS": "エンコーダ状態",
            "ODOM_STATUS": "オドメトリ状態",
            "DIST_STATUS": "距離センサ状態",
            "LINE_STATUS": "ライン状態",
            "COLOR_STATUS": "カラー状態",
        }
        for key, label in self.sensor_status_labels.items():
            matches = re.findall(rf"^{key},([^,\r\n]+)", text, flags=re.MULTILINE)
            if not matches:
                label.setText(f"{titles[key]}: 未確認")
                label.setStyleSheet("color:#fef08a; font-weight:700;")
                continue
            status = matches[-1].upper()
            label.setText(f"{titles[key]}: {status}")
            color = "#86efac" if status in {"OK", "DUMMY"} else "#fca5a5" if status == "ERROR" else "#dbeafe"
            label.setStyleSheet(f"color:{color}; font-weight:700;")

    def _log_file_content(self) -> str:
        return "\n".join(
            [
                f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"COM port: {self.current_port() or '-'}",
                f"baudrate: {self.baud_combo.currentText()}",
                "",
                "--- raw received text ---",
                self.log_view.toPlainText(),
                "",
            ]
        )


def create_serial_monitor_panel(host) -> QWidget:
    widget = SerialMonitorWidget(host)
    host.serial_monitor_widget = widget
    return boxed("シリアルモニタ", widget)
