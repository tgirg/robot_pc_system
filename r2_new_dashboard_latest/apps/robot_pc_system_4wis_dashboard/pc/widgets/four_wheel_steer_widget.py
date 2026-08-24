from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QDoubleSpinBox,
    QSpinBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    from ..four_wheel_steer_model import (
        WHEEL_NAMES,
        WheelTelemetry,
        clamp_value,
        load_vehicle_config,
        save_vehicle_config,
        telemetry_from_line,
    )
    from ..v29_drive_adapter import V29DriveAdapter
    from ..four_wheel_motion_check import format_4wis_motion_check_report, run_4wis_motion_checks
    from ..v29_send_inspection import inspect_v29_send_line
except ImportError:
    from four_wheel_steer_model import (
        WHEEL_NAMES,
        WheelTelemetry,
        clamp_value,
        load_vehicle_config,
        save_vehicle_config,
        telemetry_from_line,
    )
    from v29_drive_adapter import V29DriveAdapter
    from four_wheel_motion_check import format_4wis_motion_check_report, run_4wis_motion_checks
    from v29_send_inspection import inspect_v29_send_line

from .ui_helpers import boxed, make_notice, set_section_title

try:
    from ..steer_view_geometry import robot_angle_to_qt_rotation, robot_angle_to_screen_vector
except ImportError:
    from steer_view_geometry import robot_angle_to_qt_rotation, robot_angle_to_screen_vector


class WheelSteerCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.angles_deg = [0.0, 0.0, 0.0, 0.0]
        self.speeds_mps = [0.0, 0.0, 0.0, 0.0]
        self.source = "未更新"
        self.setMinimumSize(430, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, telemetry: WheelTelemetry) -> None:
        self.angles_deg = list(telemetry.angles_deg)
        self.speeds_mps = list(telemetry.speeds_mps)
        self.source = telemetry.source
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(self.rect(), QColor("#0f172a"))

        body_w = min(rect.width() * 0.58, 330.0)
        body_h = min(rect.height() * 0.66, 250.0)
        body_x = rect.center().x() - body_w / 2.0
        body_y = rect.center().y() - body_h / 2.0
        body = QRectF(body_x, body_y, body_w, body_h)

        painter.setPen(QPen(QColor("#334155"), 2))
        painter.setBrush(QColor("#1f2937"))
        painter.drawRoundedRect(body, 8, 8)

        painter.setPen(QPen(QColor("#7dd3fc"), 2))
        painter.drawLine(int(body.center().x()), int(body.top() + 16), int(body.center().x()), int(body.top() + 52))
        painter.drawLine(int(body.center().x()), int(body.top() + 16), int(body.center().x() - 8), int(body.top() + 30))
        painter.drawLine(int(body.center().x()), int(body.top() + 16), int(body.center().x() + 8), int(body.top() + 30))

        wheel_points = [
            (body.left() + body_w * 0.18, body.top() + body_h * 0.20),
            (body.right() - body_w * 0.18, body.top() + body_h * 0.20),
            (body.left() + body_w * 0.18, body.bottom() - body_h * 0.20),
            (body.right() - body_w * 0.18, body.bottom() - body_h * 0.20),
        ]
        max_speed = max((abs(speed) for speed in self.speeds_mps), default=0.0)
        max_speed = max(max_speed, 0.001)
        for index, (x_pos, y_pos) in enumerate(wheel_points):
            self._draw_wheel(painter, index, x_pos, y_pos, max_speed)

        painter.setPen(QColor("#cbd5e1"))
        painter.drawText(rect.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, f"入力: {self.source}")

    def _draw_wheel(self, painter: QPainter, index: int, x_pos: float, y_pos: float, max_speed: float) -> None:
        angle = self.angles_deg[index]
        speed = self.speeds_mps[index]
        speed_abs = abs(speed)
        color = QColor("#22c55e") if speed_abs > 0.02 else QColor("#64748b")
        painter.save()
        painter.translate(x_pos, y_pos)
        painter.rotate(robot_angle_to_qt_rotation(angle))
        painter.setBrush(color)
        painter.setPen(QPen(QColor("#e2e8f0"), 2))
        painter.drawRoundedRect(QRectF(-13, -36, 26, 72), 5, 5)
        painter.setPen(QPen(QColor("#0f172a"), 2))
        painter.drawLine(0, -26, 0, 26)
        painter.restore()

        scale = clamp_value(speed_abs / max_speed, 0.0, 1.0)
        arrow_len = 22.0 + 34.0 * scale
        drive_angle = angle if speed >= 0.0 else angle + 180.0
        dir_x, dir_y = robot_angle_to_screen_vector(drive_angle)
        end_x = x_pos + dir_x * arrow_len
        end_y = y_pos + dir_y * arrow_len
        perp_x, perp_y = -dir_y, dir_x
        painter.setPen(QPen(QColor("#facc15"), 3))
        painter.drawLine(int(x_pos), int(y_pos), int(end_x), int(end_y))
        painter.drawLine(int(end_x), int(end_y), int(end_x - dir_x * 10 + perp_x * 5), int(end_y - dir_y * 10 + perp_y * 5))
        painter.drawLine(int(end_x), int(end_y), int(end_x - dir_x * 10 - perp_x * 5), int(end_y - dir_y * 10 - perp_y * 5))

        label_x = x_pos - 104 if index in (0, 2) else x_pos + 24
        label_y = y_pos - 18
        painter.setPen(QColor("#e5e7eb"))
        align = Qt.AlignRight if index in (0, 2) else Qt.AlignLeft
        painter.drawText(QRectF(label_x, label_y, 88, 42), align | Qt.AlignVCenter, f"{WHEEL_NAMES[index]}\n{angle:+.1f} deg")


class FourWheelSteerWidget(QWidget):
    real_connect_requested = Signal()
    real_refresh_ports_requested = Signal()
    real_connection_test_requested = Signal()
    real_config_requested = Signal()
    real_arm_requested = Signal()
    real_drive_requested = Signal()
    real_stop_requested = Signal()
    real_disarm_requested = Signal()
    servo_debug_lock_changed = Signal(bool)
    real_servo_debug_requested = Signal(list)
    real_servo_center_us_requested = Signal(list)
    firmware_upload_requested = Signal()
    serial_cleanup_requested = Signal()
    fake_enabled_changed = Signal(bool)
    fake_fault_requested = Signal()
    fake_timeout_requested = Signal()

    def __init__(self, host: Any | None = None) -> None:
        super().__init__()
        self.host = host
        self.vehicle_config = load_vehicle_config()
        self.last_angles = [0.0, 0.0, 0.0, 0.0]
        self.preview_adapter = V29DriveAdapter(self.vehicle_config)
        self.v29_preview_max_pwm = 120
        self.current_telemetry = self.preview_adapter.build_stop(1, armed=False).telemetry
        self.vehicle_param_inputs: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.pid_enabled_input: QCheckBox | None = None
        self.pid_param_inputs: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.vehicle_config_status_label: QLabel | None = None
        self.servo_connect_inputs: dict[str, QSpinBox] = {}
        self.servo_center_sliders: dict[str, QSlider] = {}
        self.servo_center_labels: dict[str, QLabel] = {}
        self.servo_connect_status_label: QLabel | None = None
        self.firmware_write_status_label: QLabel | None = None
        self.servo_sliders: dict[str, QSlider] = {}
        self.servo_name_labels: dict[str, QLabel] = {}
        self.servo_angle_labels: dict[str, QLabel] = {}
        self.servo_debug_lock = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("4輪独立ステア")
        set_section_title(title)
        root.addWidget(title)
        root.addWidget(make_notice("4WIS表示: v29実機送信はARM ACK後のボタン操作のみ / telemetry受信時は自動反映"))

        main = QHBoxLayout()
        main.setSpacing(12)
        self.canvas = WheelSteerCanvas()
        main.addWidget(boxed("ステア角ビュー", self.canvas), 4)

        side = QWidget()
        side.setMinimumWidth(500)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        side_layout.addWidget(self._build_drive_input_box())
        side_layout.addWidget(self._build_vehicle_param_box())
        side_layout.addWidget(self._build_connector_box())
        side_layout.addWidget(self._build_servo_center_box())
        side_layout.addWidget(self._build_firmware_write_box())
        side_layout.addWidget(self._build_real_control_box())
        side_layout.addWidget(self._build_send_inspection_box())
        side_layout.addWidget(self._build_fake_esp32_box())
        side_layout.addWidget(self._build_status_box())
        side_layout.addWidget(self._build_motion_check_box())
        side_layout.addWidget(self._build_servo_input_box())
        side_layout.addStretch(1)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setMinimumWidth(520)
        side_scroll.setWidget(side)
        main.addWidget(side_scroll, 3)
        root.addLayout(main, 1)
        self._publish_state(self.current_telemetry)

    def _build_drive_input_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.input_labels: dict[str, QLabel] = {}
        self.sliders: dict[str, QSlider] = {}
        for key, label in [("vx", "前後"), ("vy", "左右"), ("omega", "旋回")]:
            row = QHBoxLayout()
            name = QLabel(label)
            value_label = QLabel("0")
            value_label.setMinimumWidth(44)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(-100, 100)
            slider.setSingleStep(5)
            slider.setPageStep(10)
            slider.valueChanged.connect(self._manual_inputs_changed)
            row.addWidget(name)
            row.addWidget(slider, 1)
            row.addWidget(value_label)
            layout.addLayout(row)
            self.input_labels[key] = value_label
            self.sliders[key] = slider

        preset_grid = QGridLayout()
        preset_grid.setSpacing(6)
        presets = [
            ("前進", 60, 0, 0),
            ("後退", -60, 0, 0),
            ("左移動", 0, 60, 0),
            ("右移動", 0, -60, 0),
            ("左旋回", 0, 0, 60),
            ("右旋回", 0, 0, -60),
            ("停止", 0, 0, 0),
        ]
        for index, (text, vx, vy, omega) in enumerate(presets):
            button = QPushButton(text)
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, a=vx, b=vy, c=omega: self.set_manual_inputs(a, b, c))
            preset_grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(preset_grid)
        box = boxed("走行入力", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_vehicle_param_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._init_vehicle_param_fields()
        self.vehicle_config_status_label = QLabel("vehicle_config: not edited")
        self.vehicle_config_status_label.setObjectName("diagnosticLabel")
        self.vehicle_config_status_label.setWordWrap(True)
        layout.addWidget(self.vehicle_config_status_label)

        grid = QGridLayout()
        grid.setSpacing(6)
        row = 0
        grid.addWidget(QLabel("wheelbase_m"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["wheelbase_m"], row, 1)
        row += 1
        grid.addWidget(QLabel("track_width_m"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["track_width_m"], row, 1)
        row += 1
        grid.addWidget(QLabel("wheel_diameter_m"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["wheel_diameter_m"], row, 1)
        row += 1
        grid.addWidget(QLabel("max_linear_speed_mps"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["max_linear_speed_mps"], row, 1)
        row += 1
        grid.addWidget(QLabel("max_angular_speed_radps"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["max_angular_speed_radps"], row, 1)
        row += 1
        grid.addWidget(QLabel("open_loop_max_pwm"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["open_loop_max_pwm"], row, 1)
        row += 1
        grid.addWidget(QLabel("max_wheel_rpm"), row, 0)
        grid.addWidget(self.vehicle_param_inputs["max_wheel_rpm"], row, 1)
        layout.addLayout(grid)

        self.pid_enabled_input = QCheckBox("PID ON (rpm command; OFF = PWM command)")
        self.pid_enabled_input.setToolTip(
            "ON saves vehicle_config.pid_enabled=true and 4WIS drive sends control=rpm. "
            "After saving, send CONFIG before ARM."
        )
        layout.addWidget(self.pid_enabled_input)

        pid_grid = QGridLayout()
        pid_grid.setSpacing(6)
        pid_grid.addWidget(QLabel("kp"), 0, 0)
        pid_grid.addWidget(self.pid_param_inputs["kp"], 0, 1)
        pid_grid.addWidget(QLabel("ki"), 1, 0)
        pid_grid.addWidget(self.pid_param_inputs["ki"], 1, 1)
        pid_grid.addWidget(QLabel("kd"), 2, 0)
        pid_grid.addWidget(self.pid_param_inputs["kd"], 2, 1)
        pid_grid.addWidget(QLabel("integral_limit"), 3, 0)
        pid_grid.addWidget(self.pid_param_inputs["integral_limit"], 3, 1)
        pid_grid.addWidget(QLabel("output_min"), 4, 0)
        pid_grid.addWidget(self.pid_param_inputs["output_min"], 4, 1)
        pid_grid.addWidget(QLabel("output_max"), 5, 0)
        pid_grid.addWidget(self.pid_param_inputs["output_max"], 5, 1)
        layout.addWidget(QLabel("PID values (applied to all 4 motors)"))
        layout.addLayout(pid_grid)
        self._load_vehicle_param_fields(self.vehicle_config)

        buttons = QHBoxLayout()
        reload_button = QPushButton("再読込")
        reload_button.setMinimumHeight(34)
        reload_button.clicked.connect(self._reload_vehicle_params_from_disk)
        save_button = QPushButton("保存して反映")
        save_button.setMinimumHeight(34)
        save_button.clicked.connect(self._save_vehicle_params)
        buttons.addWidget(reload_button, 1)
        buttons.addWidget(save_button, 1)
        layout.addLayout(buttons)
        box = boxed("4WIS パラメータ", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_connector_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.servo_connect_inputs = {}
        self.servo_connect_status_label = QLabel("connector: not edited")
        self.servo_connect_status_label.setObjectName("diagnosticLabel")
        self.servo_connect_status_label.setWordWrap(True)
        layout.addWidget(self.servo_connect_status_label)

        grid = QGridLayout()
        grid.setSpacing(6)
        header = ["", "サーボ ch", "モータ physical", "エンコーダ physical"]
        for col, text in enumerate(header):
            grid.addWidget(QLabel(text), 0, col)

        for index, name in enumerate(WHEEL_NAMES):
            row = index + 1
            grid.addWidget(QLabel(name), row, 0)
            servo_channel = QSpinBox()
            servo_channel.setRange(0, 31)
            servo_channel.setSingleStep(1)
            motor_physical = QSpinBox()
            motor_physical.setRange(0, 31)
            motor_physical.setSingleStep(1)
            encoder_physical = QSpinBox()
            encoder_physical.setRange(0, 31)
            encoder_physical.setSingleStep(1)
            self.servo_connect_inputs[f"{name}_servo_channel"] = servo_channel
            self.servo_connect_inputs[f"{name}_motor_physical"] = motor_physical
            self.servo_connect_inputs[f"{name}_encoder_physical"] = encoder_physical
            grid.addWidget(servo_channel, row, 1)
            grid.addWidget(motor_physical, row, 2)
            grid.addWidget(encoder_physical, row, 3)

        layout.addLayout(grid)
        self._load_connector_fields(self.vehicle_config)

        button_row = QHBoxLayout()
        reload_button = QPushButton("再読込")
        reload_button.setMinimumHeight(34)
        reload_button.clicked.connect(self._reload_vehicle_params_from_disk)
        save_button = QPushButton("接続設定を保存して反映")
        save_button.setMinimumHeight(34)
        save_button.clicked.connect(self._save_connector_config)
        button_row.addWidget(reload_button, 1)
        button_row.addWidget(save_button, 1)
        layout.addLayout(button_row)

        box = boxed("コネクタ接続", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_servo_center_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        note = QLabel("個別サーボ診断ONの時だけ、スライダー変更を実機へservo_usで即送信します。保存でcenter_usへ反映します。")
        note.setObjectName("diagnosticLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.servo_center_sliders = {}
        self.servo_center_labels = {}
        for index, name in enumerate(WHEEL_NAMES):
            row = QHBoxLayout()
            servo_name = QLabel(f"{name} ch{self._servo_channel(index)}")
            servo_name.setMinimumWidth(64)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(500, 2500)
            slider.setSingleStep(1)
            slider.setPageStep(10)
            slider.valueChanged.connect(self._servo_center_inputs_changed)
            label = QLabel("1500 us")
            label.setMinimumWidth(72)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(servo_name)
            row.addWidget(slider, 1)
            row.addWidget(label)
            layout.addLayout(row)
            self.servo_center_sliders[name] = slider
            self.servo_center_labels[name] = label

        self._load_servo_center_fields(self.vehicle_config)

        button_row = QHBoxLayout()
        send_button = QPushButton("中心usを実機へ送信")
        send_button.setMinimumHeight(34)
        send_button.setToolTip("個別サーボ診断ONにして、現在のcenter_usをservo_usで実機へ送信します。")
        save_button = QPushButton("中心usを保存")
        save_button.setMinimumHeight(34)
        send_button.clicked.connect(self._request_servo_center_debug_send)
        save_button.clicked.connect(self._save_connector_config)
        button_row.addWidget(send_button, 1)
        button_row.addWidget(save_button, 1)
        layout.addLayout(button_row)

        box = boxed("サーボ中心us調整", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_firmware_write_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.firmware_write_status_label = QLabel("firmware: ready")
        self.firmware_write_status_label.setObjectName("diagnosticLabel")
        self.firmware_write_status_label.setWordWrap(True)
        layout.addWidget(self.firmware_write_status_label)

        write_button = QPushButton("4WISファームを書き込む")
        write_button.setMinimumHeight(40)
        write_button.setToolTip("esp32_firmwareをESP32へ書き込みます。実機送信は停止し、確認ダイアログ後に実行します。")
        write_button.clicked.connect(self._request_firmware_upload)
        layout.addWidget(write_button)
        cleanup_button = QPushButton("他のシリアル通信を停止")
        cleanup_button.setMinimumHeight(36)
        cleanup_button.setToolTip("アプリ内の実機接続/シリアルモニタを切断し、Arduinoのserial-monitor/avrdudeを停止します。")
        cleanup_button.clicked.connect(self._request_serial_cleanup)
        layout.addWidget(cleanup_button)

        box = boxed("4WIS 書き込み", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _request_firmware_upload(self) -> None:
        self.set_firmware_write_status("4WISファーム書き込みを開始します", "busy")
        self.firmware_upload_requested.emit()

    def _request_serial_cleanup(self) -> None:
        self.set_firmware_write_status("他のシリアル通信を停止しています", "busy")
        self.serial_cleanup_requested.emit()

    def _init_vehicle_param_fields(self) -> None:
        self.vehicle_param_inputs.clear()
        wheelbase_input = QDoubleSpinBox()
        wheelbase_input.setRange(0.01, 10.0)
        wheelbase_input.setDecimals(3)
        wheelbase_input.setSingleStep(0.005)

        track_input = QDoubleSpinBox()
        track_input.setRange(0.01, 10.0)
        track_input.setDecimals(3)
        track_input.setSingleStep(0.005)

        diameter_input = QDoubleSpinBox()
        diameter_input.setRange(0.001, 10.0)
        diameter_input.setDecimals(4)
        diameter_input.setSingleStep(0.001)

        max_linear_input = QDoubleSpinBox()
        max_linear_input.setRange(0.01, 20.0)
        max_linear_input.setDecimals(3)
        max_linear_input.setSingleStep(0.05)

        max_angular_input = QDoubleSpinBox()
        max_angular_input.setRange(0.01, 30.0)
        max_angular_input.setDecimals(3)
        max_angular_input.setSingleStep(0.05)

        open_loop_max_pwm_input = QSpinBox()
        open_loop_max_pwm_input.setRange(10, 50000)
        open_loop_max_pwm_input.setSingleStep(10)

        max_rpm_input = QSpinBox()
        max_rpm_input.setRange(1, 100000)
        max_rpm_input.setSingleStep(50)

        kp_input = QDoubleSpinBox()
        ki_input = QDoubleSpinBox()
        kd_input = QDoubleSpinBox()
        for gain_input in (kp_input, ki_input, kd_input):
            gain_input.setRange(0.0, 1000.0)
            gain_input.setDecimals(4)
            gain_input.setSingleStep(0.05)

        integral_limit_input = QDoubleSpinBox()
        integral_limit_input.setRange(0.0, 50000.0)
        integral_limit_input.setDecimals(3)
        integral_limit_input.setSingleStep(10.0)

        output_min_input = QSpinBox()
        output_min_input.setRange(-50000, 0)
        output_min_input.setSingleStep(10)

        output_max_input = QSpinBox()
        output_max_input.setRange(0, 50000)
        output_max_input.setSingleStep(10)

        self.vehicle_param_inputs = {
            "wheelbase_m": wheelbase_input,
            "track_width_m": track_input,
            "wheel_diameter_m": diameter_input,
            "max_linear_speed_mps": max_linear_input,
            "max_angular_speed_radps": max_angular_input,
            "open_loop_max_pwm": open_loop_max_pwm_input,
            "max_wheel_rpm": max_rpm_input,
        }
        self.pid_param_inputs = {
            "kp": kp_input,
            "ki": ki_input,
            "kd": kd_input,
            "integral_limit": integral_limit_input,
            "output_min": output_min_input,
            "output_max": output_max_input,
        }
        self._load_vehicle_param_fields(self.vehicle_config)

    def _load_vehicle_param_fields(self, vehicle_config: dict[str, Any]) -> None:
        motion = vehicle_config.get("motion", {}) if isinstance(vehicle_config, dict) else {}
        defaults = {
            "wheelbase_m": 0.327,
            "track_width_m": 0.327,
            "wheel_diameter_m": 0.055,
            "max_linear_speed_mps": 1.5,
            "max_angular_speed_radps": 4.0,
            "open_loop_max_pwm": 600,
            "max_wheel_rpm": 520,
        }
        for key, default in defaults.items():
            widget = self.vehicle_param_inputs.get(key)
            if widget is None:
                continue
            source = motion.get(key, default) if isinstance(motion, dict) else default
            if isinstance(widget, QSpinBox):
                value = int(float(source))
                widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))
            else:
                value = float(source)
                widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))
        if self.pid_enabled_input is not None:
            motors = vehicle_config.get("motors", []) if isinstance(vehicle_config, dict) else []
            any_motor_pid = any(isinstance(item, dict) and bool(item.get("pid_enabled", False)) for item in motors)
            self.pid_enabled_input.setChecked(bool(vehicle_config.get("pid_enabled", any_motor_pid)))
        motors = vehicle_config.get("motors", []) if isinstance(vehicle_config, dict) else []
        first_motor = motors[0] if motors and isinstance(motors[0], dict) else {}
        pid_defaults = {
            "kp": 1.0,
            "ki": 1.2,
            "kd": 0.0,
            "integral_limit": 100.0,
            "output_min": -140,
            "output_max": 140,
        }
        for key, default in pid_defaults.items():
            widget = self.pid_param_inputs.get(key)
            if widget is None:
                continue
            source = first_motor.get(key, default) if isinstance(first_motor, dict) else default
            if isinstance(widget, QSpinBox):
                value = int(float(source))
                widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))
            else:
                value = float(source)
                widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))

    def _load_connector_fields(self, vehicle_config: dict[str, Any]) -> None:
        servos = vehicle_config.get("servos", []) if isinstance(vehicle_config, dict) else []
        motors = vehicle_config.get("motors", []) if isinstance(vehicle_config, dict) else []
        encoders = vehicle_config.get("encoders", []) if isinstance(vehicle_config, dict) else []
        for index, name in enumerate(WHEEL_NAMES):
            servo_key = f"{name}_servo_channel"
            motor_key = f"{name}_motor_physical"
            encoder_key = f"{name}_encoder_physical"
            if servo_key not in self.servo_connect_inputs:
                continue
            servo_widget = self.servo_connect_inputs[servo_key]
            motor_widget = self.servo_connect_inputs[motor_key]
            encoder_widget = self.servo_connect_inputs[encoder_key]

            servo_ch = 0
            motor_phy = 0
            encoder_phy = 0
            if index < len(servos) and isinstance(servos[index], dict):
                servo_ch = int(servos[index].get("channel", servo_ch) or servo_ch)
            if index < len(motors) and isinstance(motors[index], dict):
                motor_phy = int(motors[index].get("physical", motor_phy) or motor_phy)
            if index < len(encoders) and isinstance(encoders[index], dict):
                encoder_phy = int(encoders[index].get("physical", encoder_phy) or encoder_phy)
            servo_widget.setValue(max(servo_widget.minimum(), min(servo_widget.maximum(), servo_ch)))
            motor_widget.setValue(max(motor_widget.minimum(), min(motor_widget.maximum(), motor_phy)))
            encoder_widget.setValue(max(encoder_widget.minimum(), min(encoder_widget.maximum(), encoder_phy)))
        self._load_servo_center_fields(vehicle_config)

    def _load_servo_center_fields(self, vehicle_config: dict[str, Any]) -> None:
        servos = vehicle_config.get("servos", []) if isinstance(vehicle_config, dict) else []
        for index, name in enumerate(WHEEL_NAMES):
            slider = self.servo_center_sliders.get(name)
            if slider is None:
                continue
            center_us = 1500
            if index < len(servos) and isinstance(servos[index], dict):
                center_us = int(servos[index].get("center_us", center_us) or center_us)
            slider.blockSignals(True)
            slider.setValue(max(slider.minimum(), min(slider.maximum(), center_us)))
            slider.blockSignals(False)
        self._update_servo_center_labels(self.current_servo_center_us())

    def _reload_vehicle_params_from_disk(self) -> None:
        self.vehicle_config = load_vehicle_config()
        self.preview_adapter = V29DriveAdapter(self.vehicle_config)
        self._load_vehicle_param_fields(self.vehicle_config)
        self._load_connector_fields(self.vehicle_config)
        self._refresh_servo_channel_labels()
        self._manual_inputs_changed()
        self._set_vehicle_param_status("vehicle_config を再読込しました", level="ok")
        self._set_servo_connector_status("connector 設定を再読込しました", level="ok")

    def _current_connector_params(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for index, name in enumerate(WHEEL_NAMES):
            values[f"{name}_servo_channel"] = int(self.servo_connect_inputs[f"{name}_servo_channel"].value())
            values[f"{name}_servo_center_us"] = int(self.servo_center_sliders[name].value())
            values[f"{name}_motor_physical"] = int(self.servo_connect_inputs[f"{name}_motor_physical"].value())
            values[f"{name}_encoder_physical"] = int(self.servo_connect_inputs[f"{name}_encoder_physical"].value())
        return values

    def _save_connector_config(self) -> None:
        try:
            values = self._current_connector_params()
            updated = dict(self.vehicle_config)
            servos = [dict(item) if isinstance(item, dict) else {} for item in list(updated.get("servos", []))]
            motors = [dict(item) if isinstance(item, dict) else {} for item in list(updated.get("motors", []))]
            encoders = [dict(item) if isinstance(item, dict) else {} for item in list(updated.get("encoders", []))]
            while len(servos) < len(WHEEL_NAMES):
                servos.append({})
            while len(motors) < len(WHEEL_NAMES):
                motors.append({})
            while len(encoders) < len(WHEEL_NAMES):
                encoders.append({})
            for index, name in enumerate(WHEEL_NAMES):
                servos[index]["name"] = str(name)
                motors[index]["name"] = str(name)
                encoders[index]["name"] = str(name)
                servos[index]["logical"] = index
                motors[index]["logical"] = index
                encoders[index]["logical"] = index
                servos[index]["channel"] = values[f"{name}_servo_channel"]
                servos[index]["center_us"] = values[f"{name}_servo_center_us"]
                motors[index]["physical"] = values[f"{name}_motor_physical"]
                encoders[index]["physical"] = values[f"{name}_encoder_physical"]
            updated["servos"] = servos[: len(WHEEL_NAMES)]
            updated["motors"] = motors[: len(WHEEL_NAMES)]
            updated["encoders"] = encoders[: len(WHEEL_NAMES)]
            save_vehicle_config(updated)
            self.vehicle_config = load_vehicle_config()
            self.preview_adapter = V29DriveAdapter(self.vehicle_config)
            if self.host is not None and hasattr(self.host, "v29_drive_adapter"):
                self.host.v29_drive_adapter = V29DriveAdapter(self.vehicle_config)
            self._load_connector_fields(self.vehicle_config)
            self._refresh_servo_channel_labels()
            self._manual_inputs_changed()
            self._set_servo_connector_status("接続設定を保存しました", level="ok")
            QMessageBox.information(self, "保存", "コネクタ接続設定を保存しました")
        except Exception as exc:
            self._set_servo_connector_status(f"保存失敗: {exc}", level="error")
            QMessageBox.warning(self, "保存失敗", str(exc))

    def _set_servo_connector_status(self, text: str, level: str = "info") -> None:
        if self.servo_connect_status_label is None:
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        self.servo_connect_status_label.setText(text)
        self.servo_connect_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def _current_motion_params(self) -> dict[str, Any]:
        return {
            "wheelbase_m": float(self.vehicle_param_inputs["wheelbase_m"].value()),
            "track_width_m": float(self.vehicle_param_inputs["track_width_m"].value()),
            "wheel_diameter_m": float(self.vehicle_param_inputs["wheel_diameter_m"].value()),
            "max_linear_speed_mps": float(self.vehicle_param_inputs["max_linear_speed_mps"].value()),
            "max_angular_speed_radps": float(self.vehicle_param_inputs["max_angular_speed_radps"].value()),
            "open_loop_max_pwm": int(self.vehicle_param_inputs["open_loop_max_pwm"].value()),
            "max_wheel_rpm": int(self.vehicle_param_inputs["max_wheel_rpm"].value()),
        }

    def _current_pid_enabled(self) -> bool:
        return bool(self.pid_enabled_input is not None and self.pid_enabled_input.isChecked())

    def _current_pid_params(self) -> dict[str, Any]:
        return {
            "kp": float(self.pid_param_inputs["kp"].value()),
            "ki": float(self.pid_param_inputs["ki"].value()),
            "kd": float(self.pid_param_inputs["kd"].value()),
            "integral_limit": float(self.pid_param_inputs["integral_limit"].value()),
            "output_min": int(self.pid_param_inputs["output_min"].value()),
            "output_max": int(self.pid_param_inputs["output_max"].value()),
        }

    def _save_vehicle_params(self) -> None:
        try:
            motion = self._current_motion_params()
            pid_enabled = self._current_pid_enabled()
            pid_params = self._current_pid_params()
            if any(value <= 0 for value in motion.values()):
                raise ValueError("数値はすべて 0 より大きい値である必要があります")
            updated = dict(self.vehicle_config)
            updated["motion"] = dict(updated.get("motion", {}))
            updated["motion"].update(motion)
            updated["pid_enabled"] = pid_enabled
            motors = [dict(item) if isinstance(item, dict) else {} for item in list(updated.get("motors", []))]
            while len(motors) < len(WHEEL_NAMES):
                motors.append({})
            for index, name in enumerate(WHEEL_NAMES):
                motors[index]["logical"] = index
                motors[index]["name"] = str(name)
                motors[index]["pid_enabled"] = pid_enabled
                motors[index].update(pid_params)
            updated["motors"] = motors[: len(WHEEL_NAMES)]
            save_vehicle_config(updated)
            self.vehicle_config = load_vehicle_config()
            self.preview_adapter = V29DriveAdapter(self.vehicle_config)
            self.set_v29_preview_max_pwm(int(motion.get("open_loop_max_pwm", self.v29_preview_max_pwm)))
            if self.host is not None:
                if hasattr(self.host, "v29_drive_adapter"):
                    self.host.v29_drive_adapter = V29DriveAdapter(self.vehicle_config)
                if hasattr(self.host, "real_4wis_max_pwm"):
                    self.host.real_4wis_max_pwm = int(motion.get("open_loop_max_pwm", self.host.real_4wis_max_pwm))
            self._load_vehicle_param_fields(self.vehicle_config)
            self._manual_inputs_changed()
            self._set_vehicle_param_status("保存しました", level="ok")
            QMessageBox.information(self, "保存", "vehicle_config.json を保存しました")
        except Exception as exc:
            self._set_vehicle_param_status(f"保存失敗: {exc}", level="error")
            QMessageBox.warning(self, "保存失敗", str(exc))

    def _set_vehicle_param_status(self, text: str, level: str = "info") -> None:
        if self.vehicle_config_status_label is None:
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        self.vehicle_config_status_label.setText(text)
        self.vehicle_config_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def _build_servo_input_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.servo_debug_lock_check = QCheckBox("個別サーボ診断ON（上書き停止）")
        self.servo_debug_lock_check.setToolTip(
            "ON中はtelemetryやコントローラ入力で個別サーボ角スライダーを上書きしません。"
            "実機接続時はDEBUG ARMで個別サーボ角を送ります。"
        )
        self.servo_debug_lock_check.toggled.connect(self._set_servo_debug_lock)
        layout.addWidget(self.servo_debug_lock_check)

        for index, name in enumerate(WHEEL_NAMES):
            row = QHBoxLayout()
            servo_name = QLabel(f"{name} ch{self._servo_channel(index)}")
            servo_name.setMinimumWidth(64)
            self.servo_name_labels[name] = servo_name
            angle_label = QLabel("+0")
            angle_label.setMinimumWidth(52)
            angle_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            slider = QSlider(Qt.Horizontal)
            min_angle, max_angle = self._servo_limits(index)
            slider.setRange(int(round(min_angle)), int(round(max_angle)))
            slider.setSingleStep(1)
            slider.setPageStep(5)
            slider.valueChanged.connect(self._manual_servo_inputs_changed)
            row.addWidget(servo_name)
            row.addWidget(slider, 1)
            row.addWidget(angle_label)
            layout.addLayout(row)
            self.servo_sliders[name] = slider
            self.servo_angle_labels[name] = angle_label

        servo_preset_grid = QGridLayout()
        servo_preset_grid.setSpacing(6)
        servo_presets = [
            ("全0", [0, 0, 0, 0]),
            ("横向き", [90, 90, 90, 90]),
            ("旋回姿勢", [-45, 45, 45, -45]),
            ("旋回姿勢180", [135, -135, -135, 135]),
        ]
        for index, (text, angles) in enumerate(servo_presets):
            button = QPushButton(text)
            button.setMinimumHeight(34)
            button.clicked.connect(lambda checked=False, values=angles: self.set_servo_angles(values))
            servo_preset_grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(servo_preset_grid)

        send_debug_button = QPushButton("個別サーボ角を実機へ送信")
        send_debug_button.setMinimumHeight(36)
        send_debug_button.setToolTip("個別サーボ診断ONにして、現在のFL/FR/RL/RR角度をESP32へDEBUG送信します。")
        send_debug_button.clicked.connect(self._request_servo_debug_send)
        layout.addWidget(send_debug_button)
        box = boxed("個別サーボ角", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_real_control_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.real_connection_status_label = QLabel("ESP32接続: 未接続（先に実機接続）")
        self.real_connection_status_label.setObjectName("diagnosticLabel")
        self.real_connection_status_label.setWordWrap(True)
        layout.addWidget(self.real_connection_status_label)

        self.real_output_status_label = QLabel("実機送信: OFF / ARM ACK待ち")
        self.real_output_status_label.setObjectName("diagnosticLabel")
        self.real_output_status_label.setWordWrap(True)
        layout.addWidget(self.real_output_status_label)

        connect_row = QHBoxLayout()
        refresh_button = QPushButton("COM更新")
        connect_button = QPushButton("実機接続")
        test_button = QPushButton("接続テスト")
        for button in [refresh_button, connect_button, test_button]:
            button.setMinimumHeight(34)
            connect_row.addWidget(button)
        layout.addLayout(connect_row)

        config_button = QPushButton("CONFIG送信（ESP32へ保存）")
        config_button.setMinimumHeight(40)
        config_button.setToolTip("config/vehicle_config.jsonを読み直してESP32へ送信します。成功後にARMしてください。")
        layout.addWidget(config_button)

        row1 = QHBoxLayout()
        arm_button = QPushButton("ARM")
        disarm_button = QPushButton("DISARM")
        for button in [arm_button, disarm_button]:
            button.setMinimumHeight(34)
            row1.addWidget(button)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        drive_button = QPushButton("現在値送信")
        stop_button = QPushButton("0送信")
        for button in [drive_button, stop_button]:
            button.setMinimumHeight(36)
            row2.addWidget(button)
        layout.addLayout(row2)

        refresh_button.clicked.connect(self.real_refresh_ports_requested.emit)
        connect_button.clicked.connect(self.real_connect_requested.emit)
        test_button.clicked.connect(self.real_connection_test_requested.emit)
        config_button.clicked.connect(self.real_config_requested.emit)
        arm_button.clicked.connect(self.real_arm_requested.emit)
        drive_button.clicked.connect(self.real_drive_requested.emit)
        stop_button.clicked.connect(self.real_stop_requested.emit)
        disarm_button.clicked.connect(self.real_disarm_requested.emit)
        box = boxed("実機v29送信", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_send_inspection_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.send_inspection_status_label = QLabel("最終送信: なし")
        self.send_inspection_status_label.setObjectName("diagnosticLabel")
        self.send_inspection_status_label.setWordWrap(True)
        layout.addWidget(self.send_inspection_status_label)

        clear_button = QPushButton("送信ログ消去")
        clear_button.setMinimumHeight(30)
        clear_button.clicked.connect(self.clear_v29_send_log)
        layout.addWidget(clear_button)

        self.send_inspection_view = QPlainTextEdit()
        self.send_inspection_view.setReadOnly(True)
        self.send_inspection_view.setMinimumHeight(150)
        self.send_inspection_view.setMaximumHeight(240)
        self.send_inspection_view.setPlaceholderText("ARM/現在値送信/0送信/DISARMのv29 JSONを表示します。")
        layout.addWidget(self.send_inspection_view)
        box = boxed("送信値検査ログ", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_fake_esp32_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.fake_esp32_status_label = QLabel("Fake ESP32: OFF")
        self.fake_esp32_status_label.setObjectName("diagnosticLabel")
        self.fake_esp32_status_label.setWordWrap(True)
        layout.addWidget(self.fake_esp32_status_label)

        self.fake_esp32_check = QCheckBox("実機なしFake ESP32通信")
        self.fake_esp32_check.setToolTip("ONにするとARM/送信/telemetryを実機なしで確認できます。実機へは送信しません。")
        self.fake_esp32_check.toggled.connect(self.fake_enabled_changed.emit)
        layout.addWidget(self.fake_esp32_check)

        row = QHBoxLayout()
        fault_button = QPushButton("FAULT発生")
        timeout_button = QPushButton("通信断")
        for button in [fault_button, timeout_button]:
            button.setMinimumHeight(32)
            row.addWidget(button)
        layout.addLayout(row)
        fault_button.clicked.connect(self.fake_fault_requested.emit)
        timeout_button.clicked.connect(self.fake_timeout_requested.emit)
        box = boxed("Fake ESP32通信", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_status_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.source_label = QLabel("source: -")
        self.source_label.setObjectName("diagnosticLabel")
        self.detail_label = QLabel("-")
        self.detail_label.setObjectName("diagnosticLabel")
        self.detail_label.setWordWrap(True)
        self.wheel_rows: dict[str, list[QLabel]] = {}
        layout.addWidget(self.source_label)
        layout.addWidget(self.detail_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        for col, text in enumerate(["輪", "角度", "RPM", "PWM", "PCA ch"]):
            header = QLabel(text)
            header.setObjectName("cardDetail")
            grid.addWidget(header, 0, col)
        for row, name in enumerate(WHEEL_NAMES, start=1):
            name_label = QLabel(name)
            name_label.setObjectName("metricValue")
            grid.addWidget(name_label, row, 0)
            labels: list[QLabel] = []
            for col in range(1, 5):
                label = QLabel("-")
                label.setObjectName("metricValue")
                label.setMinimumWidth(54 if col < 4 else 46)
                grid.addWidget(label, row, col)
                labels.append(label)
            self.wheel_rows[name] = labels
        layout.addLayout(grid)
        box = boxed("4WIS状態", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def _build_motion_check_box(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.motion_check_status_label = QLabel("未実行")
        self.motion_check_status_label.setObjectName("diagnosticLabel")
        self.motion_check_status_label.setWordWrap(True)
        layout.addWidget(self.motion_check_status_label)

        button = QPushButton("全パターンチェック")
        button.setMinimumHeight(34)
        button.clicked.connect(self.run_motion_pattern_check)
        layout.addWidget(button)

        self.motion_check_result_view = QPlainTextEdit()
        self.motion_check_result_view.setReadOnly(True)
        self.motion_check_result_view.setMinimumHeight(170)
        self.motion_check_result_view.setMaximumHeight(260)
        self.motion_check_result_view.setPlaceholderText("実機なしで4WISの代表動作をチェックします。")
        layout.addWidget(self.motion_check_result_view)
        box = boxed("動作パターンチェック", panel)
        box.setCheckable(True)
        box.setChecked(True)
        box.toggled.connect(panel.setVisible)
        return box

    def set_manual_inputs(self, vx: int, vy: int, omega: int) -> None:
        for key, value in [("vx", vx), ("vy", vy), ("omega", omega)]:
            self.sliders[key].blockSignals(True)
            self.sliders[key].setValue(int(value))
            self.sliders[key].blockSignals(False)
        self._manual_inputs_changed()

    def set_v29_preview_max_pwm(self, max_pwm: int) -> None:
        self.v29_preview_max_pwm = max(1, abs(int(max_pwm)))

    def set_vehicle_config(self, vehicle_config: dict[str, Any]) -> None:
        self.vehicle_config = vehicle_config
        self.preview_adapter = V29DriveAdapter(self.vehicle_config)
        self._load_vehicle_param_fields(self.vehicle_config)
        self._load_connector_fields(self.vehicle_config)
        self._refresh_servo_channel_labels()
        self._manual_inputs_changed()

    def current_normalized_inputs(self) -> tuple[float, float, float]:
        return (
            self.sliders["vx"].value() / 100.0,
            self.sliders["vy"].value() / 100.0,
            self.sliders["omega"].value() / 100.0,
        )

    def current_servo_angles(self) -> list[float]:
        return [float(self.servo_sliders[name].value()) for name in WHEEL_NAMES]

    def current_servo_center_us(self) -> list[int]:
        return [int(self.servo_center_sliders[name].value()) for name in WHEEL_NAMES if name in self.servo_center_sliders]

    def set_servo_debug_lock(self, enabled: bool) -> None:
        if hasattr(self, "servo_debug_lock_check"):
            self.servo_debug_lock_check.blockSignals(True)
            self.servo_debug_lock_check.setChecked(bool(enabled))
            self.servo_debug_lock_check.blockSignals(False)
        self._set_servo_debug_lock(bool(enabled))

    def set_real_output_status(self, text: str, level: str = "info") -> None:
        if not hasattr(self, "real_output_status_label"):
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        self.real_output_status_label.setText(text)
        self.real_output_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def set_real_connection_status(self, text: str, level: str = "info") -> None:
        if not hasattr(self, "real_connection_status_label"):
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "busy": "#93c5fd",
            "info": "#dbeafe",
        }
        self.real_connection_status_label.setText(text)
        self.real_connection_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def set_fake_esp32_status(self, text: str, level: str = "info") -> None:
        if not hasattr(self, "fake_esp32_status_label"):
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        self.fake_esp32_status_label.setText(text)
        self.fake_esp32_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def set_firmware_write_status(self, text: str, level: str = "info") -> None:
        if self.firmware_write_status_label is None:
            return
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "busy": "#93c5fd",
            "info": "#dbeafe",
        }
        self.firmware_write_status_label.setText(text)
        self.firmware_write_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")

    def append_v29_send_log(self, label: str, line: str, *, status: str = "TX", max_pwm: int | None = None, level: str = "info") -> None:
        if not hasattr(self, "send_inspection_view"):
            return
        inspection = inspect_v29_send_line(label, line, status=status, max_pwm=max_pwm)
        colors = {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        self.send_inspection_status_label.setText("最終送信: " + inspection.summary)
        self.send_inspection_status_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")
        timestamp = datetime.now().strftime("%H:%M:%S")
        block = f"[{timestamp}] {inspection.text}"
        existing = self.send_inspection_view.toPlainText().strip()
        self.send_inspection_view.setPlainText(block if not existing else block + "\n\n" + existing)

    def clear_v29_send_log(self) -> None:
        if hasattr(self, "send_inspection_view"):
            self.send_inspection_view.clear()
        if hasattr(self, "send_inspection_status_label"):
            self.send_inspection_status_label.setText("最終送信: なし")
            self.send_inspection_status_label.setStyleSheet("color:#dbeafe; font-weight:700;")

    def set_servo_angles(self, angles: list[int]) -> None:
        for index, name in enumerate(WHEEL_NAMES):
            value = int(round(angles[index] if index < len(angles) else 0))
            slider = self.servo_sliders[name]
            value = int(clamp_value(value, float(slider.minimum()), float(slider.maximum())))
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        self._manual_servo_inputs_changed()

    def _set_servo_debug_lock(self, enabled: bool) -> None:
        self.servo_debug_lock = bool(enabled)
        if self.servo_debug_lock:
            self._manual_servo_inputs_changed()
            self.set_real_output_status("実機送信: 個別サーボ診断ON / DEBUG ARM準備", "warn")
        else:
            self.set_real_output_status("実機送信: 個別サーボ診断OFF", "warn")
        self.servo_debug_lock_changed.emit(self.servo_debug_lock)

    def _request_servo_debug_send(self) -> None:
        if not self.servo_debug_lock:
            self.set_servo_debug_lock(True)
            return
        self.real_servo_debug_requested.emit(self.current_servo_angles())

    def _request_servo_center_debug_send(self) -> None:
        centers = self.current_servo_center_us()
        if not self.servo_debug_lock:
            self.set_servo_debug_lock(True)
        self.real_servo_center_us_requested.emit(centers)

    def _servo_center_inputs_changed(self) -> None:
        centers = self.current_servo_center_us()
        self._update_servo_center_labels(centers)
        if self.servo_debug_lock:
            self.real_servo_center_us_requested.emit(centers)

    def _update_servo_center_labels(self, centers: list[int]) -> None:
        for name, center_us in zip(WHEEL_NAMES, centers):
            label = self.servo_center_labels.get(name)
            if label is not None:
                label.setText(f"{int(center_us)} us")

    def run_motion_pattern_check(self) -> None:
        self._set_motion_check_visible_status("実行中: 4WIS動作パターンを確認しています", "busy")
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        try:
            report = run_4wis_motion_checks(self.vehicle_config, max_pwm=self.v29_preview_max_pwm)
            text = format_4wis_motion_check_report(report)
        except Exception as exc:
            self._set_motion_check_visible_status(f"チェック失敗: {exc}", "error")
            self.motion_check_result_view.setPlainText(str(exc))
            return
        if report.passed:
            self._set_motion_check_visible_status(f"PASS: {report.passed_count}/{len(report.results)} パターンOK", "ok")
        else:
            self._set_motion_check_visible_status(f"FAIL: {report.passed_count}/{len(report.results)} パターンOK", "error")
        self.motion_check_result_view.setPlainText(text)

    def _set_motion_check_visible_status(self, text: str, level: str) -> None:
        colors = {
            "ok": "#86efac",
            "busy": "#fde68a",
            "error": "#fca5a5",
            "info": "#dbeafe",
        }
        color = colors.get(level, "#dbeafe")
        self.motion_check_status_label.setText(text)
        self.motion_check_status_label.setStyleSheet(f"color:{color}; font-weight:700;")
        self.detail_label.setText(f"動作パターンチェック: {text}")
        self.set_real_output_status(f"動作パターンチェック: {text}", "ok" if level == "ok" else "error" if level == "error" else "warn")
        if self.host is not None and hasattr(self.host, "notify_operation"):
            notify_level = "success" if level == "ok" else "error" if level == "error" else "busy"
            self.host.notify_operation(f"4WIS動作パターンチェック: {text}", notify_level)

    def _manual_inputs_changed(self) -> None:
        vx = self.sliders["vx"].value()
        vy = self.sliders["vy"].value()
        omega = self.sliders["omega"].value()
        for key, value in [("vx", vx), ("vy", vy), ("omega", omega)]:
            self.input_labels[key].setText(str(value))
        self.preview_adapter.reset(self.last_angles)
        telemetry = self.preview_adapter.build_drive(
            1,
            vx / 100.0,
            vy / 100.0,
            omega / 100.0,
            armed=False,
            max_pwm=self.v29_preview_max_pwm,
        ).telemetry
        telemetry = WheelTelemetry(
            angles_deg=telemetry.angles_deg,
            speeds_mps=telemetry.speeds_mps,
            rpm=telemetry.rpm,
            pwm=telemetry.pwm,
            source="v29実機プレビュー",
            detail=telemetry.detail.replace(" / seq 1 / armed False", ""),
        )
        self._publish_state(telemetry)

    def _manual_servo_inputs_changed(self) -> None:
        angles = self.current_servo_angles()
        self._update_servo_angle_labels(angles)
        telemetry = WheelTelemetry(
            angles_deg=angles,
            speeds_mps=[0.0, 0.0, 0.0, 0.0],
            rpm=[None, None, None, None],
            pwm=[None, None, None, None],
            source="手動サーボ角",
            detail=(
                "個別サーボ診断ON: DEBUGでESP32へ送信します。"
                if self.servo_debug_lock
                else "個別サーボ角の表示。ESP32へは送信していません。"
            ),
        )
        self._publish_state(telemetry)
        if self.servo_debug_lock:
            self.real_servo_debug_requested.emit(angles)

    def apply_legacy_drive_command(self, command_text: str) -> None:
        parts = command_text.split()
        if command_text in {"DRIVE STOP", "EMERGENCY_STOP", "DRIVE VEL 0 0"}:
            self.set_manual_inputs(0, 0, 0)
            return
        if len(parts) >= 4 and parts[:2] == ["DRIVE", "VEL"]:
            try:
                left = clamp_value(float(parts[2]) / 255.0, -1.0, 1.0)
                right = clamp_value(float(parts[3]) / 255.0, -1.0, 1.0)
            except ValueError:
                return
            vx = int(round(((left + right) / 2.0) * 100.0))
            omega = int(round(((right - left) / 2.0) * 100.0))
            self.set_manual_inputs(vx, 0, omega)

    def apply_serial_line(self, line: str, source: str = "ESP32") -> None:
        telemetry = telemetry_from_line(line, source, self.vehicle_config, self.last_angles)
        if telemetry is not None:
            self._publish_state(telemetry)

    def _publish_state(self, telemetry: WheelTelemetry) -> None:
        telemetry = self._preserve_live_rpm_for_tx_preview(telemetry)
        manual_servo_source = telemetry.source.startswith("手動サーボ")
        if self.servo_debug_lock and not manual_servo_source:
            telemetry = WheelTelemetry(
                angles_deg=self.current_servo_angles(),
                speeds_mps=[0.0, 0.0, 0.0, 0.0],
                rpm=telemetry.rpm,
                pwm=telemetry.pwm,
                source=f"{telemetry.source} / 個別サーボ固定",
                detail="個別サーボ診断ONのため、受信値ではなくスライダー角を表示しています。",
            )
        self.current_telemetry = telemetry
        self.last_angles = list(telemetry.angles_deg)
        if self.servo_debug_lock and not manual_servo_source:
            self._update_servo_angle_labels(telemetry.angles_deg)
        else:
            self._sync_servo_sliders(telemetry.angles_deg)
        self.canvas.set_state(telemetry)
        self.source_label.setText(f"入力/受信: {telemetry.source}")
        self.detail_label.setText(telemetry.detail or "-")
        servos = self.vehicle_config.get("servos", [])
        for index, name in enumerate(WHEEL_NAMES):
            labels = self.wheel_rows[name]
            channel = "-"
            if index < len(servos) and isinstance(servos[index], dict):
                channel = str(servos[index].get("channel", "-"))
            rpm = telemetry.rpm[index] if index < len(telemetry.rpm) else None
            pwm = telemetry.pwm[index] if index < len(telemetry.pwm) else None
            labels[0].setText(f"{telemetry.angles_deg[index]:+.1f}")
            labels[1].setText("-" if rpm is None else f"{rpm:+.1f}")
            labels[2].setText("-" if pwm is None else f"{pwm:+d}")
            labels[3].setText(channel)

    def _preserve_live_rpm_for_tx_preview(self, telemetry: WheelTelemetry) -> WheelTelemetry:
        if any(value is not None for value in telemetry.rpm):
            return telemetry
        has_pwm = any(value is not None for value in telemetry.pwm)
        if "TX" not in telemetry.source and not has_pwm:
            return telemetry
        if has_pwm and all(value == 0 for value in telemetry.pwm if value is not None):
            return WheelTelemetry(
                angles_deg=telemetry.angles_deg,
                speeds_mps=telemetry.speeds_mps,
                rpm=[0.0, 0.0, 0.0, 0.0],
                pwm=telemetry.pwm,
                source=telemetry.source,
                detail=telemetry.detail,
            )
        previous_rpm = getattr(self.current_telemetry, "rpm", [None, None, None, None])
        if not any(value is not None for value in previous_rpm):
            return telemetry
        return WheelTelemetry(
            angles_deg=telemetry.angles_deg,
            speeds_mps=telemetry.speeds_mps,
            rpm=list(previous_rpm),
            pwm=telemetry.pwm,
            source=telemetry.source,
            detail=telemetry.detail,
        )

    def _update_servo_angle_labels(self, angles: list[float]) -> None:
        if not self.servo_angle_labels:
            return
        for index, name in enumerate(WHEEL_NAMES):
            value = int(round(angles[index] if index < len(angles) else 0.0))
            self.servo_angle_labels[name].setText(f"{value:+d}")

    def _sync_servo_sliders(self, angles: list[float]) -> None:
        if not self.servo_sliders:
            return
        for index, name in enumerate(WHEEL_NAMES):
            slider = self.servo_sliders[name]
            value = int(round(angles[index] if index < len(angles) else 0.0))
            value = int(clamp_value(value, float(slider.minimum()), float(slider.maximum())))
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            self.servo_angle_labels[name].setText(f"{value:+d}")

    def _refresh_servo_channel_labels(self) -> None:
        for index, name in enumerate(WHEEL_NAMES):
            label = self.servo_name_labels.get(name)
            if label is not None:
                label.setText(f"{name} ch{self._servo_channel(index)}")

    def _servo_limits(self, index: int) -> tuple[float, float]:
        servos = self.vehicle_config.get("servos", [])
        if index < len(servos) and isinstance(servos[index], dict):
            return (
                float(servos[index].get("min_angle_deg", -135.0) or -135.0),
                float(servos[index].get("max_angle_deg", 135.0) or 135.0),
            )
        return -135.0, 135.0

    def _servo_channel(self, index: int) -> str:
        servos = self.vehicle_config.get("servos", [])
        if index < len(servos) and isinstance(servos[index], dict):
            return str(servos[index].get("channel", "-"))
        return "-"


def create_four_wheel_steer_tab(host) -> QWidget:
    widget = FourWheelSteerWidget(host)
    if hasattr(host, "real_4wis_max_pwm"):
        widget.set_v29_preview_max_pwm(int(host.real_4wis_max_pwm))
    host.four_wheel_steer_widget = widget
    return widget
