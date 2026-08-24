from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hardware_profile import (
    HardwareProfile,
    get_safe_default_profile,
    load_hardware_profile,
    save_hardware_profile,
    validate_hardware_profile,
)

from .ui_helpers import boxed, make_button, make_notice


class HardwareProfileEditorWidget(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.profile = load_hardware_profile()
        self.fields: dict[str, QWidget] = {}
        self._build()
        self.load_profile(self.profile)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(make_notice(
            "この画面はハードウェア構成メモです。保存しても実モータ出力は有効になりません。"
            "MOTOR_OUTPUT_ENABLED / USE_REAL_IMU / USE_REAL_LIDAR は変更しません。"
        ))

        tabs = QTabWidget()
        tabs.addTab(self._board_page(), "ボード")
        tabs.addTab(self._imu_page(), "IMU")
        tabs.addTab(self._lidar_page(), "LiDAR")
        tabs.addTab(self._motor_page(), "モータドライバ")
        tabs.addTab(self._encoder_page(), "エンコーダ")
        tabs.addTab(self._actuator_page(), "アクチュエータ")
        layout.addWidget(tabs, 1)

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        for text, slot in [
            ("読み込み", self.reload_profile),
            ("保存", self.save_profile),
            ("安全デフォルトに戻す", self.reset_to_safe_default),
            ("YAMLを開く", lambda: self.host.open_project_file("config/hardware_profile.yaml")),
            ("現在の構成をコピー", self.copy_profile_summary),
            ("すべてダミー", self.apply_all_dummy_preset),
            ("MPU6050想定", self.apply_mpu6050_preset),
            ("UART LiDAR想定", self.apply_uart_lidar_preset),
            ("TB6612FNG想定", self.apply_tb6612_preset),
        ]:
            button_layout.addWidget(make_button(text, slot))
        button_layout.addStretch(1)
        layout.addWidget(buttons)

    def _board_page(self) -> QWidget:
        return self._form_page([
            ("board.name", "ボード名", "line"),
            ("board.fqbn", "FQBN", "line"),
            ("board.port", "COMポート", "line"),
            ("board.baudrate", "通信速度", "line"),
        ])

    def _imu_page(self) -> QWidget:
        return self._form_page([
            ("imu.enabled", "有効", "check"),
            ("imu.type", "型番", "line"),
            ("imu.communication", "通信方式", ["dummy", "i2c", "uart", "spi", "usb"]),
            ("imu.sda_pin", "SDA pin", "line"),
            ("imu.scl_pin", "SCL pin", "line"),
            ("imu.voltage", "電圧", "line"),
            ("imu.notes", "メモ", "text"),
        ])

    def _lidar_page(self) -> QWidget:
        return self._form_page([
            ("lidar.enabled", "有効", "check"),
            ("lidar.type", "型番", "line"),
            ("lidar.communication", "通信方式", ["dummy", "uart", "i2c", "usb", "unknown"]),
            ("lidar.uart_rx_pin", "UART RX pin", "line"),
            ("lidar.uart_tx_pin", "UART TX pin", "line"),
            ("lidar.i2c_sda_pin", "I2C SDA pin", "line"),
            ("lidar.i2c_scl_pin", "I2C SCL pin", "line"),
            ("lidar.voltage", "電圧", "line"),
            ("lidar.notes", "メモ", "text"),
        ])

    def _motor_page(self) -> QWidget:
        return self._form_page([
            ("motor_driver.enabled", "有効", "check"),
            ("motor_driver.model", "型番", "line"),
            ("motor_driver.left_pwm_pin", "left PWM pin", "line"),
            ("motor_driver.left_dir_pin", "left DIR pin", "line"),
            ("motor_driver.right_pwm_pin", "right PWM pin", "line"),
            ("motor_driver.right_dir_pin", "right DIR pin", "line"),
            ("motor_driver.standby_pin", "STBY pin", "line"),
            ("motor_driver.voltage_motor", "モータ電源", "line"),
            ("motor_driver.voltage_logic", "ロジック電源", "line"),
            ("motor_driver.notes", "メモ", "text"),
        ])

    def _encoder_page(self) -> QWidget:
        return self._form_page([
            ("encoder.enabled", "有効", "check"),
            ("encoder.left_a_pin", "left A pin", "line"),
            ("encoder.left_b_pin", "left B pin", "line"),
            ("encoder.right_a_pin", "right A pin", "line"),
            ("encoder.right_b_pin", "right B pin", "line"),
            ("encoder.pulses_per_rev", "pulses per rev", "line"),
            ("encoder.notes", "メモ", "text"),
        ])

    def _actuator_page(self) -> QWidget:
        return self._form_page([
            ("actuator.enabled", "有効", "check"),
            ("actuator.type", "種類", "line"),
            ("actuator.notes", "メモ", "text"),
        ])

    def _form_page(self, specs: list[tuple[str, str, Any]]) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        for path, label, kind in specs:
            if kind == "check":
                widget = QCheckBox()
            elif kind == "text":
                widget = QTextEdit()
                widget.setMaximumHeight(90)
            elif isinstance(kind, list):
                widget = QComboBox()
                widget.addItems(kind)
                widget.setEditable(True)
            else:
                widget = QLineEdit()
            self.fields[path] = widget
            layout.addRow(label, widget)
        return page

    def load_profile(self, profile: HardwareProfile) -> None:
        self.profile = profile
        for path, widget in self.fields.items():
            value = self._get_path(profile.data, path)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QTextEdit):
                widget.setPlainText("" if value is None else str(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText("" if value is None else str(value))
            elif isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))

    def collect_profile(self) -> HardwareProfile:
        data = HardwareProfile(self.profile.data).data
        for path, widget in self.fields.items():
            value: Any
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QTextEdit):
                value = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                value = widget.currentText().strip()
            else:
                text = widget.text().strip()
                value = self._coerce_value(path, text)
            self._set_path(data, path, value)
        return HardwareProfile(data)

    def reload_profile(self) -> None:
        self.load_profile(load_hardware_profile())
        self.host._log("ハードウェア構成を読み込みました")

    def save_profile(self) -> None:
        profile = self.collect_profile()
        validation = validate_hardware_profile(profile)
        if validation["errors"]:
            QMessageBox.critical(self, "保存できません", "\n".join(validation["errors"]))
            return
        if validation["warnings"]:
            answer = QMessageBox.question(
                self,
                "警告があります",
                "\n".join(validation["warnings"]) + "\n\n警告がありますが保存しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        path = save_hardware_profile(profile)
        self.host.hardware_profile = load_hardware_profile()
        self.host.hardware_profile_label.setText(self.host.hardware_profile.to_summary_text())
        self.host._log(f"ハードウェア構成を保存しました: {path}")
        QMessageBox.information(self, "保存完了", f"保存しました。\n{path}")

    def reset_to_safe_default(self) -> None:
        answer = QMessageBox.question(
            self,
            "安全デフォルトに戻す",
            "入力中の内容を安全デフォルトに戻しますか？\n保存するまではYAMLには反映されません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.load_profile(get_safe_default_profile())

    def copy_profile_summary(self) -> None:
        profile = self.collect_profile()
        QApplication.clipboard().setText(profile.to_summary_text())
        self.host._log("ハードウェア構成をクリップボードへコピーしました")

    def apply_all_dummy_preset(self) -> None:
        self.load_profile(get_safe_default_profile())

    def apply_mpu6050_preset(self) -> None:
        self._set_field("imu.enabled", True)
        self._set_field("imu.type", "MPU6050")
        self._set_field("imu.communication", "i2c")
        self._set_field("imu.voltage", "3.3V")
        self._set_field("imu.notes", "MPU6050想定。USE_REAL_IMUは0のまま。")

    def apply_uart_lidar_preset(self) -> None:
        self._set_field("lidar.enabled", True)
        self._set_field("lidar.type", "UART LiDAR")
        self._set_field("lidar.communication", "uart")
        self._set_field("lidar.voltage", "5V or 3.3V 要確認")
        self._set_field("lidar.notes", "UART LiDAR想定。USE_REAL_LIDARは0のまま。")

    def apply_tb6612_preset(self) -> None:
        self._set_field("motor_driver.enabled", True)
        self._set_field("motor_driver.model", "TB6612FNG")
        self._set_field("motor_driver.voltage_motor", "モータ電源 要確認")
        self._set_field("motor_driver.voltage_logic", "3.3V or 5V 要確認")
        self._set_field("motor_driver.notes", "TB6612FNG想定。MOTOR_OUTPUT_ENABLEDは0のまま。")

    def _set_field(self, path: str, value: Any) -> None:
        widget = self.fields.get(path)
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(str(value))
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    @staticmethod
    def _get_path(data: dict[str, Any], path: str) -> Any:
        section, key = path.split(".", 1)
        value = data.get(section, {})
        return value.get(key) if isinstance(value, dict) else None

    @staticmethod
    def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
        section, key = path.split(".", 1)
        target = data.setdefault(section, {})
        if isinstance(target, dict):
            target[key] = value

    @staticmethod
    def _coerce_value(path: str, text: str) -> Any:
        if text == "":
            return None
        integer_fields = {
            "board.baudrate",
            "imu.sda_pin",
            "imu.scl_pin",
            "lidar.uart_rx_pin",
            "lidar.uart_tx_pin",
            "lidar.i2c_sda_pin",
            "lidar.i2c_scl_pin",
            "motor_driver.left_pwm_pin",
            "motor_driver.left_dir_pin",
            "motor_driver.right_pwm_pin",
            "motor_driver.right_dir_pin",
            "motor_driver.standby_pin",
            "encoder.left_a_pin",
            "encoder.left_b_pin",
            "encoder.right_a_pin",
            "encoder.right_b_pin",
            "encoder.pulses_per_rev",
        }
        if path in integer_fields:
            try:
                return int(text)
            except ValueError:
                return text
        return text


def create_hardware_profile_editor_panel(host) -> QWidget:
    return boxed("ハードウェア構成エディタ", HardwareProfileEditorWidget(host))
