from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from ..noise_eval import (
        DEFAULT_BAUDRATE,
        WHEEL_NAMES,
        format_result_text,
        run_combined_noise_test,
        run_motor_ramp_test,
        run_servo_sweep_test,
        send_stop_disarm,
    )
except ImportError:
    from noise_eval import (
        DEFAULT_BAUDRATE,
        WHEEL_NAMES,
        format_result_text,
        run_combined_noise_test,
        run_motor_ramp_test,
        run_servo_sweep_test,
        send_stop_disarm,
    )

from .ui_helpers import boxed, make_button, make_notice, set_monospace, set_section_title


class NoiseTestWorker(QThread):
    progress = Signal(str)
    result_ready = Signal(dict)
    error_ready = Signal(str)

    def __init__(
        self,
        *,
        mode: str,
        port: str,
        wheel: int,
        pwm: int,
        baudrate: int = DEFAULT_BAUDRATE,
        log_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.port = port
        self.wheel = wheel
        self.pwm = pwm
        self.baudrate = baudrate
        self.log_dir = log_dir
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True
        self.progress.emit("停止要求: 現在の測定を打ち切り、安全停止/DISARMへ移行します。")

    def _should_stop(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        try:
            if self.mode == "combined":
                result = run_combined_noise_test(
                    self.port,
                    self.wheel,
                    self.pwm,
                    baudrate=self.baudrate,
                    log_dir=self.log_dir,
                    progress=self.progress.emit,
                    should_stop=self._should_stop,
                )
            elif self.mode == "servo":
                result = run_servo_sweep_test(
                    self.port,
                    self.wheel,
                    baudrate=self.baudrate,
                    log_dir=self.log_dir,
                    progress=self.progress.emit,
                    should_stop=self._should_stop,
                )
            elif self.mode == "ramp":
                result = run_motor_ramp_test(
                    self.port,
                    self.wheel,
                    baudrate=self.baudrate,
                    log_dir=self.log_dir,
                    progress=self.progress.emit,
                    should_stop=self._should_stop,
                )
            elif self.mode == "stop-disarm":
                result = send_stop_disarm(
                    self.port,
                    self.wheel,
                    baudrate=self.baudrate,
                    log_dir=self.log_dir,
                    progress=self.progress.emit,
                )
            else:
                raise ValueError(f"unknown mode: {self.mode}")
            self.result_ready.emit(result)
        except Exception as exc:
            self.error_ready.emit(str(exc))


class NoiseTestWidget(QWidget):
    def __init__(self, host: Any | None = None) -> None:
        super().__init__()
        self.host = host
        self.worker: NoiseTestWorker | None = None
        self.log_dir = self._project_log_dir()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("エンコーダノイズ測定")
        set_section_title(title)
        root.addWidget(title)
        root.addWidget(
            make_notice(
                "v29 DEBUGで1輪ずつ低PWM測定します。判定は encoder_count / wheel_rpm / motor_pwm / "
                "servo_deg / fault_flags を使います。PWM出力だけでは合格にしません。"
            )
        )

        controls = QWidget()
        grid = QGridLayout(controls)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(180)
        grid.addWidget(QLabel("COM"), 0, 0)
        grid.addWidget(self.port_combo, 0, 1)
        grid.addWidget(make_button("更新", self.refresh_ports, height=34), 0, 2)

        self.wheel_combo = QComboBox()
        for index, name in enumerate(WHEEL_NAMES):
            self.wheel_combo.addItem(f"{name} ({index})", index)
        self.wheel_combo.setCurrentIndex(1)
        grid.addWidget(QLabel("対象輪"), 1, 0)
        grid.addWidget(self.wheel_combo, 1, 1, 1, 2)

        self.pwm_spin = QSpinBox()
        self.pwm_spin.setRange(0, 120)
        self.pwm_spin.setValue(40)
        self.pwm_spin.setSingleStep(5)
        grid.addWidget(QLabel("PWM"), 2, 0)
        grid.addWidget(self.pwm_spin, 2, 1, 1, 2)

        self.safety_check = QCheckBox("タイヤ浮かせ済み / 非常停止できる / 他のシリアル監視を閉じた")
        grid.addWidget(self.safety_check, 3, 0, 1, 3)

        root.addWidget(boxed("測定条件", controls))

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.servo_button = make_button("サーボ全範囲だけ測定", lambda: self._start("servo"))
        self.combined_button = make_button("モータ+サーボ測定", lambda: self._start("combined"))
        self.ramp_button = make_button("モータPWMランプ", lambda: self._start("ramp"))
        self.stop_button = make_button("STOP / DISARM", self._stop_or_disarm)
        button_layout.addWidget(self.servo_button)
        button_layout.addWidget(self.combined_button)
        button_layout.addWidget(self.ramp_button)
        button_layout.addWidget(self.stop_button)
        root.addWidget(buttons)

        self.status_label = QLabel("未測定")
        self.status_label.setWordWrap(True)
        root.addWidget(boxed("状態", self.status_label))

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(360)
        set_monospace(self.output)
        root.addWidget(boxed("ログ/判定", self.output), 1)

        self.refresh_ports()

    def _project_log_dir(self) -> Path:
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "config" / "vehicle_config.json").exists():
                return parent / "logs"
        return Path.cwd() / "logs"

    def _default_port(self) -> str:
        serial_obj = getattr(self.host, "serial", None)
        port = getattr(serial_obj, "port", None)
        return str(port or "COM7")

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText().strip() or self._default_port()
        self.port_combo.clear()
        seen: set[str] = set()
        try:
            from serial.tools import list_ports

            for info in list_ports.comports():
                device = str(info.device)
                label = f"{device} - {info.description}"
                self.port_combo.addItem(label, device)
                seen.add(device.upper())
        except Exception as exc:
            self.output.appendPlainText(f"COM更新失敗: {exc}")

        if current.upper() not in seen:
            self.port_combo.insertItem(0, current, current)
        index = self.port_combo.findData(current)
        self.port_combo.setCurrentIndex(index if index >= 0 else 0)

    def _selected_port(self) -> str:
        data = self.port_combo.currentData()
        text = str(data) if data else self.port_combo.currentText()
        return text.split(" - ", 1)[0].strip()

    def _selected_wheel(self) -> int:
        data = self.wheel_combo.currentData()
        return int(data if data is not None else self.wheel_combo.currentIndex())

    def _host_port_conflict(self, port: str) -> bool:
        host = self.host
        if host is None:
            return False
        try:
            if hasattr(host, "_serial_monitor_uses_port") and host._serial_monitor_uses_port(port):
                self.output.appendPlainText("同じCOMをシリアルモニタが使用中です。閉じてから測定してください。")
                return True
        except Exception:
            pass
        serial_obj = getattr(host, "serial", None)
        if serial_obj is None or not hasattr(serial_obj, "status"):
            return False
        try:
            status = serial_obj.status()
            connected = bool(getattr(status, "connected", False))
            used_port = str(getattr(status, "port", "") or getattr(serial_obj, "port", ""))
        except Exception:
            return False
        if connected and used_port.upper() == port.upper():
            self.output.appendPlainText("4WIS通常接続が同じCOMを開いています。先にDISARM/切断してから測定してください。")
            return True
        return False

    def _start(self, mode: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.output.appendPlainText("測定中です。完了を待ってください。")
            return
        if mode != "stop-disarm" and not self.safety_check.isChecked():
            self.output.appendPlainText("安全確認チェックを入れてから測定してください。")
            return

        port = self._selected_port()
        if not port:
            self.output.appendPlainText("COMポートを選択してください。")
            return
        if self._host_port_conflict(port):
            return

        wheel = self._selected_wheel()
        pwm = int(self.pwm_spin.value())
        self._set_running(True)
        self.status_label.setText(f"{mode} 実行中: {port} / {WHEEL_NAMES[wheel]} / PWM={pwm}")
        self.output.appendPlainText("")
        self.output.appendPlainText(f"=== {mode} start: {port} {WHEEL_NAMES[wheel]} pwm={pwm} ===")

        self.worker = NoiseTestWorker(mode=mode, port=port, wheel=wheel, pwm=pwm, log_dir=self.log_dir)
        self.worker.progress.connect(self.output.appendPlainText)
        self.worker.result_ready.connect(self._handle_result)
        self.worker.error_ready.connect(self._handle_error)
        self.worker.finished.connect(lambda: self._set_running(False))
        self.worker.start()

    def _stop_or_disarm(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.status_label.setText("停止要求中: 安全停止/DISARM待ち")
            self.stop_button.setEnabled(False)
            return
        self._start("stop-disarm")

    def _set_running(self, running: bool) -> None:
        self.servo_button.setEnabled(not running)
        self.combined_button.setEnabled(not running)
        self.ramp_button.setEnabled(not running)
        self.stop_button.setEnabled(True)

    def _handle_result(self, result: dict) -> None:
        text = format_result_text(result)
        self.output.appendPlainText(text)
        classification = result.get("classification", {})
        status = str(classification.get("status", "-")) if isinstance(classification, dict) else "-"
        if status == "pass":
            self.status_label.setText("完了: ノイズ未検出")
        elif status == "rotation_unconfirmed":
            self.status_label.setText("完了: 回転未確認。モータ配線/MD10C/機械拘束/物理マッピングを確認。")
        elif status == "noise_observed":
            self.status_label.setText("完了: ノイズ検出。ログを確認。")
        elif status == "fault":
            self.status_label.setText("完了: FAULT発生。ログを確認。")
        else:
            self.status_label.setText(f"完了: {status}")

    def _handle_error(self, message: str) -> None:
        self.status_label.setText(f"エラー: {message}")
        self.output.appendPlainText(f"ERROR: {message}")


def create_noise_test_tab(host: Any | None = None) -> NoiseTestWidget:
    widget = NoiseTestWidget(host)
    if host is not None:
        host.noise_test_widget = widget
    return widget
