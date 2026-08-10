from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QCheckBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from camera_module import CameraModule
from arduino_tools import is_non_esp_port, normalize_port_name
from config_loader import cfg_section, load_config, save_config
from connection import ConnectionManager, detect_ports
from control import AutoController, CommandHistory, SafetyLayer, SerialCommandSender, format_command, parse_command
from hardware_check import HardwareCheckLogger, HardwareCheckResult
from hardware_profile import load_hardware_profile
from logger import CsvLogger
from mock_sensors import MockSensors
from sensor_fusion import SensorFusion
from serial_comm import ESP32Serial
from sensors import ImuInertialEstimator, ImuState, OpticalOdometryState, is_sensor_active, parse_serial_sensor_line, status_label
from simulation import RobotSimulator
from widgets.camera_widget import CameraWidget
from widgets.control_panel import ActuatorPanel, ControlPanel
from widgets.arduino_ide_widget import create_arduino_ide_tab
from widgets.diagnostics_widget import create_diagnostics_tab
from widgets.document_links_widget import create_document_links_tab
from widgets.drive_control_widget import create_drive_tab
from widgets.hardware_profile_widget import create_settings_tab
from widgets.header_status_widget import create_header_status_widget
from widgets.home_overview_widget import create_home_tab
from widgets.log_viewer_widget import create_log_tab
from widgets.map_widget import MapWidget
from widgets.real_machine_overview_widget import create_real_machine_overview
from widgets.sensor_panel import SensorPanel
from widgets.sensor_overview_widget import create_sensor_tab
from widgets.serial_monitor_widget import create_serial_monitor_panel
from widgets.simulation_overview_widget import create_simulation_tab
from widgets.status_panel import StatusPanel
from widgets.test_field_widget import TestFieldWidget
from widgets.ui_feedback import clear_busy, set_busy
from widgets.ui_helpers import install_input_wheel_guard, install_qt_font_warning_filter, make_font


class DiagnosticsWorker(QThread):
    result_ready = Signal(str, dict)
    error_ready = Signal(str, str)

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode

    def run(self) -> None:
        try:
            if self.mode == "environment":
                from diagnostics.environment_check import check_environment

                result = {"environment": check_environment()}
            elif self.mode == "serial":
                from diagnostics.serial_port_check import list_serial_ports

                result = {"serial_ports": list_serial_ports()}
            elif self.mode == "camera":
                from diagnostics.camera_check import check_cameras

                result = {"cameras": check_cameras(0, 3)}
            else:
                from diagnostics.diagnostics_report import build_report

                result = build_report()
            self.result_ready.emit(self.mode, result)
        except Exception as exc:
            self.error_ready.emit(self.mode, str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.local_settings = self._load_local_settings()
        self.hardware_profile = load_hardware_profile()
        app_cfg = cfg_section(self.config, "app")
        mode_cfg = cfg_section(self.config, "mode")
        self.display_cfg = self._display_config()
        sensor_cfg = cfg_section(self.config, "sensors")
        logging_cfg = cfg_section(self.config, "logging")
        field_cfg = cfg_section(self.config, "field")
        simulation_cfg = cfg_section(self.config, "simulation")
        auto_drive_cfg = cfg_section(self.config, "auto_drive")

        self.sensor_source, self.sensor_connected = self._sensor_source(mode_cfg)
        self.mode_name, self.mode_description = self._mode_text(mode_cfg)
        self.setWindowTitle(str(app_cfg.get("title", "ロボットPCダッシュボード")))
        self._apply_app_icon()
        self.resize(1400, 900)
        self.setMinimumSize(1100, 720)

        self.connection_manager = ConnectionManager(self.config)
        self.serial = ESP32Serial(self._serial_config(), self.connection_manager)
        safety_cfg = cfg_section(self.config, "safety")
        self.command_sender = SerialCommandSender(self.serial)
        self.safety_layer = SafetyLayer(command_timeout_ms=int(safety_cfg.get("command_timeout_ms", 500)))
        self.command_history = CommandHistory()
        self.imu_state = ImuState()
        self.imu_inertial_estimator = ImuInertialEstimator()
        self.optical_odometry_state = OpticalOdometryState.load()
        self.last_serial_status_text = ""
        self.last_connection_signal_line = ""
        self.firmware_name = ""
        self.firmware_version = ""
        self.arduino_cli_checked = False
        self.arduino_cli_ok = False
        self.esp32_core_ok = False
        self.board_list_checked = False
        self.compile_checked = False
        self.compile_ok = False
        self.upload_checked = False
        self.upload_ok = False
        self.last_esp32_sent_text = "-"
        self.last_motor_dummy_text = "-"
        self.last_motor_left_command = "-"
        self.last_motor_right_command = "-"
        self.quick_check_active = False
        self.quick_check_phase = "idle"
        self.quick_check_deadline = 0.0
        self.quick_check_alive_received = False
        self.quick_check_drive_response = False
        self.quick_check_stop_response = False
        self.quick_check_items: dict[str, dict[str, str]] = {}
        self.quick_check_item_labels: dict[str, QLabel] = {}
        self.quick_check_raw_lines: list[str] = []
        self.latest_hardware_check_json_path = ""
        self.latest_hardware_check_txt_path = ""
        self.latest_wiring_report_json_path = ""
        self.latest_wiring_report_txt_path = ""
        self.firmware_safety_flags = self._load_firmware_safety_flags()
        self.receive_check_lines: list[str] = []
        self.receive_check_deadline = 0.0
        self.test_send_waiting = False
        self.camera = CameraModule(cfg_section(self.config, "camera"))
        self.mock_sensors = MockSensors(
            lidar_min_m=float(sensor_cfg.get("lidar_min_m", 0.35)),
            lidar_max_m=float(sensor_cfg.get("lidar_max_m", 3.0)),
        )
        self.robot_simulator = RobotSimulator.from_config(field_cfg, simulation_cfg)
        self.last_simulation_boundary_status = ""
        self.last_simulation_obstacle_status = ""
        self.auto_controller = AutoController.from_config(auto_drive_cfg)
        self.auto_drive_active = False
        self.auto_drive_decision = "停止"
        self.auto_drive_reason = "未開始"
        self.last_auto_command_text = ""
        self.last_auto_drive_time = 0.0
        self.auto_drive_interval_s = float(auto_drive_cfg.get("command_interval_ms", 300)) / 1000.0
        self.fusion = SensorFusion()
        self.csv_logger = CsvLogger(str(logging_cfg.get("directory", "logs")))
        self.current_command = "DRIVE VEL 0 0"
        self.last_update = time.monotonic()

        self.mode_label = QLabel(self.mode_name)
        self.mode_label.setObjectName("modeLabel")
        self.mode_detail_label = QLabel(self.mode_description)
        self.mode_detail_label.setObjectName("modeDetailLabel")
        self.mode_notice_label = QLabel(self._mode_notice(self.sensor_source))
        self.mode_notice_label.setObjectName("modeNoticeLabel")
        self.global_notification_label = QLabel("最新通知: 起動中")
        self.global_notification_label.setObjectName("modeNoticeLabel")
        self.safety_label = QLabel("安全状態: 正常")
        self.safety_label.setObjectName("safetyLabel")
        self.header_esp32_label = QLabel("ESP32接続状態: 未確認")
        self.header_esp32_label.setObjectName("esp32HeaderLabel")
        self.command_label = QLabel(f"現在の指令: {self.current_command}")
        self.command_label.setObjectName("commandLabel")
        self.display_mode_label = QLabel("表示: 通常")
        self.display_mode_label.setObjectName("displayModeLabel")
        self.header_emergency_button = QPushButton("緊急停止")
        self.header_emergency_button.setObjectName("emergencyButton")
        self.header_emergency_button.setMinimumHeight(42)
        self.header_emergency_button.setToolTip("どのタブからでも緊急停止を実行できます。Escキーでも実行できます。")

        self.camera_widget = CameraWidget()
        self.status_panel = StatusPanel()
        self.sensor_panel = SensorPanel()
        self.map_widget = MapWidget()
        self.map_widget.set_obstacles(self.robot_simulator.field.obstacles)
        self.test_field_widget = TestFieldWidget(
            field_width_mm=self.robot_simulator.field.width_mm,
            field_height_mm=self.robot_simulator.field.height_mm,
        )
        self.real_field_start_pose = self.test_field_widget.r2_start_pose
        self.real_field_x_mm = float(self.real_field_start_pose[0])
        self.real_field_y_mm = float(self.real_field_start_pose[1])
        self.real_field_theta_deg = float(self.real_field_start_pose[2])
        self.real_field_pose_has_data = False
        self.real_field_last_odom_time = 0.0
        self.real_field_pose_source = "実センサ未受信"
        self.field_imu_only_enabled = False
        self.replay_timer = QTimer(self)
        self.replay_timer.timeout.connect(self._replay_next_sensor_log_line)
        self.replay_lines: list[str] = []
        self.replay_index = 0
        self.external_serial_buffer = ""
        self.control_panel = ControlPanel()
        self.simulation_control_panel = ControlPanel()
        self.actuator_panel = ActuatorPanel()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(800)
        self.log_view.setMinimumHeight(220)
        self.machine_log_view = QPlainTextEdit()
        self.machine_log_view.setReadOnly(True)
        self.machine_log_view.setMaximumBlockCount(200)
        self.machine_log_view.setMinimumHeight(220)
        self.diagnostics_log_view = QPlainTextEdit()
        self.diagnostics_log_view.setReadOnly(True)
        self.diagnostics_log_view.setMaximumBlockCount(300)
        self.diagnostics_log_view.setPlaceholderText("診断ログを表示します。")
        self.diagnostics_result_view = QPlainTextEdit()
        self.diagnostics_result_view.setReadOnly(True)
        self.diagnostics_result_view.setPlaceholderText("診断結果がここに表示されます。")
        self.diagnostics_worker: DiagnosticsWorker | None = None
        self.simulation_status_label = QLabel("シミュレーション状態: 未更新")
        self.simulation_status_label.setObjectName("diagnosticLabel")
        self.auto_drive_status_label = QLabel("自動走行状態: 停止中\n自動走行判断: 停止")
        self.auto_drive_status_label.setObjectName("diagnosticLabel")
        self.com_port_combo = QComboBox()
        self.esp32_connection_label = QLabel("接続状態: 未接続")
        self.esp32_connection_label.setObjectName("diagnosticLabel")
        self.esp32_connection_detail_label = QLabel("選択COMポート: -\n通信速度: -\n最終受信: -\n最終送信: -\n受信行数: 0")
        self.esp32_connection_detail_label.setObjectName("diagnosticLabel")
        self.real_esp32_connection_label = QLabel("接続状態: 未接続")
        self.real_esp32_connection_label.setObjectName("diagnosticLabel")
        self.real_esp32_connection_detail_label = QLabel("選択COMポート: -\n通信速度: -\n最終受信: -\n最終送信: -\n受信行数: 0")
        self.real_esp32_connection_detail_label.setObjectName("diagnosticLabel")
        self.connection_test_label = QLabel("接続テスト: 未実行")
        self.connection_test_label.setObjectName("diagnosticLabel")
        self.esp32_receive_log = QPlainTextEdit()
        self.esp32_receive_log.setReadOnly(True)
        self.esp32_receive_log.setMaximumBlockCount(100)
        self.esp32_receive_log.setPlaceholderText("ESP32からの受信行を表示します。")
        self.machine_cards: dict[str, list[dict[str, QLabel]]] = {}
        self.sensor_detail_labels: dict[str, dict[str, QLabel]] = {}
        self.quick_check_com_label = QLabel("使用COMポート: -")
        self.quick_check_connection_label = QLabel("ESP32接続状態: 未確認")
        self.quick_check_result_label = QLabel("最終確認結果: 未実行")
        self.quick_check_time_label = QLabel("最終確認時刻: -")
        self.latest_hardware_result_label = QLabel("前回の実機確認結果: なし")
        self.latest_hardware_result_label.setObjectName("diagnosticLabel")
        self.next_action_label = QLabel("次にやること: 未更新")
        self.next_action_label.setObjectName("modeNoticeLabel")
        self.workflow_step_labels: dict[str, QLabel] = {}
        self.hardware_profile_label = QLabel("")
        self.hardware_profile_label.setObjectName("diagnosticLabel")
        self.hardware_profile_label.setWordWrap(True)
        self.safety_checkboxes: list[QCheckBox] = []
        for label in [
            self.quick_check_com_label,
            self.quick_check_connection_label,
            self.quick_check_result_label,
            self.quick_check_time_label,
        ]:
            label.setObjectName("diagnosticLabel")

        self._build_layout()
        self._connect_signals()
        self._apply_style()

        self._write_startup_log("START")
        try:
            self._startup(logging_cfg)
            self._write_startup_log("SUCCESS")
        except Exception as exc:
            self._write_startup_log(f"FAIL: {exc}")
            raise

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(int(app_cfg.get("update_interval_ms", 100)))
        self._update_latest_hardware_result_label()

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)
        self.header_status_widget = create_header_status_widget(self)
        root_layout.addWidget(self.header_status_widget)

        self.tabs = QTabWidget()
        self.tabs.addTab(create_home_tab(self), "ホーム")
        self.tabs.addTab(create_diagnostics_tab(self), "診断")
        self.tabs.addTab(create_real_machine_overview(self), "実機接続")
        self.tabs.addTab(create_sensor_tab(self), "センサ")
        self.tabs.addTab(create_arduino_ide_tab(self), "書き込み")
        self.tabs.addTab(create_serial_monitor_panel(self), "シリアル")
        self.tabs.addTab(self._box("テストフィールド", self.test_field_widget), "テストフィールド")
        self.tabs.addTab(create_drive_tab(self), "駆動")
        self.tabs.addTab(create_simulation_tab(self), "シミュレーション")
        self.tabs.addTab(create_log_tab(self), "ログ")
        self.tabs.addTab(create_settings_tab(self), "設定")
        self.tabs.addTab(create_document_links_tab(self), "ドキュメント")
        root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self.tabs.currentChanged.connect(self._update_header_visibility_for_tab)
        self._update_header_visibility_for_tab(self.tabs.currentIndex())
        self.refresh_com_ports(log_result=False)

    def switch_to_tab(self, tab_name: str) -> None:
        aliases = {
            "Arduino": "書き込み",
            "Arduino風": "書き込み",
            "シリアルモニタ": "シリアル",
        }
        tab_name = aliases.get(tab_name, tab_name)
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == tab_name:
                self.tabs.setCurrentIndex(index)
                return
        self._log(f"タブが見つかりません: {tab_name}")

    def _prepare_serial_tab_for_immediate_start(self) -> None:
        monitor = getattr(self, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "prepare_for_immediate_start"):
            monitor.prepare_for_immediate_start(auto_connect=True)

    def _update_header_visibility_for_tab(self, index: int) -> None:
        if not hasattr(self, "header_status_widget"):
            return
        tab_name = self.tabs.tabText(index) if 0 <= index < self.tabs.count() else ""
        self.header_status_widget.setVisible(tab_name not in {"書き込み", "シリアル"})
        if tab_name == "シリアル":
            QTimer.singleShot(0, self._prepare_serial_tab_for_immediate_start)

    def enter_fullscreen(self) -> None:
        self.showFullScreen()
        self._update_display_mode_label()
        self._log("全画面表示に切り替えました")

    def exit_fullscreen(self) -> None:
        self.showNormal()
        self._update_display_mode_label()
        self._log("通常表示に戻しました")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def _update_display_mode_label(self) -> None:
        if hasattr(self, "display_mode_label"):
            self.display_mode_label.setText("表示: 全画面" if self.isFullScreen() else "表示: 通常")

    def _machine_card(self, key: str, title: str, rows: list[tuple[str, str]]) -> QGroupBox:
        box = QGroupBox(title)
        box.setObjectName("machineCard")
        layout = QGridLayout(box)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setVerticalSpacing(8)
        labels: dict[str, QLabel] = {}
        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setObjectName("cardLabel")
            value_label = QLabel(value)
            value_label.setObjectName("cardValue")
            value_label.setWordWrap(True)
            layout.addWidget(name_label, row, 0)
            layout.addWidget(value_label, row, 1)
            labels[name] = value_label
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        self.machine_cards.setdefault(key, []).append(labels)
        return box

    def _set_card(self, key: str, status: str, value: str, data_type: str) -> None:
        cards = self.machine_cards.get(key, [])
        if not cards:
            return
        for card in cards:
            labels = list(card.values())
            status_label = card.get("状態") or (labels[0] if len(labels) > 0 else None)
            value_label = card.get("値") or (labels[1] if len(labels) > 1 else None)
            type_label = card.get("データ種別") or (labels[2] if len(labels) > 2 else None)
            if status_label is not None:
                status_label.setText(status)
            if value_label is not None:
                value_label.setText(value)
            if type_label is not None:
                type_label.setText(data_type)

    def _set_card_rows(self, key: str, values: dict[str, str], styles: dict[str, str] | None = None) -> None:
        cards = self.machine_cards.get(key, [])
        if not cards:
            return
        styles = styles or {}
        for card in cards:
            for name, value in values.items():
                label = card.get(name)
                if label is None:
                    continue
                label.setText(value)
                label.setStyleSheet(styles.get(name, ""))

    def _load_firmware_safety_flags(self) -> dict[str, str]:
        root = self._project_root()
        return {
            "MOTOR_OUTPUT_ENABLED": self._read_define_value(root / "esp32" / "drive_controller" / "motor_driver.h", "MOTOR_OUTPUT_ENABLED"),
            "USE_REAL_IMU": self._read_define_value(root / "esp32" / "drive_controller" / "imu_reader.h", "USE_REAL_IMU"),
            "USE_REAL_LIDAR": self._read_define_value(root / "esp32" / "drive_controller" / "drive_controller.ino", "USE_REAL_LIDAR"),
        }

    def _read_define_value(self, path: Path, name: str) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "不明"
        match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+(\S+)", text, re.MULTILINE)
        return match.group(1) if match else "不明"

    def _simulation_controls_box(self) -> QGroupBox:
        simulation_box = QWidget()
        simulation_layout = QVBoxLayout(simulation_box)
        simulation_layout.setContentsMargins(0, 0, 0, 0)
        simulation_buttons = QWidget()
        simulation_button_layout = QHBoxLayout(simulation_buttons)
        reset_button = QPushButton("シミュレーションリセット")
        start_pose_button = QPushButton("初期位置に戻す")
        clear_trail_button = QPushButton("軌跡クリア")
        for button in [reset_button, start_pose_button, clear_trail_button]:
            button.setMinimumHeight(44)
            simulation_button_layout.addWidget(button)
        reset_button.clicked.connect(self.reset_simulation)
        start_pose_button.clicked.connect(self.reset_simulation_pose)
        clear_trail_button.clicked.connect(self.clear_simulation_trail)
        simulation_button_layout.addStretch(1)
        simulation_layout.addWidget(simulation_buttons)
        return self._box("シミュレーション操作", simulation_box)

    def _auto_drive_box(self) -> QGroupBox:
        auto_drive_box = QWidget()
        auto_drive_layout = QVBoxLayout(auto_drive_box)
        auto_drive_layout.setContentsMargins(0, 0, 0, 0)
        auto_drive_layout.addWidget(self.auto_drive_status_label)
        auto_drive_buttons = QWidget()
        auto_drive_button_layout = QHBoxLayout(auto_drive_buttons)
        auto_start_button = QPushButton("自動走行開始")
        auto_stop_button = QPushButton("自動走行停止")
        auto_start_button.setMinimumHeight(44)
        auto_stop_button.setMinimumHeight(44)
        auto_start_button.clicked.connect(self.start_auto_drive)
        auto_stop_button.clicked.connect(self.stop_auto_drive)
        auto_drive_button_layout.addWidget(auto_start_button)
        auto_drive_button_layout.addWidget(auto_stop_button)
        auto_drive_button_layout.addStretch(1)
        auto_drive_layout.addWidget(auto_drive_buttons)
        return self._box("自動走行", auto_drive_box)
    def _box(self, title: str, widget: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.addWidget(widget)
        return box

    def _connect_signals(self) -> None:
        self.control_panel.command_requested.connect(self.send_command)
        self.simulation_control_panel.command_requested.connect(self.send_command)
        self.actuator_panel.command_requested.connect(self.send_command)
        self.test_field_widget.reset_simulation_requested.connect(self._reset_test_field_simulation)
        if hasattr(self.test_field_widget, "r2_position_reset_requested"):
            self.test_field_widget.r2_position_reset_requested.connect(self.reset_r2_field_pose)
        if hasattr(self.test_field_widget, "r2_pose_correction_requested"):
            self.test_field_widget.r2_pose_correction_requested.connect(self.apply_test_field_pose_correction)
        if hasattr(self.test_field_widget, "imu_only_field_requested"):
            self.test_field_widget.imu_only_field_requested.connect(self.enable_imu_only_field_mode)
        if hasattr(self.test_field_widget, "imu_only_field_stop_requested"):
            self.test_field_widget.imu_only_field_stop_requested.connect(self.disable_imu_only_field_mode)
        if hasattr(self.test_field_widget, "optical_apply_toggled"):
            self.test_field_widget.optical_apply_toggled.connect(self.set_optical_odometry_apply_enabled)
        if hasattr(self.test_field_widget, "optical_zero_requested"):
            self.test_field_widget.optical_zero_requested.connect(self.zero_optical_odometry)
        if hasattr(self.test_field_widget, "optical_calibration_requested"):
            self.test_field_widget.optical_calibration_requested.connect(self.save_optical_odometry_scale)
        self.header_emergency_button.clicked.connect(lambda: self.send_command("EMERGENCY_STOP"))
        self.com_port_combo.currentIndexChanged.connect(self._handle_com_port_selection_changed)

    def refresh_com_ports(self, log_result: bool = True) -> None:
        current_port = self.serial.port
        self.com_port_combo.clear()
        if log_result:
            self.connection_test_label.setText("COMポート更新中...")
            self.notify_operation("COMポート更新中...", "busy")
        try:
            ports = detect_ports()
        except Exception as exc:
            self.com_port_combo.addItem(current_port, current_port)
            self.esp32_connection_label.setText(f"接続状態: エラー（COMポート取得失敗: {exc}）")
            if log_result:
                self._log(f"COMポート更新失敗: {exc}")
                self.notify_operation(f"COMポート更新失敗: {exc}", "error")
            return

        if ports:
            for port in ports:
                self.com_port_combo.addItem(port.display_name(), port.port)
        else:
            self.com_port_combo.addItem(current_port, current_port)
        if self.com_port_combo.findData("COM10") < 0:
            self.com_port_combo.addItem("COM10 - 手入力候補（ESP32）", "COM10")

        port_by_name = {normalize_port_name(port.port): port for port in ports}
        last_port = normalize_port_name(str(self.local_settings.get("last_com_port", "")))
        last_index = self.com_port_combo.findData(last_port) if last_port else -1
        likely_index = next((i for i, port in enumerate(ports) if port.is_likely_esp32), -1)
        last_info = port_by_name.get(last_port)
        current_info = port_by_name.get(normalize_port_name(current_port))
        if last_index >= 0 and (last_info is None or not is_non_esp_port(last_info)):
            self.com_port_combo.setCurrentIndex(last_index)
            if log_result:
                self._log(f"前回のCOMポートを選択しました: {last_port}")
        elif likely_index >= 0:
            self.com_port_combo.setCurrentIndex(likely_index)
            self._log(f"ESP32候補を自動選択: {ports[likely_index].port}")
        else:
            if last_port and log_result:
                self._log("前回のCOMポートは見つかりませんでした。ESP32候補を探します。")
            index = self.com_port_combo.findData(current_port)
            if index >= 0 and (current_info is None or not is_non_esp_port(current_info)):
                self.com_port_combo.setCurrentIndex(index)
            else:
                com10_index = self.com_port_combo.findData("COM10")
                if com10_index >= 0:
                    self.com_port_combo.setCurrentIndex(com10_index)
        if log_result:
            self._log("COMポート一覧を更新しました")
            self.connection_test_label.setText(f"COMポート更新完了: {len(ports)}件")
            self.notify_operation(f"COMポート更新完了: {len(ports)}件", "success")

    def auto_select_esp32_port(self) -> None:
        self.notify_operation("ESP32候補を検索中...", "busy")
        ports = detect_ports()
        likely = next((port for port in ports if port.is_likely_esp32), None)
        if likely is None:
            self._log("ESP32候補が見つかりません。")
            self.connection_test_label.setText("接続テスト: ESP32候補が見つかりません")
            self.notify_operation("ESP32候補が見つかりません", "error")
            return
        index = self.com_port_combo.findData(likely.port)
        if index < 0:
            self.refresh_com_ports(log_result=False)
            index = self.com_port_combo.findData(likely.port)
        if index >= 0:
            self.com_port_combo.setCurrentIndex(index)
        self._log(f"ESP32候補を自動選択: {likely.port}")
        self.notify_operation(f"ESP32候補を自動選択しました: {likely.port}", "success")

    def _run_diagnostics(self, mode: str) -> None:
        if self.diagnostics_worker is not None and self.diagnostics_worker.isRunning():
            self.diagnostics_result_view.setPlainText("診断を実行中です。完了までお待ちください。")
            return

        log_messages = {
            "environment": "環境診断を実行しました",
            "serial": "COMポート確認を実行しました",
            "camera": "カメラ確認を実行しました",
            "all": "全診断を実行しました",
        }
        self._log(log_messages.get(mode, "診断を実行しました"))
        self._diagnostic_log(log_messages.get(mode, "診断を実行しました"))
        self.diagnostics_result_view.setPlainText("診断を実行中です...")
        self.notify_operation("診断を実行中...", "busy")
        worker = DiagnosticsWorker(mode)
        worker.result_ready.connect(self._handle_diagnostics_result)
        worker.error_ready.connect(self._handle_diagnostics_error)
        worker.finished.connect(self._clear_diagnostics_worker)
        self.diagnostics_worker = worker
        worker.start()

    def _clear_diagnostics_worker(self) -> None:
        if self.diagnostics_worker is not None:
            self.diagnostics_worker.deleteLater()
            self.diagnostics_worker = None

    def _handle_diagnostics_error(self, mode: str, message: str) -> None:
        self.diagnostics_result_view.setPlainText(f"診断中にエラーが発生しました。\n種別: {mode}\n内容: {message}")
        self._diagnostic_log(f"診断エラー: {mode} / {message}")
        self.notify_operation(f"診断エラー: {message}", "error")

    def _handle_diagnostics_result(self, mode: str, result: dict) -> None:
        text = self._format_diagnostics_result(mode, result)
        self.diagnostics_result_view.setPlainText(text)
        self._diagnostic_log(f"診断完了: {mode}")
        self.notify_operation("診断が完了しました", "success")

    def _format_diagnostics_result(self, mode: str, result: dict) -> str:
        lines: list[str] = []
        title = {
            "environment": "環境診断結果",
            "serial": "COMポート確認結果",
            "camera": "カメラ確認結果",
            "all": "全診断結果",
        }.get(mode, "診断結果")
        lines.append(f"=== {title} ===")

        if "environment" in result:
            self._append_environment_summary(lines, result["environment"])
        if "serial_ports" in result:
            self._append_serial_summary(lines, result["serial_ports"])
        if "cameras" in result:
            self._append_camera_summary(lines, result["cameras"])
        return "\n".join(lines)

    def _append_environment_summary(self, lines: list[str], environment: dict) -> None:
        python = environment.get("python", {})
        lines.append("")
        lines.append("[Python]")
        lines.append(f"バージョン: {python.get('version', '-')} ({'OK' if python.get('ok') else 'NG'})")
        lines.append(f"実行ファイル: {python.get('executable', '-')}")
        lines.append("")
        lines.append("[ライブラリ]")
        for name, item in environment.get("imports", {}).items():
            lines.append(f"{name}: {'OK' if item.get('available') else 'NG'}")

    def _append_serial_summary(self, lines: list[str], serial_ports: dict) -> None:
        lines.append("")
        lines.append("[COMポート]")
        if not serial_ports.get("ok", False):
            lines.append(f"エラー: {serial_ports.get('error', '-')}")
            return
        ports = serial_ports.get("ports", [])
        if not ports:
            lines.append("COMポートは見つかりませんでした。")
            return
        for port in ports:
            lines.append(f"{port.get('device', '-')}  {port.get('description', '')}  {port.get('hwid', '')}")

    def _append_camera_summary(self, lines: list[str], cameras: dict) -> None:
        lines.append("")
        lines.append("[カメラ]")
        if not cameras.get("ok", False):
            lines.append(f"エラー: {cameras.get('error', '-')}")
            return
        found = False
        for camera in cameras.get("cameras", []):
            if camera.get("available"):
                found = True
                lines.append(f"index {camera.get('index')}: 使用可能 {camera.get('width')}x{camera.get('height')}")
            else:
                lines.append(f"index {camera.get('index')}: 未検出")
        if not found:
            lines.append("使用可能なカメラは見つかりませんでした。")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background:#17212b; color:#e5edf5; font-size:14px; }
            QTabWidget::pane { border:1px solid #314151; border-radius:6px; }
            QTabBar::tab { background:#243447; color:#dbe7f3; padding:11px 20px; border:1px solid #314151; border-bottom:0; font-weight:700; }
            QTabBar::tab:selected { background:#33485f; color:#ffffff; }
            QGroupBox { border:1px solid #314151; border-radius:6px; margin-top:10px; padding:10px; font-weight:700; }
            QGroupBox#machineCard { background:#1d2a36; border:2px solid #42566d; border-radius:8px; }
            QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; }
            QPushButton { background:#243447; border:1px solid #3d5064; border-radius:6px; padding:10px 14px; font-weight:700; }
            QPushButton:hover { background:#30465d; }
            QPushButton:disabled { background:#1b2836; color:#7f8b99; border-color:#2a3948; }
            QPushButton#emergencyButton { background:#991b1b; border-color:#ef4444; color:#ffffff; font-size:17px; }
            QPushButton#emergencyButton:hover { background:#b91c1c; }
            QLabel#modeLabel { color:#bfdbfe; font-size:20px; font-weight:800; }
            QLabel#modeDetailLabel { color:#cbd5e1; font-size:13px; }
            QLabel#modeNoticeLabel { color:#fef08a; font-size:14px; font-weight:800; }
            QLabel#safetyLabel { color:#86efac; font-size:18px; font-weight:800; }
            QLabel#esp32HeaderLabel { color:#fdba74; font-size:16px; font-weight:800; }
            QLabel#commandLabel { color:#fef3c7; font-size:16px; font-weight:800; }
            QLabel#displayModeLabel { color:#c4b5fd; font-size:15px; font-weight:800; }
            QLabel#diagnosticLabel { color:#dbe7f3; }
            QLabel#metricValue { color:#f8fafc; font-weight:800; font-size:16px; }
            QLabel#cardLabel { color:#aebed0; font-size:13px; font-weight:700; }
            QLabel#cardValue { color:#f8fafc; font-size:21px; font-weight:900; }
            QLabel#cardStatus { color:#f8fafc; font-size:22px; font-weight:900; }
            QLabel#cardDetail { color:#cbd5e1; font-size:13px; }
            QLabel#largeValue { color:#f8fafc; font-size:24px; font-weight:900; }
            QLabel#sectionTitle { color:#bfdbfe; font-size:18px; font-weight:900; }
            QPlainTextEdit { background:#0f1720; border:1px solid #314151; color:#d8e2ec; font-family:Consolas, "Yu Gothic UI"; font-size:13px; }
            QLabel#quickCheckItem { background:#223142; border:1px solid #3d5064; border-radius:6px; padding:10px; font-size:16px; font-weight:800; }
            QLabel { color:#e5edf5; }
            """
        )

    def _startup(self, logging_cfg: dict) -> None:
        self._log("アプリ起動")
        self._log("設定ファイル読み込み完了")
        self._log(f"{self.mode_name} 有効")
        self.camera.open()
        esp32_status = self.serial.connect(force=True)
        if esp32_status.mock:
            self._log("ESP32未接続: Mock通信で継続")
        elif esp32_status.connected:
            self._log(f"ESP32接続中: {esp32_status.message}")
        else:
            self._log(f"ESP32未接続: {esp32_status.message}")
        if self.camera.connected:
            self._log("カメラ接続中")
        elif self.camera.mock:
            self._log("カメラ未接続: Mock映像で継続")
        else:
            self._log("カメラ未接続: データなし")
        self._log_sensor_sources()

        if bool(logging_cfg.get("enabled_on_start", False)):
            self.start_logging()

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def _local_settings_path(self) -> Path:
        return self._project_root() / "config" / "local_settings.json"

    def _load_local_settings(self) -> dict:
        path = Path(__file__).resolve().parents[1] / "config" / "local_settings.json"
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_local_settings(self) -> None:
        try:
            path = self._local_settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.local_settings["last_window_size"] = [self.width(), self.height()]
            self.local_settings["last_mode"] = self.sensor_source
            with path.open("w", encoding="utf-8") as file:
                json.dump(self.local_settings, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._log(f"ローカル設定の保存に失敗しました: {exc}")

    def _apply_app_icon(self) -> None:
        icon_path = self._project_root() / "assets" / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _write_startup_log(self, status: str) -> None:
        try:
            project_root = self._project_root()
            log_dir = project_root / "logs"
            log_dir.mkdir(exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = (
                f"{timestamp}\t{status}\t"
                f"project={project_root}\t"
                f"python={sys.executable}\t"
                f"mode={self.sensor_source}\n"
            )
            with (log_dir / "startup.log").open("a", encoding="utf-8") as file:
                file.write(line)
        except Exception:
            pass

    def update_loop(self) -> None:
        now = time.monotonic()
        dt = max(0.001, now - self.last_update)
        self.last_update = now

        frame = self.camera.read()
        esp32_status = self.serial.status()
        self._read_serial_sensor_lines(esp32_status)
        show_sensor_values = self._show_sensor_values()
        if self.sensor_source == "Simulation":
            data = self.robot_simulator.step(dt)
            if self.robot_simulator.state.boundary_status and self.robot_simulator.state.boundary_status != self.last_simulation_boundary_status:
                self._log(self.robot_simulator.state.boundary_status)
            if self.robot_simulator.state.obstacle_status and self.robot_simulator.state.obstacle_status != self.last_simulation_obstacle_status:
                self._log("障害物に接触しました")
            self.last_simulation_boundary_status = self.robot_simulator.state.boundary_status
            self.last_simulation_obstacle_status = self.robot_simulator.state.obstacle_status
        elif self.sensor_source == "Real" and self.imu_state.has_recent_data():
            data = self.imu_state.to_sensor_data()
            self.sensor_connected = True
        else:
            data = self.mock_sensors.read(dt, source=self.sensor_source, connected=self.sensor_connected)
        pose = self.fusion.update(data) if show_sensor_values else self.fusion.pose
        real_sensor_values = self._show_real_sensor_values(esp32_status)
        real_sensor_data = self.imu_state.to_sensor_data()
        if self.field_imu_only_enabled:
            self._apply_imu_only_field_pose(real_sensor_data)

        self.camera_widget.set_frame(frame)
        boundary_status = self.robot_simulator.state.boundary_status if self.sensor_source == "Simulation" else ""
        obstacle_status = self.robot_simulator.state.obstacle_status if self.sensor_source == "Simulation" else ""
        self.map_widget.set_pose(pose, self.sensor_source if show_sensor_values else "NoData", boundary_status, obstacle_status)
        self._update_test_field(data, show_sensor_values)
        if hasattr(self, "test_field_widget"):
            self.test_field_widget.update_sensor_status(real_sensor_data, "Real", real_sensor_values)
            self.test_field_widget.update_optical_odometry_status(self.optical_odometry_state.summary())
        self.sensor_panel.update_values(
            real_sensor_data,
            self.current_command,
            source="Real",
            show_values=real_sensor_values,
            label_values=bool(self.display_cfg.get("label_mock_values", True)),
        )
        self._update_sensor_detail_widgets(real_sensor_data, real_sensor_values)
        self._maybe_run_auto_drive()
        self._update_status(esp32_status)
        self._update_safety(esp32_status)
        self._update_simulation_status()
        self._update_auto_drive_status()
        self._update_machine_cards(real_sensor_data, esp32_status, real_sensor_values)
        self._update_home_status(real_sensor_data, esp32_status, real_sensor_values)
        self._update_workflow_state()
        self.csv_logger.write(pose, data, self.current_command, esp32_status)

    def _serial_monitor_uses_port(self, port: str | None = None) -> bool:
        monitor = getattr(self, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "uses_port") and bool(monitor.uses_port(port)):
            return True
        arduino_ide = getattr(self, "arduino_ide_widget", None)
        if arduino_ide is not None and hasattr(arduino_ide, "uses_port") and bool(arduino_ide.uses_port(port)):
            return True
        return False

    def _warn_serial_monitor_conflict(self) -> None:
        message = "シリアルモニタがCOMポートを使用中です。先にシリアルモニタを切断してください。"
        self._log(message)
        try:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "COMポート使用中", message)
        except Exception:
            pass

    def _update_test_field(self, data, show_sensor_values: bool) -> None:
        if not hasattr(self, "test_field_widget"):
            return
        if not show_sensor_values:
            self.test_field_widget.update_from_pose("データなし", None, None, None, has_data=False)
            return
        if self.real_field_pose_has_data and (time.monotonic() - self.real_field_last_odom_time) <= 3.0:
            self.test_field_widget.update_from_pose(
                self.real_field_pose_source,
                self.real_field_x_mm,
                self.real_field_y_mm,
                self.real_field_theta_deg,
                has_data=True,
                source_note="ESP32から受信したオドメトリ/IMUをフィールド座標へ反映しています。",
            )
            return
        if self.sensor_source == "Simulation":
            state = self.robot_simulator.state
            self.test_field_widget.update_from_pose(
                "シミュレーション",
                state.x_mm,
                state.y_mm,
                state.theta_deg,
                has_data=True,
            )
            return
        if self.sensor_source == "Mock":
            self.test_field_widget.update_from_pose(
                "ダミー",
                data.pose_x * 1000.0,
                data.pose_y * 1000.0,
                data.pose_theta,
                has_data=True,
            )
            return
        self.test_field_widget.update_from_pose(
            "実機オドメトリ未接続",
            None,
            None,
            None,
            has_data=False,
            source_note="実機オドメトリ未接続",
        )

    def _reset_test_field_simulation(self) -> None:
        if self.sensor_source == "Simulation":
            self.reset_simulation_pose()
            if hasattr(self, "test_field_widget"):
                self.test_field_widget.set_start_to_current()
            self._log("テストフィールドからシミュレーション位置を初期化しました")
            self.notify_operation("テストフィールドのシミュレーション位置を初期化しました", "success")
            return
        self._reset_real_field_pose(log=True)
        self.notify_operation("R2位置推定をリセットしました", "success")

    def reset_r2_field_pose(self) -> None:
        self._reset_real_field_pose(log=True, keep_visible=True)
        self.notify_operation("R2位置をスタート位置へリセットしました", "success")

    def _update_status(self, esp32_status) -> None:
        if esp32_status.connected and not esp32_status.mock:
            esp32_source = "Real"
        elif esp32_status.mock:
            esp32_source = "Mock通信"
        else:
            esp32_source = "データなし"
        self.status_panel.set_status("ESP32", esp32_status.connected and not esp32_status.mock, esp32_source)
        if self.camera.connected:
            camera_source = "RealCamera"
        elif self.camera.mock:
            camera_source = "Mock映像"
        else:
            camera_source = "データなし"
        self.status_panel.set_status("Camera", self.camera.connected, camera_source)
        for name in ["LiDAR", "IMU", "Optical Odometry", "Encoder"]:
            if name == "LiDAR":
                connected = self.imu_state.has_recent_lidar()
            elif name == "Optical Odometry":
                connected = self.imu_state.has_recent_data() and is_sensor_active(self.imu_state.odom_status)
            elif name == "Encoder":
                connected = self.imu_state.has_recent_data() and is_sensor_active(self.imu_state.encoder_status)
            else:
                connected = self.imu_state.has_recent_data() and is_sensor_active(self.imu_state.imu_status)
            if connected and self._has_real_serial_connection(esp32_status):
                source = "Real"
            elif connected:
                source = "シリアル受信"
            else:
                source = "データなし"
            self.status_panel.set_status(name, connected, source)
        self._update_esp32_connection_label(esp32_status)

    def notify_operation(self, message: str, level: str = "info") -> None:
        text = f"最新通知: {time.strftime('%H:%M:%S')} {message}"
        if hasattr(self, "global_notification_label"):
            colors = {"success": "#86efac", "error": "#fca5a5", "busy": "#fde68a", "info": "#dbeafe"}
            self.global_notification_label.setText(text)
            self.global_notification_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:700;")
        self._log(message)

    def _update_safety(self, esp32_status) -> None:
        if self.current_command == "EMERGENCY_STOP":
            text = "安全状態: 緊急停止中"
            color = "#fca5a5"
        elif not esp32_status.connected:
            text = "安全状態: ESP32通信なし"
            color = "#fdba74"
        elif esp32_status.mock:
            text = "安全状態: 正常（Mock通信）"
            color = "#fde68a"
        else:
            text = "安全状態: 正常"
            color = "#86efac"
        self.safety_label.setText(text)
        self.safety_label.setStyleSheet(f"color:{color}; font-size:18px; font-weight:800;")

    def send_command(self, command: str) -> None:
        parsed_command = parse_command(command)
        safety_result = self.safety_layer.filter_command(parsed_command)
        safe_command_text = format_command(safety_result.command)
        if safe_command_text == "EMERGENCY_STOP" and self.auto_drive_active:
            self.auto_drive_active = False
            self.auto_drive_decision = "停止"
            self.auto_drive_reason = "緊急停止"
            self._log("緊急停止により自動走行を停止しました")
        if safety_result.message:
            prefix = "安全制限" if safety_result.changed or not safety_result.allowed else "安全確認"
            self._log(f"{prefix}: {safety_result.message}")
        if not safety_result.allowed:
            self.command_history.add(safe_command_text, "UI", False, safety_result.message)
            return

        self.current_command = safe_command_text
        self.command_label.setText(f"現在の指令: {self.current_command}")
        if safe_command_text == "EMERGENCY_STOP":
            self._log("緊急停止: EMERGENCY_STOP")
        else:
            self._log(f"指令送信: {safe_command_text}")
        if self.sensor_source == "Simulation":
            self.command_history.add(safe_command_text, "Simulation", True, safety_result.message)
            self._log("シミュレーションモードのためESP32へ送信しません")
            self._apply_simulation_command(safety_result.command, safe_command_text)
            return
        result = self.command_sender.send(safety_result.command)
        self.command_history.add(result.sent_text, "UI", result.success, safety_result.message)
        self._log(result.message if result.success else result.message)
        self._apply_simulation_command(safety_result.command, safe_command_text)

    def _read_serial_sensor_lines(self, esp32_status) -> None:
        if not esp32_status.connected or esp32_status.mock:
            return
        for line in self.serial.read_lines(max_lines=20):
            self._append_esp32_receive_line(line)
            self._handle_quick_check_line(line)
            if self._is_connection_signal(line):
                self.last_connection_signal_line = line
            parsed = parse_serial_sensor_line(line)
            if parsed is None:
                continue
            if parsed.get("type") == "FW":
                name = str(parsed.get("name", ""))
                version = str(parsed.get("version", ""))
                if name != self.firmware_name or version != self.firmware_version:
                    self.firmware_name = name
                    self.firmware_version = version
                    self._log(f"ESP32ファームウェア受信: {name} {version}")
                continue
            self.imu_state.update_from_message(parsed)
            self._apply_real_field_pose_message(parsed, source_kind="REAL")
            if parsed.get("type") == "STATUS":
                status_text = str(parsed.get("status", ""))
                if status_text and status_text != self.last_serial_status_text:
                    self.last_serial_status_text = status_text
                    self._log(f"ESP32状態受信: {status_text}")
            if self.test_send_waiting and (
                line.startswith("RX,DRIVE VEL 50 50") or line.startswith("DRIVE,50,50")
            ):
                self.test_send_waiting = False
                self.connection_test_label.setText("テスト送信成功")
                self._log("テスト送信成功")
                self.notify_operation("テスト送信成功", "success")
                self._send_esp32_line("DRIVE STOP", "テスト後停止")

    def handle_external_serial_text(self, text: str, source: str = "シリアルモニタ") -> None:
        self.external_serial_buffer += text
        lines = self.external_serial_buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self.external_serial_buffer = lines.pop()
        else:
            self.external_serial_buffer = ""
        for raw_line in lines:
            self._handle_external_serial_line(raw_line.strip(), source)

    def _handle_external_serial_line(self, line: str, source: str = "シリアルモニタ") -> None:
        if not line or line.startswith("[") or line.startswith("---") or line.startswith("timestamp:"):
            return
        parsed = parse_serial_sensor_line(line)
        if parsed is None:
            return
        if parsed.get("type") == "FW":
            self.firmware_name = str(parsed.get("name", self.firmware_name))
            self.firmware_version = str(parsed.get("version", self.firmware_version))
            return
        self.imu_state.update_from_message(parsed)
        source_kind = "REAL" if source == "シリアルモニタ" else "REFRESH" if source == "更新" else str(source).upper()
        self._apply_real_field_pose_message(parsed, source_kind=source_kind)
        if parsed.get("type") in {"ODOM", "OPTICAL", "IMU", "LIDAR", "STATUS"}:
            self.real_field_pose_source = source if parsed.get("type") in {"ODOM", "OPTICAL"} else self.real_field_pose_source

    def start_sensor_log_replay(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.notify_operation(f"センサログ再生失敗: {exc}", "error")
            return
        self.replay_lines = [line.strip() for line in text.splitlines() if line.strip()]
        self.replay_index = 0
        self.external_serial_buffer = ""
        self._reset_real_field_pose(log=False)
        if not self.replay_lines:
            self.notify_operation("センサログに再生できる行がありません", "error")
            return
        self.replay_timer.start(30)
        self.notify_operation(f"センサログ再生開始: {path.name}", "busy")

    def _replay_next_sensor_log_line(self) -> None:
        if self.replay_index >= len(self.replay_lines):
            self.replay_timer.stop()
            self.notify_operation("センサログ再生完了", "success")
            return
        for _ in range(5):
            if self.replay_index >= len(self.replay_lines):
                break
            line = self.replay_lines[self.replay_index]
            self.replay_index += 1
            self._handle_external_serial_line(line, "ログ再生")

    def apply_test_field_pose_correction(self, x_mm: float, y_mm: float, theta_deg: float) -> None:
        if not hasattr(self, "test_field_widget"):
            return
        self.real_field_x_mm = max(0.0, min(self.test_field_widget.field_model.width_mm, float(x_mm)))
        self.real_field_y_mm = max(0.0, min(self.test_field_widget.field_model.height_mm, float(y_mm)))
        self.real_field_theta_deg = float(theta_deg) % 360.0
        self.real_field_pose_has_data = True
        self.real_field_last_odom_time = time.monotonic()
        self.real_field_pose_source = "手動補正"
        self.test_field_widget.update_from_pose(
            "手動補正",
            self.real_field_x_mm,
            self.real_field_y_mm,
            self.real_field_theta_deg,
            has_data=True,
            source_note="R2位置を手動補正しました。",
        )
        self.notify_operation("R2位置を手動補正しました", "success")

    def force_sensor_ok_refresh(self) -> None:
        monitor = getattr(self, "serial_monitor_widget", None)
        if monitor is not None and hasattr(monitor, "log_view"):
            text = monitor.log_view.toPlainText()
            if text:
                self.handle_external_serial_text(text + "\n", source="更新")
        data = self.imu_state.to_sensor_data()
        esp32_status = self.serial.status()
        show_values = self._show_real_sensor_values(esp32_status)
        if hasattr(self, "test_field_widget"):
            self.test_field_widget.update_sensor_status(data, "Real", show_values)
        self.sensor_panel.update_values(
            data,
            self.current_command,
            source="Real",
            show_values=show_values,
            label_values=bool(self.display_cfg.get("label_mock_values", True)),
        )
        self._update_sensor_detail_widgets(data, show_values)
        self._update_status(esp32_status)
        self._update_machine_cards(data, esp32_status, show_values)
        self._update_home_status(data, esp32_status, show_values)
        self.notify_operation("センサ表示を更新しました", "success" if show_values else "error")

    def enable_imu_only_field_mode(self) -> None:
        self.field_imu_only_enabled = True
        if hasattr(self, "test_field_widget"):
            current = self.test_field_widget.state
            if current.has_data:
                self.imu_inertial_estimator.reset(current.x_mm, current.y_mm)
            else:
                self.imu_inertial_estimator.reset(self.real_field_start_pose[0], self.real_field_start_pose[1])
        data = self.imu_state.to_sensor_data()
        self._apply_imu_only_field_pose(data)
        if is_sensor_active(getattr(data, "imu_status", "未接続")):
            self.notify_operation("IMU慣性推定を開始しました", "success")
        else:
            self.notify_operation("IMU入力が未受信です。シリアルでIMU_STATUS,OKとIMU行を確認してください。", "error")

    def disable_imu_only_field_mode(self) -> None:
        self.field_imu_only_enabled = False
        self.notify_operation("IMU慣性推定を停止しました", "info")

    def set_optical_odometry_apply_enabled(self, enabled: bool) -> None:
        self.optical_odometry_state.apply_enabled = bool(enabled)
        state = "開始" if enabled else "停止"
        self.notify_operation(f"光学式オドメトリのR2反映を{state}しました", "success" if enabled else "info")

    def zero_optical_odometry(self) -> None:
        self.optical_odometry_state.zero()
        if hasattr(self, "test_field_widget"):
            self.test_field_widget.update_optical_odometry_status(self.optical_odometry_state.summary())
        self.notify_operation("光学式オドメトリのゼロ点を設定しました", "success")

    def save_optical_odometry_scale(self, axis: str, measured_distance_mm: float) -> None:
        axis_name = str(axis).lower()
        measured = float(measured_distance_mm)
        if axis_name == "x":
            count = abs(float(self.optical_odometry_state.total_x_count))
        else:
            count = abs(float(self.optical_odometry_state.total_y_count))
        if count <= 0.0:
            self.notify_operation("累積countが0です。ゼロ点設定後にセンサを動かしてから保存してください。", "error")
            return
        scale = measured / count
        if axis_name == "x":
            self.optical_odometry_state.config.scale_x_mm_per_count = scale
        else:
            self.optical_odometry_state.config.scale_y_mm_per_count = scale
        try:
            self.optical_odometry_state.config.save()
        except OSError as exc:
            self.notify_operation(f"光学式scale保存失敗: {exc}", "error")
            return
        if hasattr(self, "test_field_widget"):
            self.test_field_widget.update_optical_odometry_status(self.optical_odometry_state.summary())
        self.notify_operation(f"光学式{axis_name.upper()} scaleを保存しました: {scale:.6f} mm/count", "success")

    def _apply_imu_only_field_pose(self, data) -> None:
        if not hasattr(self, "test_field_widget"):
            return
        if not self.imu_state.has_recent_data() or not is_sensor_active(getattr(data, "imu_status", "未接続")):
            return
        if self.imu_inertial_estimator.last_time_s is None:
            if self.real_field_pose_has_data:
                self.imu_inertial_estimator.reset(self.real_field_x_mm, self.real_field_y_mm)
            else:
                self.imu_inertial_estimator.reset(self.real_field_start_pose[0], self.real_field_start_pose[1])
        pose = self.imu_inertial_estimator.update(
            accel_x_g=float(getattr(data, "accel_x_g", 0.0)),
            accel_y_g=float(getattr(data, "accel_y_g", 0.0)),
            yaw_deg=float(getattr(data, "imu_yaw", 0.0)),
            timestamp_s=time.monotonic(),
            field_width_mm=self.test_field_widget.field_model.width_mm,
            field_height_mm=self.test_field_widget.field_model.height_mm,
        )
        self.real_field_x_mm = pose.x_mm
        self.real_field_y_mm = pose.y_mm
        self.real_field_theta_deg = pose.theta_deg
        self.real_field_pose_has_data = True
        self.real_field_last_odom_time = time.monotonic()
        self.real_field_pose_source = "IMU慣性推定"

    def _apply_real_field_pose_message(self, parsed: dict, source_kind: str = "REAL") -> None:
        message_type = parsed.get("type")
        if message_type == "IMU" and self.real_field_pose_has_data and is_sensor_active(self.imu_state.imu_status):
            self.real_field_theta_deg = float(self.imu_state.yaw)
            return
        if source_kind == "REFRESH":
            return
        if message_type in {"ODOM_STATUS", "OPTICAL_STATUS"}:
            self.optical_odometry_state.update_status(parsed.get("status"), source=source_kind)
            return
        if message_type not in {"ODOM", "OPTICAL"}:
            return
        if source_kind != "REAL":
            return

        if not self.real_field_pose_has_data:
            self._reset_real_field_pose(log=False)
            self.real_field_pose_has_data = True

        if message_type == "ODOM":
            if not is_sensor_active(self.imu_state.odom_status):
                return
            x_offset_mm = float(parsed.get("x", 0.0))
            y_offset_mm = float(parsed.get("y", 0.0))
            self.real_field_x_mm = self.real_field_start_pose[0] + x_offset_mm
            self.real_field_y_mm = self.real_field_start_pose[1] + y_offset_mm
            theta = float(parsed.get("theta", self.real_field_theta_deg))
            self.real_field_theta_deg = float(self.imu_state.yaw) if is_sensor_active(self.imu_state.imu_status) else theta
            self.real_field_pose_source = "実機ODOM"
        else:
            converted = self.optical_odometry_state.update_delta(parsed.get("dx", 0.0), parsed.get("dy", 0.0), source=source_kind)
            if converted is None:
                return
            dx_mm, dy_mm = converted
            if is_sensor_active(self.imu_state.imu_status):
                self.real_field_theta_deg = float(self.imu_state.yaw)
            field_dx, field_dy = self.optical_odometry_state.transform_robot_delta_to_field(dx_mm, dy_mm, self.real_field_theta_deg)
            self.real_field_x_mm += field_dx
            self.real_field_y_mm += field_dy
            self.real_field_pose_source = "光学式オドメトリ"
            self.optical_odometry_state.last_applied_time = time.monotonic()

        self.real_field_x_mm = max(0.0, min(self.test_field_widget.field_model.width_mm, self.real_field_x_mm))
        self.real_field_y_mm = max(0.0, min(self.test_field_widget.field_model.height_mm, self.real_field_y_mm))
        self.real_field_last_odom_time = time.monotonic()

    def _reset_real_field_pose(self, log: bool = True, keep_visible: bool = False) -> None:
        if hasattr(self, "test_field_widget"):
            self.real_field_start_pose = self.test_field_widget.r2_start_pose
        self.real_field_x_mm = float(self.real_field_start_pose[0])
        self.real_field_y_mm = float(self.real_field_start_pose[1])
        self.real_field_theta_deg = float(self.real_field_start_pose[2])
        self.real_field_pose_has_data = bool(keep_visible)
        self.real_field_last_odom_time = time.monotonic() if keep_visible else 0.0
        self.real_field_pose_source = "位置リセット" if keep_visible else "R2スタート位置"
        if hasattr(self, "imu_inertial_estimator"):
            self.imu_inertial_estimator.reset(self.real_field_x_mm, self.real_field_y_mm)
        if hasattr(self, "optical_odometry_state"):
            self.optical_odometry_state.zero()
        if hasattr(self, "test_field_widget"):
            self.test_field_widget.update_from_pose(
                "位置リセット",
                self.real_field_x_mm,
                self.real_field_y_mm,
                self.real_field_theta_deg,
                has_data=True,
                source_note="R2位置推定をスタート位置へリセットしました。",
            )
            self.test_field_widget.set_start_to_current()
        if log:
            self._log("R2位置推定をスタート位置へリセットしました")

    def _append_esp32_receive_line(self, line: str) -> None:
        if not line:
            return
        self.esp32_receive_log.appendPlainText(line)
        if line.startswith("MOTOR_DUMMY,"):
            self.last_motor_dummy_text = line
            parts = line.split(",")
            if len(parts) >= 3:
                self.last_motor_left_command = parts[1]
                self.last_motor_right_command = parts[2]
        if self.receive_check_deadline:
            self.receive_check_lines.append(line)

    def connect_esp32_from_ui(self) -> None:
        selected_port = self.com_port_combo.currentData() or self.com_port_combo.currentText().split(" - ")[0].strip()
        if not selected_port:
            self._log("ESP32接続失敗: COMポートが選択されていません")
            self.esp32_connection_label.setText("接続状態: エラー（COMポート未選択）")
            self.notify_operation("ESP32接続失敗: COMポート未選択", "error")
            return
        if self._serial_monitor_uses_port(str(selected_port)):
            self._warn_serial_monitor_conflict()
            return
        baudrate = int(self._serial_config().get("baudrate", 115200))
        self.connection_test_label.setText(f"ESP32接続中: {selected_port}")
        self.notify_operation(f"ESP32へ接続中: {selected_port}", "busy")
        status = self.serial.connect_port(str(selected_port), baudrate=baudrate, mock=False)
        if status.connected and not status.mock:
            self._update_config_ports(str(selected_port))
            self._remember_com_port(str(selected_port), baudrate)
            self.sensor_connected = self.sensor_source == "Real"
            self._log(f"ESP32接続: {selected_port}")
            self.connection_test_label.setText("ESP32接続成功")
            self.notify_operation(f"ESP32接続成功: {selected_port}", "success")
        else:
            self._log(f"ESP32接続失敗: {selected_port}")
            self.connection_test_label.setText("接続テスト: COMポートを開けません")
            self.notify_operation(f"ESP32接続失敗: {selected_port}", "error")
        self._update_esp32_connection_label(status)

    def disconnect_esp32_from_ui(self) -> None:
        status = self.serial.status()
        if status.connected and not status.mock:
            try:
                self.serial.send_command("DRIVE STOP")
            except Exception as exc:
                self._log(f"ESP32切断前の停止指令に失敗: {exc}")
        self.serial.disconnect()
        mode_cfg = cfg_section(self.config, "mode")
        self.serial.mock = bool(mode_cfg.get("use_mock", True))
        self.sensor_connected = False
        self.imu_state.connected = False
        self._log("ESP32切断")
        self.connection_test_label.setText("接続テスト: 未実行")
        self.notify_operation("ESP32を切断しました", "info")
        self._update_esp32_connection_label(self.serial.status())

    def test_esp32_connection(self) -> None:
        status = self.serial.status()
        if not status.connected or status.mock:
            self.connection_test_label.setText("接続テスト失敗：ESP32が未接続です")
            self._log("接続テスト失敗：ESP32が未接続です")
            self.notify_operation("接続テスト失敗: ESP32未接続", "error")
            return
        self.connection_test_label.setText("接続テスト: STATUS,OKを待っています")
        self.notify_operation("接続テスト中: STATUS,OKを待っています", "busy")
        self._send_esp32_line("STATUS?", "接続テスト")
        QTimer.singleShot(1500, self._finish_esp32_connection_test)

    def _finish_esp32_connection_test(self) -> None:
        connection_status = self.connection_manager.drive_status()
        last_line = connection_status.last_received_line
        if self.last_serial_status_text == "OK" or self._is_connection_signal(last_line) or self._is_connection_signal(self.last_connection_signal_line):
            self.connection_test_label.setText("接続テスト成功：ESP32から信号を受信しました")
            self._log("接続テスト成功：ESP32から信号を受信しました")
            self.notify_operation("接続テスト成功: ESP32から信号を受信しました", "success")
            return
        self.connection_test_label.setText("接続テスト失敗：STATUSが受信できません")
        self._log("接続テスト失敗：STATUSが受信できません")
        self.notify_operation("接続テスト失敗: STATUSが受信できません", "error")

    def _is_connection_signal(self, line: str) -> bool:
        return line.startswith((
            "BOOT,DRIVE_CONTROLLER_READY",
            "STATUS,OK",
            "IMU_STATUS,",
            "IMU,",
            "GYRO,",
            "LIDAR_STATUS,",
            "LIDAR,",
            "ENC,",
            "MOTOR_DUMMY,",
            "FW,",
        ))

    def _reset_quick_check_items(self) -> None:
        self.quick_check_items = {
            key: {"status": "未確認", "detail": ""}
            for key in ["esp32", "status", "imu", "lidar", "encoder", "motor", "test_send", "stop_send"]
        }
        self._update_quick_check_labels()

    def _set_quick_item(self, key: str, status: str, detail: str = "") -> None:
        self.quick_check_items[key] = {"status": status, "detail": detail}
        self._update_quick_check_labels()

    def _update_quick_check_labels(self) -> None:
        titles = {
            "esp32": "ESP32接続",
            "status": "STATUS受信",
            "imu": "IMU受信",
            "lidar": "LiDAR受信",
            "encoder": "エンコーダ受信",
            "motor": "モータダミー受信",
            "test_send": "テスト送信",
            "stop_send": "STOP送信",
        }
        colors = {
            "OK": "#86efac",
            "未確認": "#fef08a",
            "確認中": "#dbeafe",
            "失敗": "#fca5a5",
        }
        for key, label in self.quick_check_item_labels.items():
            item = self.quick_check_items.get(key, {"status": "未確認", "detail": ""})
            text = f"{titles[key]}: {item['status']}"
            if item.get("detail"):
                text += f"（{item['detail']}）"
            label.setText(text)
            label.setStyleSheet(f"color:{colors.get(item['status'], '#e5edf5')};")

    def start_quick_hardware_check(self) -> None:
        if self.quick_check_active:
            self._log("実機クイック確認は実行中です")
            self.notify_operation("実機クイック確認は実行中です。完了までお待ちください。", "busy")
            return
        if self._serial_monitor_uses_port():
            self._warn_serial_monitor_conflict()
            return
        if hasattr(self, "quick_check_run_button"):
            set_busy(self.quick_check_run_button, "確認中...")
        self._reset_quick_check_items()
        self.quick_check_active = True
        self.quick_check_phase = "connect"
        self.quick_check_alive_received = False
        self.quick_check_drive_response = False
        self.quick_check_stop_response = False
        self.quick_check_raw_lines = []
        self.quick_check_result_label.setText("最終確認結果: 実行中")
        self.quick_check_time_label.setText(f"最終確認時刻: {time.strftime('%H:%M:%S')}")
        self._set_quick_item("esp32", "確認中", "COM確認中")
        self._log("実機クイック確認を開始しました")
        self.notify_operation("実機クイック確認を開始しました", "busy")
        self._quick_check_tick()

    def _quick_check_tick(self) -> None:
        if not self.quick_check_active:
            return
        try:
            now = time.monotonic()
            if self.quick_check_phase == "connect":
                self._quick_check_connect()
                return
            if self.quick_check_phase == "wait_alive":
                passive_ok = all(
                    self.quick_check_items[key]["status"] == "OK"
                    for key in ["status", "imu", "lidar", "encoder"]
                )
                if passive_ok:
                    self._quick_check_send_test()
                    return
                if now >= self.quick_check_deadline:
                    if not self.quick_check_alive_received:
                        self._quick_check_fail("ESP32から生存信号を受信できませんでした")
                        return
                    self._quick_check_send_test()
                    return
            elif self.quick_check_phase == "wait_test_response":
                if self.quick_check_drive_response:
                    self._quick_check_send_stop()
                    return
                if now >= self.quick_check_deadline:
                    self._set_quick_item("test_send", "失敗", "応答なし")
                    self._quick_check_send_stop()
                    return
            elif self.quick_check_phase == "wait_stop_response":
                if self.quick_check_stop_response:
                    self._quick_check_finish()
                    return
                if now >= self.quick_check_deadline:
                    self._set_quick_item("stop_send", "失敗", "応答なし")
                    self._quick_check_finish()
                    return
        except Exception as exc:
            self._quick_check_fail(f"実機クイック確認でエラーが発生しました: {exc}")
            return
        QTimer.singleShot(100, self._quick_check_tick)

    def _quick_check_connect(self) -> None:
        self._set_quick_item("esp32", "確認中", "接続確認中")
        status = self.serial.status()
        if status.connected and not status.mock:
            self._set_quick_item("esp32", "OK", self.serial.port)
            self.quick_check_connection_label.setText("ESP32接続状態: 接続済み")
            self.quick_check_com_label.setText(f"使用COMポート: {self.serial.port}")
            self.quick_check_phase = "wait_alive"
            self.quick_check_deadline = time.monotonic() + 5.0
            self._log("ESP32接続済みです。生存信号を待っています")
            QTimer.singleShot(100, self._quick_check_tick)
            return

        self._log("COMポートを更新しました")
        self.refresh_com_ports(log_result=False)
        try:
            ports = detect_ports()
        except Exception:
            ports = []
        likely = next((port for port in ports if port.is_likely_esp32), None)
        if likely is not None:
            index = self.com_port_combo.findData(likely.port)
            if index >= 0:
                self.com_port_combo.setCurrentIndex(index)
            selected_port = likely.port
            self._log(f"ESP32候補を自動選択: {selected_port}")
        else:
            selected_port = self.com_port_combo.currentData() or self.com_port_combo.currentText().split(" - ")[0].strip()
        if not selected_port:
            self._quick_check_fail("COMポートが選択されていません")
            return
        if self._serial_monitor_uses_port(str(selected_port)):
            self._quick_check_fail("シリアルモニタがCOMポートを使用中です。先にシリアルモニタを切断してください。")
            self._warn_serial_monitor_conflict()
            return

        baudrate = int(self._serial_config().get("baudrate", 115200))
        self._set_quick_item("esp32", "確認中", f"{selected_port} 接続中")
        connect_status = self.serial.connect_port(str(selected_port), baudrate=baudrate, mock=False)
        self._update_esp32_connection_label(connect_status)
        if not connect_status.connected or connect_status.mock:
            self._quick_check_fail("COMポートを開けませんでした")
            return
        self._update_config_ports(str(selected_port))
        self._set_quick_item("esp32", "OK", str(selected_port))
        self.quick_check_connection_label.setText("ESP32接続状態: 接続済み")
        self.quick_check_com_label.setText(f"使用COMポート: {selected_port}")
        self._log("ESP32へ接続しました")
        self._set_quick_item("status", "確認中", "生存信号待ち")
        self.quick_check_phase = "wait_alive"
        self.quick_check_deadline = time.monotonic() + 5.0
        QTimer.singleShot(100, self._quick_check_tick)

    def _handle_quick_check_line(self, line: str) -> None:
        if not self.quick_check_active or not line:
            return
        self.quick_check_raw_lines.append(line)
        if self._is_quick_alive_signal(line):
            self.quick_check_alive_received = True
        if line.startswith("STATUS,OK") or line.startswith("BOOT,DRIVE_CONTROLLER_READY"):
            self._set_quick_item("status", "OK")
        elif line.startswith("IMU_STATUS,DUMMY"):
            self._set_quick_item("imu", "OK", "ESP32ダミー出力")
        elif line.startswith("IMU_STATUS,OK") or line.startswith("IMU,"):
            self._set_quick_item("imu", "OK")
        elif line.startswith("LIDAR_STATUS,DUMMY"):
            self._set_quick_item("lidar", "OK", "ESP32ダミー出力")
        elif line.startswith("LIDAR_STATUS,OK") or line.startswith("LIDAR,"):
            self._set_quick_item("lidar", "OK")
        elif line.startswith("ENC,"):
            self._set_quick_item("encoder", "OK")

        if line.startswith("MOTOR_DUMMY,"):
            self._set_quick_item("motor", "OK", "モータ出力は無効（安全ダミー）")
            if line.startswith("MOTOR_DUMMY,50,50"):
                self.quick_check_drive_response = True
            elif line.startswith("MOTOR_DUMMY,0,0"):
                self.quick_check_stop_response = True
        if line.startswith("RX,DRIVE VEL 50 50") or line.startswith("DRIVE,50,50"):
            self.quick_check_drive_response = True
            if line.startswith("DRIVE,50,50") and self.quick_check_items.get("motor", {}).get("status") != "OK":
                self._set_quick_item("motor", "OK", "DRIVE応答")
        if line.startswith("RX,DRIVE STOP") or line.startswith("DRIVE,0,0"):
            self.quick_check_stop_response = True
            if line.startswith("DRIVE,0,0") and self.quick_check_items.get("motor", {}).get("status") != "OK":
                self._set_quick_item("motor", "OK", "DRIVE応答")

    def _is_quick_alive_signal(self, line: str) -> bool:
        return line.startswith((
            "BOOT,DRIVE_CONTROLLER_READY",
            "STATUS,OK",
            "IMU_STATUS,DUMMY",
            "IMU_STATUS,OK",
            "LIDAR_STATUS,DUMMY",
            "LIDAR_STATUS,OK",
            "IMU,",
            "GYRO,",
            "ENC,",
            "LIDAR,",
        ))

    def _quick_check_send_test(self) -> None:
        if self.quick_check_phase == "wait_test_response":
            return
        self._set_quick_item("test_send", "確認中", "DRIVE VEL 50 50")
        self._log("テスト送信しました: DRIVE VEL 50 50")
        self._append_quick_check_log_line("テスト送信: DRIVE VEL 50 50")
        result = self._send_esp32_line("DRIVE VEL 50 50", "実機クイック確認テスト送信")
        if result:
            self._set_quick_item("test_send", "OK", "DRIVE VEL 50 50")
            self.quick_check_phase = "wait_test_response"
            self.quick_check_deadline = time.monotonic() + 2.0
        else:
            self._set_quick_item("test_send", "失敗", "送信失敗")
            self._quick_check_send_stop()
            return
        QTimer.singleShot(100, self._quick_check_tick)

    def _quick_check_send_stop(self) -> None:
        self._set_quick_item("stop_send", "確認中", "DRIVE STOP")
        self._log("STOP送信しました")
        self._append_quick_check_log_line("STOP送信: DRIVE STOP")
        result = self._send_esp32_line("DRIVE STOP", "実機クイック確認STOP送信")
        if result:
            self._set_quick_item("stop_send", "OK", "DRIVE STOP")
        else:
            self._set_quick_item("stop_send", "失敗", "送信失敗")
        self.quick_check_phase = "wait_stop_response"
        self.quick_check_deadline = time.monotonic() + 2.0
        QTimer.singleShot(100, self._quick_check_tick)

    def _quick_check_fail(self, message: str) -> None:
        status = self.serial.status()
        if status.connected and not status.mock:
            self._send_esp32_line("DRIVE STOP", "実機クイック確認失敗時STOP")
            self._log("STOP送信を実行しました")
        if self.quick_check_items.get("esp32", {}).get("status") != "OK":
            self._set_quick_item("esp32", "失敗", message)
        self.quick_check_active = False
        self.quick_check_phase = "idle"
        self.quick_check_result_label.setText(f"最終確認結果: 失敗 - {message}")
        self.quick_check_time_label.setText(f"最終確認時刻: {time.strftime('%H:%M:%S')}")
        self.connection_test_label.setText(f"実機クイック確認: 失敗 - {message}")
        self._log(f"実機クイック確認に失敗しました: {message}")
        self.notify_operation(f"実機クイック確認に失敗しました: {message}", "error")
        self._append_quick_check_log_line(f"失敗: {message}")
        self._save_quick_check_result("failure", message)
        if hasattr(self, "quick_check_run_button"):
            clear_busy(self.quick_check_run_button)

    def _quick_check_finish(self) -> None:
        missing = [
            key
            for key in ["esp32", "status", "imu", "lidar", "encoder", "motor", "test_send", "stop_send"]
            if self.quick_check_items.get(key, {}).get("status") != "OK"
        ]
        self.quick_check_active = False
        self.quick_check_phase = "idle"
        self.quick_check_time_label.setText(f"最終確認時刻: {time.strftime('%H:%M:%S')}")
        if missing:
            for key in missing:
                if self.quick_check_items.get(key, {}).get("status") == "未確認":
                    self._set_quick_item(key, "失敗", "未確認")
            self.quick_check_result_label.setText("最終確認結果: 一部失敗")
            self.connection_test_label.setText("実機クイック確認: 一部失敗")
            self._log("実機クイック確認は一部失敗しました")
            self.notify_operation("実機クイック確認は一部失敗しました", "error")
            self._append_quick_check_log_line("一部失敗")
            self._save_quick_check_result("partial_failure", "一部の項目を確認できませんでした")
        else:
            self.quick_check_result_label.setText("最終確認結果: 成功")
            self.connection_test_label.setText("実機クイック確認: 成功")
            self._log("実機クイック確認に成功しました")
            self.notify_operation("実機クイック確認に成功しました", "success")
            self._append_quick_check_log_line("成功")
            self._save_quick_check_result("success", "")
        if hasattr(self, "quick_check_run_button"):
            clear_busy(self.quick_check_run_button)

    def _append_quick_check_log_line(self, message: str) -> None:
        self.esp32_receive_log.appendPlainText(f"[実機クイック確認] {message}")

    def _safety_checklist_state(self) -> dict[str, bool]:
        return {checkbox.text(): checkbox.isChecked() for checkbox in self.safety_checkboxes}

    def reset_real_hardware_safety_checks(self) -> None:
        for checkbox in self.safety_checkboxes:
            checkbox.setChecked(False)
        self._log("実機接続前チェックリストをリセットしました")

    def open_project_file(self, relative_path: str) -> None:
        path = self._project_root() / relative_path
        try:
            if not path.exists():
                self._log(f"ファイルが見つかりません: {path}")
                return
            os.startfile(str(path))
            self._log(f"ファイルを開きました: {path}")
        except Exception as exc:
            self._log(f"ファイルを開けませんでした: {exc}")

    def _save_quick_check_result(self, final_result: str, error_message: str) -> None:
        try:
            self.notify_operation("実機確認結果を保存中...", "busy")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            result = self._build_hardware_check_result(timestamp, final_result, error_message)
            json_path, txt_path = HardwareCheckLogger(self._project_root()).save(result)
            self.latest_hardware_check_json_path = str(json_path)
            self.latest_hardware_check_txt_path = str(txt_path)
            self._update_latest_hardware_result_label(result, json_path, txt_path)
            self._log(f"実機確認結果を保存しました: {txt_path}")
            self.notify_operation("実機確認結果を保存しました", "success")
        except Exception as exc:
            self._log(f"実機確認結果の保存に失敗しました: {exc}")
            self.notify_operation(f"実機確認結果の保存に失敗しました: {exc}", "error")

    def _build_hardware_check_result(self, timestamp: str, final_result: str, error_message: str) -> HardwareCheckResult:
        return HardwareCheckResult(
            timestamp=timestamp,
            selected_com_port=str(self.serial.port),
            baudrate=int(self.serial.baudrate),
            esp32_connected=self.quick_check_items.get("esp32", {}).get("status") == "OK",
            status_received=self.quick_check_items.get("status", {}).get("status") == "OK",
            imu_received=self.quick_check_items.get("imu", {}).get("status") == "OK",
            imu_status=self._quick_sensor_status("imu"),
            lidar_received=self.quick_check_items.get("lidar", {}).get("status") == "OK",
            lidar_status=self._quick_sensor_status("lidar"),
            encoder_received=self.quick_check_items.get("encoder", {}).get("status") == "OK",
            motor_dummy_received=self.quick_check_items.get("motor", {}).get("status") == "OK",
            test_command_sent=self.quick_check_items.get("test_send", {}).get("status") == "OK",
            test_response_received=self.quick_check_drive_response,
            stop_sent=self.quick_check_items.get("stop_send", {}).get("status") == "OK",
            stop_response_received=self.quick_check_stop_response,
            final_result=final_result,
            error_message=error_message,
            raw_lines=list(self.quick_check_raw_lines),
            hardware_profile_summary=self.hardware_profile.to_summary_text(),
            safety_checklist=self._safety_checklist_state(),
            motor_output_enabled="0",
            use_real_imu="0",
            use_real_lidar="0",
        )

    def _quick_sensor_status(self, key: str) -> str:
        item = self.quick_check_items.get(key, {})
        if item.get("status") != "OK":
            return "no_data"
        detail = item.get("detail", "")
        if "ダミー" in detail:
            return "dummy"
        return "ok"

    def _update_latest_hardware_result_label(
        self,
        result: HardwareCheckResult | None = None,
        json_path: Path | None = None,
        txt_path: Path | None = None,
    ) -> None:
        if result is None:
            latest = HardwareCheckLogger(self._project_root()).latest_text_file()
            if latest is None:
                self._set_latest_hardware_result_text("前回の実機確認結果: なし")
                return
            self.latest_hardware_check_txt_path = str(latest)
            self._set_latest_hardware_result_text(
                "前回の実機確認結果:\n"
                f"保存先: {latest}"
            )
            return
        self.latest_hardware_check_json_path = str(json_path or "")
        self.latest_hardware_check_txt_path = str(txt_path or "")
        self._set_latest_hardware_result_text(
            "前回の実機確認結果:\n"
            f"最終実行時刻: {result.timestamp}\n"
            f"結果: {result.result_text()}\n"
            f"COMポート: {result.selected_com_port}\n"
            f"保存先: {txt_path}"
        )

    def _set_latest_hardware_result_text(self, text: str) -> None:
        self.latest_hardware_result_label.setText(text)
        if hasattr(self, "latest_hardware_result_log_label"):
            self.latest_hardware_result_log_label.setText(text)

    def _card_value_text(self, key: str) -> str:
        cards = self.machine_cards.get(key, [])
        if not cards:
            return "-"
        card = cards[0]
        status = card.get("状態").text() if card.get("状態") else "-"
        value = card.get("値").text() if card.get("値") else "-"
        source = card.get("データ種別").text() if card.get("データ種別") else "-"
        return f"{status} / {value} / {source}"

    def open_hardware_check_folder(self) -> None:
        folder = self._project_root() / "logs" / "hardware_checks"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
            self._log(f"実機確認結果フォルダを開きました: {folder}")
        except Exception as exc:
            self._log(f"実機確認結果フォルダを開けませんでした: {exc}")

    def open_latest_hardware_check_result(self) -> None:
        path = Path(self.latest_hardware_check_txt_path) if self.latest_hardware_check_txt_path else None
        if path is None or not path.exists():
            path = HardwareCheckLogger(self._project_root()).latest_text_file()
        if path is None or not path.exists():
            self._log("開ける実機確認結果がありません")
            return
        try:
            os.startfile(str(path))
            self._log(f"最新の実機確認結果を開きました: {path}")
        except Exception as exc:
            self._log(f"最新の実機確認結果を開けませんでした: {exc}")

    def copy_latest_hardware_check_result(self) -> None:
        path = Path(self.latest_hardware_check_txt_path) if self.latest_hardware_check_txt_path else None
        if path is None or not path.exists():
            path = HardwareCheckLogger(self._project_root()).latest_text_file()
        if path is None or not path.exists():
            self._log("コピーできる実機確認結果がありません")
            return
        try:
            text = path.read_text(encoding="utf-8")
            QApplication.clipboard().setText(text)
            self._log("最新の実機確認結果をクリップボードへコピーしました")
        except Exception as exc:
            self._log(f"実機確認結果のコピーに失敗しました: {exc}")

    def start_esp32_receive_check(self) -> None:
        status = self.serial.status()
        if not status.connected or status.mock:
            self.connection_test_label.setText("受信確認失敗：ESP32が未接続です")
            self._log("受信確認失敗：ESP32が未接続です")
            self.notify_operation("受信確認失敗: ESP32未接続", "error")
            return
        self.receive_check_lines = []
        self.receive_check_deadline = time.monotonic() + 2.0
        self.connection_test_label.setText("受信確認開始")
        self._log("受信確認開始")
        self.notify_operation("受信確認中...", "busy")
        self._poll_receive_check()

    def _poll_receive_check(self) -> None:
        if not self.receive_check_deadline:
            return
        if time.monotonic() >= self.receive_check_deadline:
            self.receive_check_deadline = 0.0
            if self.receive_check_lines:
                self.connection_test_label.setText(f"受信確認完了：{len(self.receive_check_lines)}行")
                self._log("受信確認完了")
                self.notify_operation(f"受信確認完了: {len(self.receive_check_lines)}行", "success")
            else:
                self.connection_test_label.setText("受信なし")
                self._log("受信なし")
                self.notify_operation("受信確認完了: 受信なし", "error")
            return
        QTimer.singleShot(100, self._poll_receive_check)

    def send_esp32_test_command(self) -> None:
        status = self.serial.status()
        if not status.connected or status.mock:
            self.connection_test_label.setText("テスト送信失敗：ESP32が未接続です")
            self._log("テスト送信失敗：ESP32が未接続です")
            self.notify_operation("テスト送信失敗: ESP32未接続", "error")
            return
        self.test_send_waiting = True
        result = self._send_esp32_line("DRIVE VEL 50 50", "テスト送信")
        if not result:
            self.test_send_waiting = False
            self.connection_test_label.setText("テスト送信失敗")
            self.notify_operation("テスト送信失敗", "error")
            return
        self.connection_test_label.setText("テスト送信中：応答待ち")
        self.notify_operation("テスト送信中: 応答待ち", "busy")
        QTimer.singleShot(1200, self._finish_esp32_test_send)

    def _finish_esp32_test_send(self) -> None:
        if not self.test_send_waiting:
            return
        self.test_send_waiting = False
        self._send_esp32_line("DRIVE STOP", "テスト後停止")
        self.connection_test_label.setText("テスト送信失敗")
        self._log("テスト送信失敗")
        self.notify_operation("テスト送信失敗: 応答がありません", "error")

    def send_esp32_stop_command(self) -> None:
        status = self.serial.status()
        if not status.connected or status.mock:
            self.connection_test_label.setText("停止送信失敗：ESP32が未接続です")
            self._log("停止送信失敗：ESP32が未接続です")
            self.notify_operation("停止送信失敗: ESP32未接続", "error")
            return
        if self._send_esp32_line("DRIVE STOP", "停止送信"):
            self.connection_test_label.setText("停止指令を送信しました")
            self._log("停止指令を送信しました")
            self.notify_operation("停止指令を送信しました", "success")

    def _send_esp32_line(self, text: str, label: str) -> bool:
        result = self.connection_manager.send_drive_command(text)
        self.last_esp32_sent_text = text
        self._update_esp32_connection_label(self.serial.status())
        if result.success:
            self._log(f"{label}: {text}")
            return True
        self._log(f"{label}失敗: {result.message}")
        return False

    def save_selected_com_port(self) -> None:
        selected_port = self.com_port_combo.currentData() or self.com_port_combo.currentText().split(" - ")[0].strip()
        if not selected_port:
            self._log("設定保存失敗: COMポートが選択されていません")
            self.notify_operation("設定保存失敗: COMポート未選択", "error")
            return
        self._update_config_ports(str(selected_port))
        self._remember_com_port(str(selected_port), int(self._serial_config().get("baudrate", 115200)))
        save_config(self.config)
        self._log(f"設定に保存: {selected_port}")
        self.notify_operation(f"COMポート設定を保存しました: {selected_port}", "success")

    def _update_config_ports(self, port: str) -> None:
        communication = self.config.setdefault("communication", {})
        usb = communication.setdefault("usb", {})
        usb["port"] = port
        controllers = self.config.setdefault("controllers", {})
        drive = controllers.setdefault("drive", {})
        drive["port"] = port
        serial_cfg = self.config.setdefault("serial", {})
        serial_cfg["port"] = port

    def _remember_com_port(self, port: str, baudrate: int) -> None:
        self.local_settings["last_com_port"] = port
        self.local_settings["last_baudrate"] = int(baudrate)
        self._save_local_settings()

    def _handle_com_port_selection_changed(self) -> None:
        selected_port = self.com_port_combo.currentData() or self.com_port_combo.currentText().split(" - ")[0].strip()
        if selected_port:
            self._remember_com_port(str(selected_port), int(self._serial_config().get("baudrate", 115200)))

    def _update_esp32_connection_label(self, esp32_status) -> None:
        connection_status = self.connection_manager.drive_status()
        if esp32_status.connected and not esp32_status.mock:
            text = f"接続状態: 接続済み / データ種別: 実通信 / COMポート: {self.serial.port}"
            color = "#86efac"
            header_text = f"ESP32接続状態: 接続中 ({self.serial.port})"
        elif esp32_status.mock:
            text = f"接続状態: 未接続 / データ種別: Mock通信 / COMポート: {self.serial.port}"
            color = "#fde68a"
            header_text = "ESP32接続状態: 未接続（Mock通信）"
        else:
            text = f"接続状態: エラー / データ種別: データなし / COMポート: {self.serial.port}"
            color = "#fdba74"
            header_text = "ESP32接続状態: エラー"
        self.esp32_connection_label.setText(text)
        self.esp32_connection_label.setStyleSheet(f"color:{color}; font-weight:800;")
        self.real_esp32_connection_label.setText(text)
        self.real_esp32_connection_label.setStyleSheet(f"color:{color}; font-weight:800;")
        self.header_esp32_label.setText(header_text)
        self.header_esp32_label.setStyleSheet(f"color:{color}; font-size:16px; font-weight:800;")
        last_time = "-"
        if connection_status.last_received_time:
            last_time = time.strftime("%H:%M:%S", time.localtime(connection_status.last_received_time))
        self.esp32_connection_detail_label.setText(
            f"選択COMポート: {self.serial.port}\n"
            f"通信速度: {self.serial.baudrate}\n"
            f"最終受信: {connection_status.last_received_line or '-'}\n"
            f"最終受信時刻: {last_time}\n"
            f"最終送信: {self.last_esp32_sent_text}\n"
            f"受信行数: {connection_status.received_line_count}"
        )
        self.real_esp32_connection_detail_label.setText(self.esp32_connection_detail_label.text())

    def start_logging(self) -> None:
        if self.csv_logger.active:
            self._log("ログはすでに記録中です")
            return
        path = self.csv_logger.start()
        self._log(f"ログ開始: {path}")

    def stop_logging(self) -> None:
        if not self.csv_logger.active:
            self._log("ログは記録されていません")
            return
        self.csv_logger.stop()
        self._log("ログ停止")

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_view.appendPlainText(line)
        self.machine_log_view.appendPlainText(line)

    def _diagnostic_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.diagnostics_log_view.appendPlainText(f"[{timestamp}] {message}")

    def clear_visible_logs(self) -> None:
        self.esp32_receive_log.clear()
        self.log_view.clear()
        self.machine_log_view.clear()
        self.diagnostics_log_view.clear()
        self._log("ログを消去しました")

    def copy_visible_logs(self) -> None:
        text = "\n\n".join(
            [
                "=== ESP32受信ログ ===",
                self.esp32_receive_log.toPlainText(),
                "=== 操作ログ ===",
                self.log_view.toPlainText(),
                "=== 診断ログ ===",
                self.diagnostics_log_view.toPlainText(),
            ]
        )
        QApplication.clipboard().setText(text)
        self._log("ログをクリップボードへコピーしました")

    def _update_machine_cards(self, data, esp32_status, show_sensor_values: bool) -> None:
        if esp32_status.connected and not esp32_status.mock:
            esp32_state = "接続中"
            esp32_type = "実通信"
        elif esp32_status.mock:
            esp32_state = "未接続"
            esp32_type = "Mock通信"
        else:
            esp32_state = "エラー" if esp32_status.error else "未接続"
            esp32_type = "データなし"
        self._set_card(
            "esp32",
            esp32_state,
            f"COM: {self.serial.port} / 速度: {self.serial.baudrate}",
            esp32_type,
        )
        self._update_pre_operation_check_card(esp32_state)
        self._set_card("mode", self.mode_name, self.mode_description, "設定")
        self._set_card("safety", self.safety_label.text().replace("安全状態: ", ""), self.current_command, "安全監視")
        self._set_card("quick", self.quick_check_result_label.text().replace("最終確認結果: ", ""), self.quick_check_time_label.text().replace("最終確認時刻: ", ""), "結果保存")
        firmware_value = f"{self.firmware_name} {self.firmware_version}".strip() if self.firmware_name else "未確認"
        self._set_card("firmware", "受信済み" if self.firmware_name else "未確認", firmware_value, "受信情報")
        wiring_path = self.latest_wiring_report_txt_path or str(self._project_root() / "logs" / "wiring_reports" / "latest_wiring_report.txt")
        wiring_exists = Path(wiring_path).exists()
        self._set_card("wiring", "作成済み" if wiring_exists else "未作成", wiring_path if wiring_exists else "-", "配線表")
        latest_log = self.log_view.toPlainText().splitlines()[-1] if self.log_view.toPlainText().splitlines() else "-"
        self._set_card("log", "表示中", latest_log, "操作ログ")

        if not show_sensor_values:
            self._set_card("imu", "未接続", "yaw 0.0 / pitch 0.0 / roll 0.0\ngyro x 0.00 / y 0.00 / z 0.00", "0表示")
            self._set_card("lidar", "未接続", "前方 0 mm / 左 0 mm\n右 0 mm / 後方 0 mm", "0表示")
            self._set_card("encoder", "未接続", "左エンコーダ 0 / 右エンコーダ 0", "0表示")
        else:
            imu_status, imu_type = self._status_and_type(data.imu_status, self.sensor_source, data.imu_source)
            self._set_card(
                "imu",
                imu_status,
                f"yaw {data.imu_yaw:.1f} / pitch {data.imu_pitch:.1f} / roll {data.imu_roll:.1f}\n"
                f"gyro x {data.gyro_x:.2f} / y {data.gyro_y:.2f} / z {data.gyro_z:.2f}",
                imu_type,
            )
            lidar_status, lidar_type = self._status_and_type(data.lidar_status, self.sensor_source, data.lidar_source)
            self._set_card(
                "lidar",
                lidar_status,
                f"前方 {data.lidar_front_mm:.0f} mm / 左 {data.lidar_left_mm:.0f} mm\n"
                f"右 {data.lidar_right_mm:.0f} mm / 後方 {data.lidar_rear_mm:.0f} mm",
                lidar_type,
            )
            encoder_status, encoder_type = self._status_and_type(getattr(data, "encoder_status", "未接続"), self.sensor_source, "")
            self._set_card(
                "encoder",
                encoder_status,
                f"左エンコーダ {data.encoder_left} / 右エンコーダ {data.encoder_right}",
                encoder_type,
            )

        if self.last_motor_dummy_text != "-":
            motor_value = f"左指令 {self.last_motor_left_command} / 右指令 {self.last_motor_right_command}"
        else:
            motor_value = "MOTOR_DUMMY未受信"
        self._set_card("motor", "停止中", motor_value, "無効（安全ダミー）")
        command_status = "緊急停止中" if self.current_command == "EMERGENCY_STOP" else "送信済み"
        if self.current_command in {"DRIVE VEL 0 0", "DRIVE STOP"}:
            command_status = "停止中"
        self._set_card("command", command_status, self.current_command, "PC指令")
        if hasattr(self, "motor_status_label"):
            self.motor_status_label.setText(
                "モータ出力：無効（安全ダミー）\n"
                f"左指令: {self.last_motor_left_command}\n"
                f"右指令: {self.last_motor_right_command}\n"
                f"MOTOR_DUMMY: {self.last_motor_dummy_text}"
            )
        if hasattr(self, "drive_status_label"):
            left = "-"
            right = "-"
            parts = self.current_command.split()
            if len(parts) >= 4 and parts[:2] == ["DRIVE", "VEL"]:
                left, right = parts[2], parts[3]
            elif self.current_command in {"DRIVE STOP", "EMERGENCY_STOP"}:
                left, right = "0", "0"
            self.drive_status_label.setText(
                f"現在指令: {self.current_command}\n"
                f"左速度指令: {left}\n"
                f"右速度指令: {right}"
            )

    def _update_home_status(self, data, esp32_status, show_sensor_values: bool) -> None:
        if not hasattr(self, "home_status_label"):
            return
        if esp32_status.connected and not esp32_status.mock:
            esp32_text = "接続中"
        elif self.imu_state.has_recent_data():
            esp32_text = "シリアル受信中"
        else:
            esp32_text = "未接続"
        imu_text = "OK" if show_sensor_values and is_sensor_active(getattr(data, "imu_status", "未接続")) else "未接続"
        lidar_text = "OK" if show_sensor_values and is_sensor_active(getattr(data, "lidar_status", "未接続")) else "未接続"
        odom_text = "OK" if show_sensor_values and is_sensor_active(getattr(data, "odom_status", "未接続")) else "未接続"
        r2_text = "表示中" if hasattr(self, "test_field_widget") and getattr(self.test_field_widget, "state", None) and self.test_field_widget.state.has_data else "準備中"
        firmware_text = f"{self.firmware_name} {self.firmware_version}".strip() if self.firmware_name else "未確認"
        dummy_note = ""
        if show_sensor_values and any(status_label(getattr(data, attr, "未接続")) == "DUMMY" for attr in ["imu_status", "lidar_status", "encoder_status", "odom_status"]):
            dummy_note = "\nDUMMY受信中: 実センサ値ではなく0表示扱い"
        self.home_status_label.setText(
            "システム状態\n"
            f"ESP32: {esp32_text}\n"
            f"IMU: {imu_text} / LiDAR: {lidar_text} / 光学式オドメトリ: {odom_text}\n"
            f"R2位置推定: {r2_text}\n"
            f"現在ファームウェア: {firmware_text}"
            f"{dummy_note}"
        )

    def _update_pre_operation_check_card(self, esp32_state: str) -> None:
        motor_flag = self.firmware_safety_flags.get("MOTOR_OUTPUT_ENABLED", "不明")
        imu_flag = self.firmware_safety_flags.get("USE_REAL_IMU", "不明")
        lidar_flag = self.firmware_safety_flags.get("USE_REAL_LIDAR", "不明")
        emergency_active = self.safety_layer.emergency_stop_active or self.current_command == "EMERGENCY_STOP"

        if motor_flag == "0":
            motor_text = "OFF（安全：実モータ出力なし）"
            motor_style = "color:#86efac; font-size:22px; font-weight:900;"
        elif motor_flag == "1":
            motor_text = "ON（注意：実モータ出力有効）"
            motor_style = "color:#fca5a5; font-size:22px; font-weight:900;"
        else:
            motor_text = f"不明（値: {motor_flag}）"
            motor_style = "color:#fde68a; font-size:22px; font-weight:900;"

        values = {
            "MOTOR_OUTPUT_ENABLED": motor_text,
            "USE_REAL_IMU": "実IMU有効" if imu_flag == "1" else "ダミー / 未接続扱い" if imu_flag == "0" else f"不明（値: {imu_flag}）",
            "USE_REAL_LIDAR": "実LiDAR有効" if lidar_flag == "1" else "ダミー / 未接続扱い" if lidar_flag == "0" else f"不明（値: {lidar_flag}）",
            "ESP32接続状態": esp32_state,
            "緊急停止状態": "作動中" if emergency_active else "未作動",
        }
        styles = {
            "MOTOR_OUTPUT_ENABLED": motor_style,
            "USE_REAL_IMU": "color:#cbd5e1;",
            "USE_REAL_LIDAR": "color:#cbd5e1;",
            "ESP32接続状態": "color:#86efac;" if esp32_state == "接続中" else "color:#fde68a;",
            "緊急停止状態": "color:#fca5a5; font-weight:900;" if emergency_active else "color:#86efac; font-weight:900;",
        }
        self._set_card_rows("pre_operation_check", values, styles)

    def _update_workflow_state(self) -> None:
        status = self.serial.status()
        port_found = bool(self.serial.port)
        quick_ok = "成功" in self.quick_check_result_label.text()
        saved = bool(self.latest_hardware_check_txt_path)
        states = {
            "usb": "OK" if port_found else "未実行",
            "board": "OK" if self.board_list_checked else "未実行",
            "compile": "OK" if self.compile_checked and self.compile_ok else "失敗" if self.compile_checked else "未実行",
            "upload": "OK" if self.upload_checked and self.upload_ok else "失敗" if self.upload_checked else "未実行",
            "reconnect": "OK" if status.connected and not status.mock else "未実行",
            "quick": "OK" if quick_ok else "未実行",
            "save": "OK" if saved else "未実行",
        }
        for key, text in states.items():
            label = self.workflow_step_labels.get(key)
            if label:
                label.setText(text)

        if not port_found:
            next_action = "ESP32をUSB接続して、診断タブでボード一覧更新を押してください。"
        elif not self.board_list_checked:
            next_action = "診断タブでボード一覧更新を押してください。"
        elif not self.compile_checked:
            next_action = "診断タブでコンパイル確認を実行してください。"
        elif self.compile_checked and not self.compile_ok:
            next_action = "コンパイルログを確認し、FQBNやESP32 coreを見直してください。"
        elif not self.upload_checked:
            next_action = "必要なら安全確認後にESP32へ書き込みます。書き込み不要なら実機接続へ進んでください。"
        elif self.upload_ok and not (status.connected and not status.mock):
            next_action = "書き込み後です。実機接続タブでESP32へ再接続してください。"
        elif not quick_ok:
            next_action = "実機接続タブで実機クイック確認を実行してください。"
        elif not saved:
            next_action = "実機確認結果の保存先を確認してください。"
        else:
            next_action = "作業完了です。ログタブで結果を確認できます。"
        if hasattr(self, "next_action_label"):
            self.next_action_label.setText(f"次にやること: {next_action}")

    def _update_sensor_detail_widgets(self, data, show_sensor_values: bool) -> None:
        imu = self.sensor_detail_labels.get("imu")
        if imu:
            if not show_sensor_values:
                imu["IMU状態"].setText("未接続")
                imu["yaw"].setText("0.0 deg")
                imu["pitch"].setText("0.0 deg")
                imu["roll"].setText("0.0 deg")
                imu["gyro x"].setText("0.00")
                imu["gyro y"].setText("0.00")
                imu["gyro z"].setText("0.00")
                if "accel x" in imu:
                    imu["accel x"].setText("0.000 g")
                    imu["accel y"].setText("0.000 g")
                    imu["accel z"].setText("0.000 g")
                imu["データ種別"].setText("信号なし")
            else:
                imu_status, imu_type = self._status_and_type(data.imu_status, "Real", data.imu_source)
                imu["IMU状態"].setText(imu_status)
                imu["yaw"].setText(f"{data.imu_yaw:.1f} deg")
                imu["pitch"].setText(f"{data.imu_pitch:.1f} deg")
                imu["roll"].setText(f"{data.imu_roll:.1f} deg")
                imu["gyro x"].setText(f"{data.gyro_x:.2f}")
                imu["gyro y"].setText(f"{data.gyro_y:.2f}")
                imu["gyro z"].setText(f"{data.gyro_z:.2f}")
                if "accel x" in imu:
                    imu["accel x"].setText(f"{getattr(data, 'accel_x_g', 0.0):.3f} g")
                    imu["accel y"].setText(f"{getattr(data, 'accel_y_g', 0.0):.3f} g")
                    imu["accel z"].setText(f"{getattr(data, 'accel_z_g', 0.0):.3f} g")
                imu["データ種別"].setText(imu_type)

        lidar = self.sensor_detail_labels.get("lidar")
        if lidar:
            if not show_sensor_values:
                lidar["LiDAR状態"].setText("未接続")
                lidar["前方"].setText("0 mm")
                lidar["左"].setText("0 mm")
                lidar["右"].setText("0 mm")
                lidar["後方"].setText("0 mm")
                lidar["データ種別"].setText("信号なし")
            else:
                lidar_status, lidar_type = self._status_and_type(data.lidar_status, "Real", data.lidar_source)
                lidar["LiDAR状態"].setText(lidar_status)
                lidar["前方"].setText(f"{data.lidar_front_mm:.0f} mm")
                lidar["左"].setText(f"{data.lidar_left_mm:.0f} mm")
                lidar["右"].setText(f"{data.lidar_right_mm:.0f} mm")
                lidar["後方"].setText(f"{data.lidar_rear_mm:.0f} mm")
                lidar["データ種別"].setText(lidar_type)

        encoder = self.sensor_detail_labels.get("encoder")
        if encoder:
            if not show_sensor_values:
                encoder["左エンコーダ"].setText("0")
                encoder["右エンコーダ"].setText("0")
                encoder["状態"].setText("未接続")
                encoder["データ種別"].setText("信号なし")
            else:
                encoder_status, encoder_type = self._status_and_type(getattr(data, "encoder_status", "未接続"), "Real", "")
                encoder["左エンコーダ"].setText(str(data.encoder_left))
                encoder["右エンコーダ"].setText(str(data.encoder_right))
                encoder["状態"].setText(encoder_status)
                encoder["データ種別"].setText(encoder_type)

        camera = self.sensor_detail_labels.get("camera")
        if camera:
            if self.camera.connected:
                camera["カメラ状態"].setText("接続中")
                camera["データ種別"].setText("実カメラ")
            elif self.camera.mock:
                camera["カメラ状態"].setText("未接続")
                camera["データ種別"].setText("Mock映像")
            else:
                camera["カメラ状態"].setText("未接続")
                camera["データ種別"].setText("データなし")

    def _status_and_type(self, status: str, source: str, source_text: str) -> tuple[str, str]:
        normalized = (status or "").upper()
        if source == "Real":
            if normalized == "DUMMY":
                return "ESP32ダミー出力", "ESP32ダミー出力"
            if normalized == "OK":
                return "接続中", "実データ"
            if normalized == "ERROR":
                return "エラー", "データなし"
            return "未接続", "データなし"
        if source == "Simulation":
            return "正常", "シミュレーション"
        if source == "Mock":
            return "DUMMY", "Mockデータ（値は0表示）"
        return source_text or "未接続", source_text or "データなし"

    def _source_type_label(self, source: str) -> str:
        labels = {
            "Real": "実データ" if self.imu_state.has_recent_data() else "データなし",
            "Simulation": "シミュレーション",
            "Mock": "Mockデータ",
        }
        return labels.get(source, "データなし")

    def _mode_text(self, mode_cfg: dict) -> tuple[str, str]:
        if bool(mode_cfg.get("use_simulation", False)):
            return "シミュレーションモード", "仮想フィールド上でロボット位置とセンサ値を確認します。"
        if bool(mode_cfg.get("use_mock", True)):
            return "モックモード", "実機なしでダミーデータを表示します。PC上だけでUIと制御指令を確認できます。"
        return "実機モード", "ESP32とセンサに接続して動作します。"

    def _mode_notice(self, source: str) -> str:
        if source == "Mock":
            return "モックモード：実機センサは未接続です。表示値はダミーデータです。"
        if source == "Simulation":
            return "シミュレーションモード：仮想フィールド上の計算値です。"
        return "実機モード：接続されたセンサの実データを表示しています。"

    def _sensor_source(self, mode_cfg: dict) -> tuple[str, bool]:
        if bool(mode_cfg.get("use_simulation", False)):
            return "Simulation", False
        if bool(mode_cfg.get("use_mock", True)):
            return "Mock", False
        return "Real", False

    def _display_config(self) -> dict:
        display_cfg = cfg_section(self.config, "display").copy()
        display_cfg.setdefault("show_mock_values", True)
        display_cfg.setdefault("label_mock_values", True)
        display_cfg.setdefault("hide_mock_values_when_disconnected", False)
        return display_cfg

    def _show_sensor_values(self) -> bool:
        if self.sensor_source == "Simulation":
            return True
        if self.sensor_source == "Real":
            return self.sensor_connected or self.imu_state.has_recent_data()
        if not bool(self.display_cfg.get("show_mock_values", True)):
            return False
        if bool(self.display_cfg.get("hide_mock_values_when_disconnected", False)) and not self.sensor_connected:
            return False
        return True

    @staticmethod
    def _has_real_serial_connection(esp32_status) -> bool:
        return bool(getattr(esp32_status, "connected", False) and not getattr(esp32_status, "mock", False))

    def _show_real_sensor_values(self, esp32_status) -> bool:
        # センサタブは通常の実機接続だけでなく、シリアルタブから受けた
        # テストスケッチ出力やログ再生の値も表示対象にする。
        return self.imu_state.has_recent_data()

    def _log_sensor_sources(self) -> None:
        if self.sensor_source == "Mock":
            for name in ["LiDAR", "IMU", "光学式オドメトリ", "エンコーダ"]:
                self._log(f"{name}未接続: Mockデータを表示")
            self._log("注意: 現在表示されているセンサ値は実データではありません")
        elif self.sensor_source == "Simulation":
            for name in ["LiDAR", "IMU", "光学式オドメトリ", "エンコーダ"]:
                self._log(f"{name}未接続: シミュレーション値を表示")
            self._log("注意: 現在表示されているセンサ値は仮想フィールド上の計算値です")
        else:
            self._log("実機モード: 接続されたセンサの実データを表示します")

    def _serial_config(self) -> dict:
        serial_cfg = cfg_section(self.config, "serial").copy()
        communication_cfg = cfg_section(self.config, "communication")
        controllers_cfg = cfg_section(self.config, "controllers")
        drive_cfg = cfg_section(controllers_cfg, "drive")
        usb_cfg = cfg_section(communication_cfg, "usb")
        for key in ("port", "baudrate"):
            if key in usb_cfg and key not in serial_cfg:
                serial_cfg[key] = usb_cfg[key]
            if key in drive_cfg:
                serial_cfg[key] = drive_cfg[key]
        mode_cfg = cfg_section(self.config, "mode")
        serial_cfg["mock"] = bool(serial_cfg.get("mock", mode_cfg.get("use_mock", True)))
        return serial_cfg

    def _apply_simulation_command(self, command, command_text: str) -> None:
        if self.sensor_source != "Simulation":
            return
        message = self.robot_simulator.apply_command(command)
        if command_text == "EMERGENCY_STOP" or command_text == "DRIVE STOP":
            self._log("シミュレーション停止")
        elif command.category == "DRIVE" and command.action == "VEL":
            self._log(f"シミュレーション指令: {command_text}")
        elif message:
            self._log(message)

    def reset_simulation(self) -> None:
        self.robot_simulator.reset()
        self.fusion.pose.x = self.robot_simulator.state.x_mm / 1000.0
        self.fusion.pose.y = self.robot_simulator.state.y_mm / 1000.0
        self.fusion.pose.theta = self.robot_simulator.state.theta_deg
        self.map_widget.clear_trail()
        self.last_simulation_boundary_status = ""
        self.last_simulation_obstacle_status = ""
        self._update_simulation_status()
        self._log("シミュレーションをリセットしました")

    def reset_simulation_pose(self) -> None:
        self.robot_simulator.reset_pose_to_start()
        self.fusion.pose.x = self.robot_simulator.state.x_mm / 1000.0
        self.fusion.pose.y = self.robot_simulator.state.y_mm / 1000.0
        self.fusion.pose.theta = self.robot_simulator.state.theta_deg
        self._update_simulation_status()
        self._log("初期位置に戻しました")

    def clear_simulation_trail(self) -> None:
        self.map_widget.clear_trail()
        self._log("軌跡をクリアしました")

    def start_auto_drive(self) -> None:
        if self.sensor_source != "Simulation":
            self._log("現在のモードでは自動走行を開始できません。シミュレーションモードで使用してください。")
            self.auto_drive_active = False
            self.auto_drive_decision = "停止"
            self.auto_drive_reason = "シミュレーションモード専用"
            self._update_auto_drive_status()
            return
        if self.safety_layer.emergency_stop_active:
            self._log("緊急停止中のため自動走行を開始できません")
            self.auto_drive_active = False
            self.auto_drive_decision = "停止"
            self.auto_drive_reason = "緊急停止中"
            self._update_auto_drive_status()
            return
        self.auto_drive_active = True
        self.auto_drive_decision = "停止"
        self.auto_drive_reason = "開始待機"
        self.last_auto_command_text = ""
        self.last_auto_drive_time = 0.0
        self._log("自動走行開始")
        self._update_auto_drive_status()

    def stop_auto_drive(self) -> None:
        was_active = self.auto_drive_active
        self.auto_drive_active = False
        self.auto_drive_decision = "停止"
        self.auto_drive_reason = "手動停止"
        self.last_auto_command_text = ""
        if was_active:
            self._log("自動走行停止")
        self.send_command("DRIVE STOP")
        self._update_auto_drive_status()

    def _maybe_run_auto_drive(self) -> None:
        if not self.auto_drive_active:
            return
        if self.sensor_source != "Simulation":
            self.auto_drive_active = False
            self.auto_drive_decision = "停止"
            self.auto_drive_reason = "シミュレーションモード専用"
            self._log("現在のモードでは自動走行を開始できません。シミュレーションモードで使用してください。")
            return
        if self.safety_layer.emergency_stop_active:
            self.auto_drive_active = False
            self.auto_drive_decision = "停止"
            self.auto_drive_reason = "緊急停止"
            self._log("緊急停止により自動走行を停止しました")
            return

        now = time.monotonic()
        if now - self.last_auto_drive_time < self.auto_drive_interval_s:
            return
        self.last_auto_drive_time = now

        state = self.robot_simulator.state
        decision = self.auto_controller.decide(
            state.lidar_front_mm,
            state.lidar_left_mm,
            state.lidar_right_mm,
            pose=state,
        )
        command_text = format_command(decision.command)
        self.auto_drive_decision = decision.action
        self.auto_drive_reason = decision.reason

        if decision.reason == "LiDARデータなし":
            self.auto_drive_active = False
            self.last_auto_command_text = ""
            self._log("自動走行停止：LiDARデータなし")
            self.send_command("DRIVE STOP")
            return

        if command_text != self.last_auto_command_text:
            self._log(f"自動走行判断：{decision.action}")
            self.send_command(command_text)
            self.last_auto_command_text = command_text

    def _update_simulation_status(self) -> None:
        state = self.robot_simulator.state
        running_text = "動作中" if state.running else "停止中"
        boundary_text = state.boundary_status or "正常"
        self.simulation_status_label.setText(
            "シミュレーション状態: "
            f"{running_text}\n"
            f"左速度: {state.left_speed}\n"
            f"右速度: {state.right_speed}\n"
            f"境界状態: {boundary_text}\n"
            f"障害物状態: {state.obstacle_status or '正常'}\n"
            f"LiDAR前方: {state.lidar_front_mm:.0f} mm\n"
            f"現在位置: x={state.x_mm:.1f} mm / y={state.y_mm:.1f} mm / θ={state.theta_deg:.1f} deg\n"
            f"最終指令: {state.last_command}"
        )

    def _update_auto_drive_status(self) -> None:
        running_text = "動作中" if self.auto_drive_active else "停止中"
        self.auto_drive_status_label.setText(
            f"自動走行状態: {running_text}\n"
            f"自動走行判断: {self.auto_drive_decision}\n"
            f"判断理由: {self.auto_drive_reason}"
        )

    def _command_label(self, command: str) -> str:
        labels = {
            "DRIVE VEL 100 100": "前進",
            "DRIVE VEL 0 0": "停止",
            "DRIVE STOP": "停止",
            "DRIVE VEL -80 80": "左旋回",
            "DRIVE VEL 80 -80": "右旋回",
            "EMERGENCY_STOP": "緊急停止",
        }
        return labels.get(command, command)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.send_command("EMERGENCY_STOP")
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F5:
            self.refresh_com_ports()
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_H:
                self.switch_to_tab("ホーム")
                event.accept()
                return
            if event.key() == Qt.Key.Key_L:
                self.switch_to_tab("ログ")
                event.accept()
                return
            if event.key() == Qt.Key.Key_E:
                self.switch_to_tab("実機接続")
                event.accept()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self.diagnostics_worker is not None and self.diagnostics_worker.isRunning():
            self.diagnostics_worker.requestInterruption()
            self.diagnostics_worker.wait(1500)
        self.camera.close()
        self.serial.close()
        self.csv_logger.stop()
        self._save_local_settings()
        super().closeEvent(event)


def main() -> None:
    install_qt_font_warning_filter()
    app = QApplication(sys.argv)
    app.setApplicationName("ロボットPCダッシュボード")
    app.setApplicationDisplayName("ロボットPCダッシュボード")
    app.setFont(make_font("Yu Gothic UI", 10))
    install_input_wheel_guard(app)
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



