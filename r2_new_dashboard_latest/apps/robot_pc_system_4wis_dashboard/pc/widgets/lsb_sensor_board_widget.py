from __future__ import annotations

import time
from typing import Any

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from ..sensors import is_sensor_active
except ImportError:
    from sensors import is_sensor_active

from .ui_helpers import boxed, make_button, make_notice, set_monospace, set_section_title


LSB_LINE_PREFIXES = (
    "LSB,",
    "BOOT,LSB",
    "FW,lsb_sensor_node",
)


class LsbSensorBoardWidget(QWidget):
    def __init__(self, host: Any | None = None) -> None:
        super().__init__()
        self.host = host
        self.value_labels: dict[str, QLabel] = {}
        self.last_lsb_line_time = 0.0
        self.manual_status_until = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("LSB基板")
        set_section_title(title)
        root.addWidget(title)
        root.addWidget(
            make_notice(
                "LSB表示: LSB,SENSを受信して反映 / センサ値取得専用 / モータ・アクチュエータ出力なし"
            )
        )

        main = QHBoxLayout()
        main.setSpacing(12)
        main.addWidget(self._build_sensor_value_box(), 4)

        side = QWidget()
        side.setMinimumWidth(500)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        side_layout.addWidget(self._build_connection_box())
        side_layout.addWidget(self._build_command_box())
        side_layout.addWidget(self._build_parameter_box())
        side_layout.addWidget(self._build_pinout_box())
        side_layout.addWidget(self._build_log_box())
        side_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(520)
        scroll.setWidget(side)
        main.addWidget(scroll, 3)
        root.addLayout(main, 1)

    def _build_sensor_value_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._grid_box("基板状態", ["LSB状態", "基板ID", "FW", "seq", "I2C", "最終受信", "エラー"], columns=2))
        upper = QHBoxLayout()
        upper.setSpacing(8)
        upper.addWidget(self._grid_box("ToF", ["前", "右", "後", "左"], columns=2), 1)
        upper.addWidget(self._grid_box("IMU", ["yaw", "pitch", "roll"], columns=1), 1)
        layout.addLayout(upper)
        layout.addWidget(
            self._grid_box(
                "超音波",
                ["前L", "前R", "右F", "右R", "後R", "後L", "左R", "左F"],
                columns=4,
            )
        )
        layout.addStretch(1)
        return boxed("LSBセンサ値", panel)

    def _grid_box(self, title: str, rows: list[str], columns: int = 1) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        columns = max(1, int(columns))
        for index, name in enumerate(rows):
            row = index // columns
            column = (index % columns) * 2
            name_label = QLabel(name)
            name_label.setObjectName("cardLabel")
            name_label.setMinimumWidth(44)
            value_label = QLabel("-")
            value_label.setObjectName("diagnosticLabel")
            value_label.setStyleSheet("color:#f8fafc; font-size:15px; font-weight:800;")
            value_label.setWordWrap(True)
            grid.addWidget(name_label, row, column)
            grid.addWidget(value_label, row, column + 1)
            self.value_labels[name] = value_label
        for index in range(columns):
            grid.setColumnStretch(index * 2, 0)
            grid.setColumnStretch(index * 2 + 1, 1)
        return boxed(title, panel)

    def _build_connection_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.connection_status_label = QLabel("LSB接続: 未接続")
        self.connection_status_label.setObjectName("diagnosticLabel")
        self.connection_status_label.setWordWrap(True)
        layout.addWidget(self.connection_status_label)
        hint = QLabel("COMが開けない時は、Arduino Serial Monitor、シリアルタブ、他の書き込み処理が同じCOMを使用中の可能性があります。")
        hint.setObjectName("diagnosticLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row1 = QHBoxLayout()
        row1.addWidget(make_button("COM更新", self._refresh_ports, 36), 1)
        row1.addWidget(make_button("COM解放", self._cleanup_serial, 36), 1)
        row1.addWidget(make_button("ESP32接続", self._connect_esp32, 36), 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(make_button("ESP32切断", self._disconnect_esp32, 40), 1)
        row2.addWidget(make_button("LSBスケッチを書き込む", self._upload_lsb_sketch, 40), 2)
        row2.addWidget(make_button("シリアルへ移動", self._open_serial_tab, 40), 1)
        layout.addLayout(row2)

        return boxed("LSB 接続 / 書き込み", panel)

    def _build_command_box(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        commands = ["PING", "ID?", "I2C?", "SENS?", "STREAM ON", "STREAM OFF"]
        for index, command in enumerate(commands):
            button = QPushButton(command)
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, text=command: self._send_command(text))
            layout.addWidget(button, index // 2, index % 2)
        return boxed("LSB コマンド", panel)

    def _build_parameter_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.parameter_status_label = QLabel("周期: 未確認 / Stream: 未確認 / ToF: 未確認")
        self.parameter_status_label.setObjectName("diagnosticLabel")
        self.parameter_status_label.setWordWrap(True)
        layout.addWidget(self.parameter_status_label)

        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("送信周期"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(100, 2000)
        self.rate_spin.setSingleStep(50)
        self.rate_spin.setValue(100)
        self.rate_spin.setSuffix(" ms")
        self.rate_spin.setMinimumHeight(34)
        rate_row.addWidget(self.rate_spin, 1)
        rate_row.addWidget(make_button("適用", self._apply_rate, 34), 1)
        rate_row.addWidget(make_button("読込", self._read_rate, 34), 1)
        layout.addLayout(rate_row)

        stream_row = QHBoxLayout()
        stream_row.addWidget(make_button("100ms高速", self._apply_fast_rate, 36), 1)
        stream_row.addWidget(make_button("250ms安定", self._apply_stable_rate, 36), 1)
        stream_row.addWidget(make_button("Stream ON", lambda: self._send_command("STREAM ON"), 36), 1)
        stream_row.addWidget(make_button("Stream OFF", lambda: self._send_command("STREAM OFF"), 36), 1)
        layout.addLayout(stream_row)

        read_row = QHBoxLayout()
        read_row.addWidget(make_button("ToF確認", lambda: self._send_command("TOF?"), 36), 1)
        read_row.addWidget(make_button("センサ単発取得", lambda: self._send_command("SENS?"), 36), 1)
        read_row.addWidget(make_button("ID/I2C読込", self._read_identity_and_i2c, 36), 1)
        layout.addLayout(read_row)

        return boxed("LSB パラメータ", panel)

    def _build_pinout_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        rows = [
            "ToF J1-J4: 1=3V3 / 2=GND / 3=SDA / 4=SCL / 5=XSHUT / 6=INT",
            "超音波 J5-J12: 1=3V3 / 2=GND / 3=SIG",
            "J5 FRONT_L / J6 FRONT_R / J7 RIGHT_F / J8 RIGHT_R / J9 REAR_R / J10 REAR_L / J11 LEFT_R / J12 LEFT_F",
            "J13 IMU / J14,J19 外部5V / J15 光学式 / J16,J17 I2C / J18 予備GPIO",
        ]
        for text in rows:
            label = QLabel(text)
            label.setObjectName("diagnosticLabel")
            label.setWordWrap(True)
            layout.addWidget(label)
        return boxed("LSB ピン配列", panel)

    def _build_log_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.lsb_log_view = QPlainTextEdit()
        self.lsb_log_view.setReadOnly(True)
        self.lsb_log_view.setMaximumBlockCount(120)
        self.lsb_log_view.setPlaceholderText("LSB,ID / LSB,SENS / LSB,ERR などを表示します。")
        set_monospace(self.lsb_log_view)
        layout.addWidget(self.lsb_log_view)
        return boxed("LSB 受信ログ", panel)

    def _refresh_ports(self) -> None:
        if self.host is not None and hasattr(self.host, "refresh_com_ports"):
            self.host.refresh_com_ports(log_result=True)
            self._set_connection_status("LSB接続: COMポートを更新しました", "info")

    def _connect_esp32(self) -> None:
        if self.host is not None and hasattr(self.host, "connect_esp32_from_ui"):
            self.host.connect_esp32_from_ui()
            status = self.host.serial.status() if hasattr(self.host, "serial") else None
            if status is not None and getattr(status, "connected", False) and not getattr(status, "mock", False):
                self._set_connection_status(f"LSB接続: ESP32接続中 {getattr(self.host.serial, 'port', '')}", "ok")
            else:
                message = str(getattr(status, "message", "") or "接続できません")
                self._set_connection_status(f"LSB接続失敗: {self._short_connection_error(message)}", "error")

    def _disconnect_esp32(self) -> None:
        if self.host is not None and hasattr(self.host, "disconnect_esp32_from_ui"):
            self.host.disconnect_esp32_from_ui()
            self._set_connection_status("LSB接続: ESP32切断を実行しました", "info")

    def _cleanup_serial(self) -> None:
        if self.host is None or not hasattr(self.host, "stop_other_serial_communications_for_upload"):
            self._set_connection_status("COM解放: 実行できません", "error")
            return
        try:
            messages = self.host.stop_other_serial_communications_for_upload(None)
        except Exception as exc:
            self._set_connection_status(f"COM解放失敗: {exc}", "error")
            return
        summary = " / ".join(messages) if messages else "停止対象なし"
        self._append_log("COM解放: " + summary)
        self._set_connection_status("COM解放: " + summary, "ok")

    def _upload_lsb_sketch(self) -> None:
        if self.host is None:
            return
        arduino_ide = getattr(self.host, "arduino_ide_widget", None)
        if arduino_ide is None or not hasattr(arduino_ide, "easy_upload_sketch"):
            self._set_connection_status("LSB書き込み: 書き込みタブが未初期化です", "error")
            return
        if hasattr(self.host, "stop_other_serial_communications_for_upload"):
            try:
                self.host.stop_other_serial_communications_for_upload(None)
            except Exception as exc:
                self._append_log(f"COM解放警告: {exc}")
        if hasattr(self.host, "switch_to_tab"):
            self.host.switch_to_tab("書き込み")
        self._set_connection_status("LSB書き込み: lsb_sensor_node を準備中", "busy")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation("LSB基板テストを書き込みます", "busy")
        arduino_ide.easy_upload_sketch("lsb_sensor_node")

    def _open_serial_tab(self) -> None:
        if self.host is None:
            return
        if hasattr(self.host, "switch_to_tab"):
            self.host.switch_to_tab("シリアル")
        monitor = getattr(self.host, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "prepare_for_immediate_start"):
            monitor.prepare_for_immediate_start(auto_connect=False)
        self._set_connection_status("シリアルタブへ移動しました。接続前にCOM使用中でないか確認してください。", "info")

    def _send_command(self, command: str) -> None:
        if self.host is None or not hasattr(self.host, "_send_esp32_line"):
            self._set_connection_status(f"LSB送信失敗: {command}", "error")
            return
        if self.host._send_esp32_line(command, f"LSB {command}"):
            self._append_log(f"TX {command}")
            self._set_connection_status(f"LSB送信: {command}", "ok")
        else:
            self._set_connection_status(f"LSB送信失敗: {command}", "error")

    def _apply_rate(self) -> None:
        self._send_command(f"RATE {self.rate_spin.value()}")

    def _read_rate(self) -> None:
        self._send_command("RATE?")

    def _apply_fast_rate(self) -> None:
        self.rate_spin.setValue(100)
        self._apply_rate()

    def _apply_stable_rate(self) -> None:
        self.rate_spin.setValue(250)
        self._apply_rate()

    def _read_identity_and_i2c(self) -> None:
        self._send_command("ID?")
        self._send_command("I2C?")

    def append_serial_line(self, line: str, source: str = "ESP32") -> None:
        if not self._is_lsb_line(line):
            return
        self.last_lsb_line_time = time.monotonic()
        self._append_log(f"{source}: {line}")
        self._update_parameters_from_line(line)
        if line.startswith("LSB,ERR"):
            self._set_connection_status("LSB接続: エラー受信", "error")
        elif line.startswith(("LSB,SENS", "LSB,ID", "LSB,PONG", "LSB,RATE", "LSB,TOF", "BOOT,LSB", "FW,lsb_sensor_node")):
            self._set_connection_status("LSB接続: 受信中", "ok")

    def _update_parameters_from_line(self, line: str) -> None:
        text = line.strip()
        if text.startswith("LSB,RATE,"):
            parts = text.split(",")
            if len(parts) >= 3:
                try:
                    interval = int(float(parts[2]))
                except ValueError:
                    interval = 0
                if interval > 0:
                    self.rate_spin.blockSignals(True)
                    self.rate_spin.setValue(max(self.rate_spin.minimum(), min(self.rate_spin.maximum(), interval)))
                    self.rate_spin.blockSignals(False)
                    self._set_parameter_status(f"周期: {interval} ms / Stream: - / ToF: -")
            return
        if text.startswith("LSB,STATUS,STREAM,"):
            parts = text.split(",")
            state = parts[3] if len(parts) >= 4 else "OK"
            self._set_parameter_status(f"周期: {self.rate_spin.value()} ms / Stream: {state} / ToF: -")
            return
        if text.startswith("LSB,TOF,"):
            parts = text.split(",")
            status = "OK" if len(parts) >= 4 and parts[3].upper() == "OK" else "NG"
            dist = "-"
            ready = "-"
            tof_type = "-"
            for part in parts[4:]:
                if part.startswith("DIST_MM="):
                    dist = part.split("=", 1)[1]
                elif part.startswith("READY="):
                    ready = part.split("=", 1)[1]
                elif part.startswith("TYPE="):
                    tof_type = part.split("=", 1)[1]
            self._set_parameter_status(
                f"周期: {self.rate_spin.value()} ms / Stream: - / ToF: {status} {tof_type} ready={ready} dist={dist} mm"
            )

    def _set_parameter_status(self, text: str) -> None:
        if hasattr(self, "parameter_status_label"):
            self.parameter_status_label.setText(text)

    def update_values(self, data: Any, esp32_status: Any, show_values: bool) -> None:
        connected = bool(getattr(esp32_status, "connected", False) and not getattr(esp32_status, "mock", False))
        status_message = str(getattr(esp32_status, "message", "") or "")
        lsb_status = str(getattr(data, "lsb_status", "未接続"))
        active = bool(show_values and is_sensor_active(lsb_status))
        self._set_label("LSB状態", "接続中" if active else "未接続")
        self._set_label("基板ID", str(getattr(data, "lsb_board_id", "未接続") if active else "未接続"))
        self._set_label("FW", str(getattr(data, "lsb_fw_version", "") if active else "-") or "-")
        self._set_label("seq", str(getattr(data, "lsb_seq", 0) if active else 0))
        self._set_label("I2C", str(getattr(data, "lsb_i2c_summary", "未受信") if active else "未受信"))
        self._set_label("エラー", str(getattr(data, "lsb_error", "") or "-"))

        for key, attr in [
            ("前", "lsb_tof_front_mm"),
            ("右", "lsb_tof_right_mm"),
            ("後", "lsb_tof_rear_mm"),
            ("左", "lsb_tof_left_mm"),
            ("前L", "lsb_us_front_l_mm"),
            ("前R", "lsb_us_front_r_mm"),
            ("右F", "lsb_us_right_f_mm"),
            ("右R", "lsb_us_right_r_mm"),
            ("後R", "lsb_us_rear_r_mm"),
            ("後L", "lsb_us_rear_l_mm"),
            ("左R", "lsb_us_left_r_mm"),
            ("左F", "lsb_us_left_f_mm"),
        ]:
            value = float(getattr(data, attr, 0.0)) if active else 0.0
            self._set_label(key, f"{value:.0f} mm")

        imu_active = active and is_sensor_active(str(getattr(data, "imu_status", "未接続")))
        self._set_label("yaw", f"{float(getattr(data, 'imu_yaw', 0.0)):.1f} deg" if imu_active else "0.0 deg")
        self._set_label("pitch", f"{float(getattr(data, 'imu_pitch', 0.0)):.1f} deg" if imu_active else "0.0 deg")
        self._set_label("roll", f"{float(getattr(data, 'imu_roll', 0.0)):.1f} deg" if imu_active else "0.0 deg")

        age_text = "未受信"
        if self.last_lsb_line_time > 0:
            age_text = f"{max(0.0, time.monotonic() - self.last_lsb_line_time):.1f}秒前"
        self._set_label("最終受信", age_text)
        if time.monotonic() < self.manual_status_until:
            return
        if active:
            self._set_connection_status("LSB接続: 受信中", "ok")
        elif connected:
            self._set_connection_status("LSB接続: ESP32接続中 / LSBデータ未受信", "warn")
        elif "PermissionError" in status_message or "アクセスが拒否" in status_message:
            self._set_connection_status("LSB接続: COM使用中の可能性があります。COM解放またはUSB抜き差し後にCOM更新してください。", "error")

    def _set_label(self, name: str, text: str) -> None:
        label = self.value_labels.get(name)
        if label is not None:
            label.setText(text)

    def _set_connection_status(self, text: str, level: str = "info") -> None:
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "busy": "#dbeafe",
            "info": "#cbd5e1",
        }
        self.connection_status_label.setText(text)
        self.connection_status_label.setStyleSheet(f"color:{colors.get(level, '#cbd5e1')}; font-weight:700;")
        self.manual_status_until = time.monotonic() + 4.0 if level in {"busy", "info", "ok", "error"} else 0.0

    def set_connection_problem(self, text: str) -> None:
        self._set_connection_status(f"LSB接続失敗: {self._short_connection_error(text)}", "error")

    @staticmethod
    def _short_connection_error(text: str) -> str:
        if "PermissionError" in text or "アクセスが拒否" in text:
            return "COM使用中の可能性があります。COM解放、Arduino Serial Monitor終了、USB抜き差しを試してください。"
        return text[:180] if text else "詳細なし"

    def _append_log(self, text: str) -> None:
        self.lsb_log_view.appendPlainText(text)

    @staticmethod
    def _is_lsb_line(line: str) -> bool:
        return bool(line and line.startswith(LSB_LINE_PREFIXES))


def create_lsb_sensor_board_tab(host) -> QWidget:
    widget = LsbSensorBoardWidget(host)
    host.lsb_sensor_board_widget = widget
    return widget
