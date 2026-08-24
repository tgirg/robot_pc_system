"""R2 real-machine connection status and SAFE-only live settings editor."""

from __future__ import annotations

import copy
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pc_controller.config_manager import (
    default_controller_mapping,
    default_vehicle_config,
    load_json_result,
    save_json,
    validate_vehicle_config,
)

from .ui_helpers import make_notice, make_scroll_area, set_section_title
from sound_manager import SoundEvent


WHEEL_NAMES = ("FL", "FR", "RL", "RR")


class RealHardwareSettingsWidget(QWidget):
    """Edit, back up, and live-apply validated settings while R2 is SAFE."""

    def __init__(
        self,
        config_dir: str | Path,
        parent: QWidget | None = None,
        *,
        apply_callback: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("realHardwareSettingsWidget")
        self.config_dir = Path(config_dir)
        self.vehicle_path = self.config_dir / "vehicle_config.json"
        self.controller_path = self.config_dir / "controller_mapping.json"
        self.apply_callback = apply_callback
        self._vehicle: dict[str, Any] = {}
        self._controller: dict[str, Any] = {}
        self._robot_armed = False

        self.connector_inputs: dict[str, dict[str, QWidget]] = {}
        self.motion_inputs: dict[str, QSpinBox | QDoubleSpinBox] = {}
        self.motion_checks: dict[str, QCheckBox] = {}
        self.servo_inputs: dict[str, dict[str, QWidget]] = {}
        self.motor_inputs: dict[str, dict[str, QWidget]] = {}
        self.controller_inputs: dict[str, QWidget] = {}

        self._build_ui()
        self.reload_from_disk(show_dialog=False)

    def _build_ui(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("R2 実機接続・設定")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "R2がSAFE・出力停止中なら、保存と同時にControllerAppとESP32へ反映します。"
                "ARM中は保存できません。サーボch / motor physical / encoder physicalは重複できません。"
            )
        )

        self.pages = QTabWidget()
        self.pages.addTab(self._build_controller_status_page(), "コントローラ確認")
        self.pages.addTab(self._build_connector_page(), "接続割当")
        self.pages.addTab(self._build_motion_page(), "走行設定")
        self.pages.addTab(self._build_servo_page(), "サーボ調整")
        self.pages.addTab(self._build_motor_encoder_page(), "モータ・エンコーダ")
        self.pages.addTab(self._build_controller_mapping_page(), "操作割当")
        layout.addWidget(self.pages, 1)

        self.save_state_label = QLabel("設定を読み込んでいます")
        self.save_state_label.setObjectName("modeNoticeLabel")
        self.save_state_label.setWordWrap(True)
        layout.addWidget(self.save_state_label)

        buttons = QHBoxLayout()
        reload_button = QPushButton("ディスクから再読込")
        reload_button.clicked.connect(self.reload_from_disk)
        save_button = QPushButton("設定を保存して即時反映")
        save_button.setObjectName("saveRealHardwareSettingsButton")
        save_button.clicked.connect(self.save_to_disk)
        buttons.addWidget(reload_button)
        buttons.addWidget(save_button, 1)
        layout.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(make_scroll_area(content))

    def _build_controller_status_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.controller_connection_label = QLabel("未確認")
        self.controller_connection_label.setObjectName("largeValue")
        self.controller_connection_label.setWordWrap(True)
        layout.addWidget(self._group("コントローラ接続", self.controller_connection_label))

        self.controller_live_label = QLabel(
            "左スティック: vx=+0.000 / vy=+0.000\n"
            "右スティック: omega=+0.000\nARM組合せ=OFF / SAFEボタン=OFF"
        )
        self.controller_live_label.setObjectName("diagnosticLabel")
        self.controller_live_label.setWordWrap(True)
        layout.addWidget(self._group("リアルタイム入力確認", self.controller_live_label))

        self.controller_mapping_summary = QLabel("")
        self.controller_mapping_summary.setObjectName("diagnosticLabel")
        self.controller_mapping_summary.setWordWrap(True)
        layout.addWidget(self._group("現在の操作割当", self.controller_mapping_summary))

        guide = QLabel(
            "確認方法:\n"
            "1. コントローラ名が表示されることを確認\n"
            "2. スティックを動かして vx / vy / omega が変化することを確認\n"
            "3. L1+R1+×でARM組合せ、OPTIONSでSAFEボタンがONになることを確認\n"
            "この画面だけではARMもモータ出力も行いません。"
        )
        guide.setWordWrap(True)
        layout.addWidget(self._group("接続テスト手順", guide))
        layout.addStretch(1)
        return page

    def _build_connector_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            make_notice(
                "旧4WIS画面のコネクタ接続設定に相当します。数字は基板上のch/physical番号です。"
                "配線と一致しない設定で走行させないでください。"
            )
        )
        grid = QGridLayout()
        headers = (
            "車輪",
            "サーボ ch",
            "モータ physical",
            "エンコーダ physical",
            "モータ反転",
            "エンコーダ反転",
            "サーボ反転",
        )
        for column, text in enumerate(headers):
            grid.addWidget(QLabel(text), 0, column)
        for row, name in enumerate(WHEEL_NAMES, start=1):
            servo_channel = self._int_input(0, 15)
            motor_physical = self._int_input(0, 3)
            encoder_physical = self._int_input(0, 3)
            motor_inverted = QCheckBox()
            encoder_inverted = QCheckBox()
            servo_inverted = QCheckBox()
            self.connector_inputs[name] = {
                "servo_channel": servo_channel,
                "motor_physical": motor_physical,
                "encoder_physical": encoder_physical,
                "motor_inverted": motor_inverted,
                "encoder_inverted": encoder_inverted,
                "servo_inverted": servo_inverted,
            }
            grid.addWidget(QLabel(name), row, 0)
            grid.addWidget(servo_channel, row, 1)
            grid.addWidget(motor_physical, row, 2)
            grid.addWidget(encoder_physical, row, 3)
            grid.addWidget(motor_inverted, row, 4, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(encoder_inverted, row, 5, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(servo_inverted, row, 6, Qt.AlignmentFlag.AlignCenter)
        grid.setColumnStretch(0, 1)
        layout.addWidget(self._group_layout("各輪の接続割当", grid))
        layout.addStretch(1)
        return page

    def _build_motion_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        specs = (
            ("wheelbase_m", "ホイールベース [m]", 0.05, 3.0, 3, 0.005),
            ("track_width_m", "トレッド幅 [m]", 0.05, 3.0, 3, 0.005),
            ("wheel_diameter_m", "車輪直径 [m]", 0.01, 0.5, 4, 0.001),
            ("max_wheel_rpm", "車輪最大RPM", 1, 5000, 0, 10),
            ("max_linear_speed_mps", "最大並進速度 [m/s]", 0.01, 10.0, 3, 0.05),
            ("max_angular_speed_radps", "最大旋回速度 [rad/s]", 0.01, 30.0, 3, 0.05),
            ("open_loop_max_pwm", "通常走行PWM上限（現段階は最大120）", 1, 120, 0, 5),
            ("pivot_max_pwm", "超信地旋回PWM上限（現段階は最大120）", 1, 120, 0, 5),
            ("translation_deadzone", "移動判定デッドゾーン", 0.0, 1.0, 3, 0.01),
            ("candidate_switch_hysteresis_deg", "角度候補切替ヒステリシス [deg]", 0.0, 90.0, 1, 1.0),
            ("servo_end_margin_deg", "サーボ端マージン [deg]", 0.0, 90.0, 1, 1.0),
            ("realign_threshold_deg", "再整列しきい値 [deg]", 0.0, 180.0, 1, 1.0),
            ("alignment_servo_rate_deg_per_sec", "整列時サーボ速度 [deg/s]", 1.0, 720.0, 1, 5.0),
            ("alignment_tolerance_deg", "整列許容誤差 [deg]", 0.1, 90.0, 1, 0.5),
            ("alignment_settle_time_ms", "整列安定待ち [ms]", 0, 5000, 0, 10),
            ("alignment_timeout_ms", "整列タイムアウト [ms]", 100, 30000, 0, 100),
            ("decel_time_ms", "減速時間 [ms]", 0, 10000, 0, 10),
            ("accel_time_ms", "加速時間 [ms]", 0, 10000, 0, 10),
            ("mixed_arc_min_radius_m", "MIX最小旋回半径 [m]", 0.05, 5.0, 3, 0.05),
            ("coordinated_4ws_max_steer_deg", "協調4WS最大舵角 [deg]", 1.0, 90.0, 1, 1.0),
        )
        for key, label, minimum, maximum, decimals, step in specs:
            widget: QSpinBox | QDoubleSpinBox
            if decimals == 0:
                widget = self._int_input(int(minimum), int(maximum), int(step))
            else:
                widget = self._float_input(float(minimum), float(maximum), int(decimals), float(step))
            self.motion_inputs[key] = widget
            form.addRow(label, widget)
        layout.addWidget(self._group_layout("走行・車体パラメータ", form))

        checks = QGridLayout()
        check_specs = (
            ("open_loop_static_compensation_enabled", "開ループ始動PWM補償を使用"),
            ("pivot_direction_inverted", "超信地旋回方向を反転"),
            ("mixed_omega_inverted", "前進・平行移動中の旋回方向を反転"),
            ("coordinated_4ws_inner_outer_speed", "内外輪速度差を使用"),
            ("coordinated_4ws_positive_steer_turns_right", "正の舵角で右旋回"),
            ("limit_mixed_peak_to_translation", "MIXピークを並進速度へ制限"),
        )
        for index, (key, text) in enumerate(check_specs):
            check = QCheckBox(text)
            self.motion_checks[key] = check
            checks.addWidget(check, index // 2, index % 2)
        layout.addWidget(self._group_layout("方向・方式", checks))
        layout.addStretch(1)
        return page

    def _build_servo_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        for index, name in enumerate(WHEEL_NAMES):
            form = QFormLayout()
            center = self._int_input(500, 2500)
            minimum_us = self._int_input(400, 2500)
            maximum_us = self._int_input(500, 3000)
            minimum_angle = self._float_input(-180.0, -0.1, 1, 1.0)
            maximum_angle = self._float_input(0.1, 180.0, 1, 1.0)
            trim = self._float_input(-90.0, 90.0, 1, 0.5)
            max_rate = self._float_input(1.0, 1000.0, 1, 5.0)
            calibrated = QCheckBox("中心・端点を実機確認済み")
            fields = {
                "center_us": center,
                "min_us": minimum_us,
                "max_us": maximum_us,
                "min_angle_deg": minimum_angle,
                "max_angle_deg": maximum_angle,
                "trim_deg": trim,
                "max_rate_deg_per_sec": max_rate,
                "calibrated": calibrated,
            }
            self.servo_inputs[name] = fields
            form.addRow("中心 [us]", center)
            form.addRow("最小 [us]", minimum_us)
            form.addRow("最大 [us]", maximum_us)
            form.addRow("最小角 [deg]", minimum_angle)
            form.addRow("最大角 [deg]", maximum_angle)
            form.addRow("トリム [deg]", trim)
            form.addRow("最大速度 [deg/s]", max_rate)
            form.addRow(calibrated)
            layout.addWidget(self._group_layout(f"{name} サーボ", form), index // 2, index % 2)
        return page

    def _build_motor_encoder_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        for index, name in enumerate(WHEEL_NAMES):
            form = QFormLayout()
            encoder_cpr = self._int_input(0, 10_000_000, 100)
            motor_cpr = self._int_input(0, 10_000_000, 100)
            pid_enabled = QCheckBox("この車輪でPIDを使用")
            kp = self._float_input(0.0, 1000.0, 4, 0.05)
            ki = self._float_input(0.0, 1000.0, 4, 0.05)
            kd = self._float_input(0.0, 1000.0, 4, 0.05)
            integral = self._float_input(0.0, 100_000.0, 2, 10.0)
            output_min = self._int_input(-1023, 0, 5)
            output_max = self._int_input(0, 1023, 5)
            ff_static_pos = self._float_input(0.0, 1023.0, 2, 1.0)
            ff_static_neg = self._float_input(0.0, 1023.0, 2, 1.0)
            ff_per_rpm_pos = self._float_input(0.0, 100.0, 4, 0.01)
            ff_per_rpm_neg = self._float_input(0.0, 100.0, 4, 0.01)
            fields = {
                "encoder_counts_per_wheel_rev": encoder_cpr,
                "motor_counts_per_wheel_rev": motor_cpr,
                "pid_enabled": pid_enabled,
                "kp": kp,
                "ki": ki,
                "kd": kd,
                "integral_limit": integral,
                "output_min": output_min,
                "output_max": output_max,
                "ff_static_pwm_pos": ff_static_pos,
                "ff_static_pwm_neg": ff_static_neg,
                "ff_pwm_per_rpm_pos": ff_per_rpm_pos,
                "ff_pwm_per_rpm_neg": ff_per_rpm_neg,
            }
            self.motor_inputs[name] = fields
            form.addRow("エンコーダCPR", encoder_cpr)
            form.addRow("モータ側CPR", motor_cpr)
            form.addRow(pid_enabled)
            form.addRow("Kp", kp)
            form.addRow("Ki", ki)
            form.addRow("Kd", kd)
            form.addRow("積分上限", integral)
            form.addRow("出力下限", output_min)
            form.addRow("出力上限", output_max)
            form.addRow("静止摩擦FF +", ff_static_pos)
            form.addRow("静止摩擦FF -", ff_static_neg)
            form.addRow("PWM/RPM FF +", ff_per_rpm_pos)
            form.addRow("PWM/RPM FF -", ff_per_rpm_neg)
            layout.addWidget(self._group_layout(f"{name} モータ・エンコーダ", form), index // 2, index % 2)
        self.global_pid_enabled = QCheckBox("全体PID制御を有効にする")
        layout.addWidget(self.global_pid_enabled, 2, 0, 1, 2)
        return page

    def _build_controller_mapping_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        for key, label in (("axis_vx", "vx軸番号"), ("axis_vy", "vy軸番号"), ("axis_omega", "omega軸番号")):
            widget = self._int_input(0, 31)
            self.controller_inputs[key] = widget
            form.addRow(label, widget)
        for key, label in (("invert_vx", "vx反転"), ("invert_vy", "vy反転"), ("invert_omega", "omega反転")):
            widget = QCheckBox()
            self.controller_inputs[key] = widget
            form.addRow(label, widget)
        logical_front = QComboBox()
        logical_front.addItems(("FRONT", "RIGHT", "REAR", "LEFT"))
        logical_front.setToolTip("機体基準の前方。REARは並進vx/vyを180度反転し、旋回omegaは維持します。")
        self.controller_inputs["logical_front"] = logical_front
        form.addRow("機体の論理前方", logical_front)
        numeric_specs = (
            ("deadzone", "スティックデッドゾーン", 0.0, 0.95, 3, 0.01),
            ("linear_scale", "並進入力倍率", 0.0, 1.0, 3, 0.01),
            ("angular_scale", "旋回入力倍率", 0.0, 1.0, 3, 0.01),
            ("arm_hold_seconds", "ARM長押し時間 [s]", 0.1, 5.0, 2, 0.1),
        )
        for key, label, minimum, maximum, decimals, step in numeric_specs:
            widget = self._float_input(minimum, maximum, decimals, step)
            self.controller_inputs[key] = widget
            form.addRow(label, widget)
        for key, label in (
            ("safe_button", "SAFEボタン番号"),
            ("mode_button", "モードボタン番号"),
            ("debug_execute_button", "診断実行ボタン番号"),
        ):
            widget = self._int_input(0 if key == "safe_button" else -1, 63)
            self.controller_inputs[key] = widget
            form.addRow(label, widget)
        arm_row = QHBoxLayout()
        self.arm_button_inputs: list[QSpinBox] = []
        for _ in range(3):
            widget = self._int_input(-1, 63)
            self.arm_button_inputs.append(widget)
            arm_row.addWidget(widget)
        form.addRow("ARM組合せボタン", arm_row)
        layout.addWidget(self._group_layout("コントローラ操作割当", form))
        layout.addStretch(1)
        return page

    def set_fleet_snapshot(self, fleet: Any) -> None:
        robot = None
        for candidate in tuple(getattr(fleet, "robots", ())):
            if str(getattr(getattr(candidate, "robot_id", ""), "value", getattr(candidate, "robot_id", ""))) == "R2":
                robot = candidate
                break
        if robot is None:
            self.controller_connection_label.setText("R2状態データなし")
            self._robot_armed = False
            return
        self._robot_armed = bool(getattr(robot, "armed", False))
        connected = bool(getattr(robot, "controller_connected", False))
        name = str(getattr(robot, "controller_name", "") or "名称未取得")
        self.controller_connection_label.setText(
            f"{'接続済み' if connected else '未接続'} / {name}\n"
            f"ロボット出力: {'ARM中' if self._robot_armed else '出力停止'}"
        )
        color = "#86efac" if connected else "#fca5a5"
        self.controller_connection_label.setStyleSheet(f"color:{color}; font-weight:900;")

    def set_controller_input_snapshot(self, state: Any) -> None:
        connected = bool(getattr(state, "connected", False))
        name = str(getattr(state, "name", "") or "名称未取得")
        self.controller_connection_label.setText(
            f"{'接続済み' if connected else '未接続'} / {name}\n"
            f"ロボット出力: {'ARM中' if self._robot_armed else '出力停止'}"
        )
        color = "#86efac" if connected else "#fca5a5"
        self.controller_connection_label.setStyleSheet(f"color:{color}; font-weight:900;")
        self.controller_live_label.setText(
            f"左スティック: vx={float(getattr(state, 'vx', 0.0)):+.3f} / "
            f"vy={float(getattr(state, 'vy', 0.0)):+.3f}\n"
            f"右スティック: omega={float(getattr(state, 'omega', 0.0)):+.3f}\n"
            f"ARM組合せ={'ON' if bool(getattr(state, 'arm_pressed', False)) else 'OFF'} / "
            f"SAFEボタン={'ON' if bool(getattr(state, 'safe_pressed', False)) else 'OFF'}"
        )

    def reload_from_disk(self, checked: bool = False, *, show_dialog: bool = True) -> None:
        del checked
        try:
            vehicle_result = load_json_result(self.vehicle_path, default_vehicle_config())
            controller_result = load_json_result(self.controller_path, default_controller_mapping())
            if not vehicle_result.loaded:
                raise ValueError(f"vehicle_config.jsonを読み込めません: {vehicle_result.error}")
            if not controller_result.loaded:
                raise ValueError(f"controller_mapping.jsonを読み込めません: {controller_result.error}")
            validate_vehicle_config(vehicle_result.data, require_armable=False)
            self._vehicle = copy.deepcopy(vehicle_result.data)
            self._controller = copy.deepcopy(controller_result.data)
            self._load_widgets()
            self._set_save_state("設定を読み込みました。変更はまだ実機へ反映されていません。", "ok")
            if show_dialog:
                QMessageBox.information(self, "再読込", "現在の設定をディスクから再読込しました。")
        except Exception as exc:
            self._set_save_state(f"設定読込失敗: {exc}", "error")
            self._play_sound(SoundEvent.SETTINGS_SAVE_FAILED)
            if show_dialog:
                QMessageBox.warning(self, "設定読込失敗", str(exc))

    def save_to_disk(self, checked: bool = False) -> None:
        del checked
        if self._robot_armed:
            self._play_sound(SoundEvent.OPERATION_REJECTED)
            QMessageBox.warning(self, "保存禁止", "R2がARM中です。OPTIONSでSAFEにしてから保存してください。")
            return
        try:
            vehicle = self._vehicle_from_widgets()
            controller = self._controller_from_widgets()
            validate_vehicle_config(vehicle, require_armable=False)
            self._validate_controller_mapping(controller)
            answer = QMessageBox.question(
                self,
                "設定保存",
                "vehicle_config.json と controller_mapping.json を保存します。\n"
                "R2をDISARM状態に保ち、ESP32へCONFIGを再送します。保存して反映しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            backup_dir = self._backup_current_files()
            try:
                save_json(self.vehicle_path, vehicle)
                save_json(self.controller_path, controller)
                if not callable(self.apply_callback):
                    raise RuntimeError("R2 runtimeへの設定反映経路がありません")
                self.apply_callback(copy.deepcopy(vehicle), copy.deepcopy(controller))
            except Exception:
                self._restore_backup(backup_dir)
                self._reload_internal_after_restore()
                raise
            self._vehicle = copy.deepcopy(vehicle)
            self._controller = copy.deepcopy(controller)
            self._set_save_state(
                f"保存・即時反映完了 / SAFE・出力停止 / backup={backup_dir.name}",
                "ok",
            )
            self._play_sound(SoundEvent.SETTINGS_SAVED)
            QMessageBox.information(
                self,
                "保存・反映完了",
                "設定を保存し、ESP32のCONFIG応答を確認しました。\nGUIを再起動する必要はありません。",
            )
        except Exception as exc:
            self._set_save_state(f"保存失敗: {exc}", "error")
            self._play_sound(SoundEvent.SETTINGS_SAVE_FAILED)
            QMessageBox.warning(self, "保存失敗", str(exc))

    def _play_sound(self, event: SoundEvent) -> None:
        manager = getattr(self.parent(), "sound_manager", None)
        if manager is not None:
            manager.play(event)

    def _load_widgets(self) -> None:
        motors = list(self._vehicle.get("motors", []))
        encoders = list(self._vehicle.get("encoders", []))
        servos = list(self._vehicle.get("servos", []))
        for index, name in enumerate(WHEEL_NAMES):
            motor = motors[index]
            encoder = encoders[index]
            servo = servos[index]
            connector = self.connector_inputs[name]
            self._set_value(connector["servo_channel"], servo.get("channel", 0))
            self._set_value(connector["motor_physical"], motor.get("physical", 0))
            self._set_value(connector["encoder_physical"], encoder.get("physical", 0))
            connector["motor_inverted"].setChecked(bool(motor.get("inverted", False)))
            connector["encoder_inverted"].setChecked(bool(encoder.get("inverted", False)))
            connector["servo_inverted"].setChecked(bool(servo.get("direction_inverted", False)))

            for key, widget in self.servo_inputs[name].items():
                if key == "calibrated":
                    widget.setChecked(bool(servo.get(key, False)))
                else:
                    self._set_value(widget, servo.get(key, 0))

            motor_widgets = self.motor_inputs[name]
            self._set_value(motor_widgets["encoder_counts_per_wheel_rev"], encoder.get("counts_per_wheel_rev", 0))
            self._set_value(motor_widgets["motor_counts_per_wheel_rev"], motor.get("counts_per_wheel_rev", 0))
            for key, widget in motor_widgets.items():
                if key in {"encoder_counts_per_wheel_rev", "motor_counts_per_wheel_rev"}:
                    continue
                if key == "pid_enabled":
                    widget.setChecked(bool(motor.get(key, False)))
                else:
                    self._set_value(widget, motor.get(key, 0))
        self.global_pid_enabled.setChecked(bool(self._vehicle.get("pid_enabled", False)))

        motion = self._vehicle.get("motion", {})
        for key, widget in self.motion_inputs.items():
            self._set_value(widget, motion.get(key, widget.minimum()))
        for key, widget in self.motion_checks.items():
            widget.setChecked(bool(motion.get(key, False)))

        for key, widget in self.controller_inputs.items():
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(self._controller.get(key, False)))
            elif isinstance(widget, QComboBox):
                value = str(self._controller.get(key, "FRONT")).strip().upper()
                widget.setCurrentText(value if value in {"FRONT", "RIGHT", "REAR", "LEFT"} else "FRONT")
            else:
                self._set_value(widget, self._controller.get(key, widget.minimum()))
        arm_buttons = list(self._controller.get("arm_buttons", []))
        for index, widget in enumerate(self.arm_button_inputs):
            widget.setValue(int(arm_buttons[index]) if index < len(arm_buttons) else -1)
        self._update_controller_mapping_summary()

    def _vehicle_from_widgets(self) -> dict[str, Any]:
        vehicle = copy.deepcopy(self._vehicle)
        vehicle["config_revision"] = int(vehicle.get("config_revision", 0)) + 1
        vehicle["pid_enabled"] = self.global_pid_enabled.isChecked()
        motion = dict(vehicle.get("motion", {}))
        for key, widget in self.motion_inputs.items():
            motion[key] = self._number(widget)
        for key, widget in self.motion_checks.items():
            motion[key] = widget.isChecked()
        vehicle["motion"] = motion

        motors = [dict(item) for item in vehicle.get("motors", [])]
        encoders = [dict(item) for item in vehicle.get("encoders", [])]
        servos = [dict(item) for item in vehicle.get("servos", [])]
        for index, name in enumerate(WHEEL_NAMES):
            connector = self.connector_inputs[name]
            motor = motors[index]
            encoder = encoders[index]
            servo = servos[index]
            motor.update(
                logical=index,
                name=name,
                physical=int(connector["motor_physical"].value()),
                inverted=connector["motor_inverted"].isChecked(),
            )
            encoder.update(
                logical=index,
                name=name,
                physical=int(connector["encoder_physical"].value()),
                inverted=connector["encoder_inverted"].isChecked(),
            )
            servo.update(
                logical=index,
                name=name,
                channel=int(connector["servo_channel"].value()),
                direction_inverted=connector["servo_inverted"].isChecked(),
            )
            for key, widget in self.servo_inputs[name].items():
                servo[key] = widget.isChecked() if isinstance(widget, QCheckBox) else self._number(widget)
            for key, widget in self.motor_inputs[name].items():
                if key == "encoder_counts_per_wheel_rev":
                    encoder["counts_per_wheel_rev"] = int(widget.value())
                elif key == "motor_counts_per_wheel_rev":
                    motor["counts_per_wheel_rev"] = int(widget.value())
                else:
                    motor[key] = widget.isChecked() if isinstance(widget, QCheckBox) else self._number(widget)
        vehicle["motors"] = motors
        vehicle["encoders"] = encoders
        vehicle["servos"] = servos
        return vehicle

    def _controller_from_widgets(self) -> dict[str, Any]:
        controller = copy.deepcopy(self._controller)
        for key, widget in self.controller_inputs.items():
            if isinstance(widget, QCheckBox):
                controller[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                controller[key] = widget.currentText()
            else:
                controller[key] = self._number(widget)
        controller["arm_buttons"] = [widget.value() for widget in self.arm_button_inputs if widget.value() >= 0]
        return controller

    @staticmethod
    def _validate_controller_mapping(mapping: dict[str, Any]) -> None:
        for key in ("axis_vx", "axis_vy", "axis_omega"):
            if int(mapping.get(key, -1)) < 0:
                raise ValueError(f"{key} は0以上で指定してください")
        if len({int(mapping[key]) for key in ("axis_vx", "axis_vy", "axis_omega")}) != 3:
            raise ValueError("vx/vy/omegaの軸番号が重複しています")
        if not 0.0 <= float(mapping.get("deadzone", -1.0)) < 0.95:
            raise ValueError("deadzoneは0以上0.95未満にしてください")
        if not mapping.get("arm_buttons"):
            raise ValueError("ARM組合せボタンを1個以上設定してください")
        if int(mapping.get("safe_button", -1)) < 0:
            raise ValueError("SAFEボタンは必ず設定してください")
        if str(mapping.get("logical_front", "FRONT")).strip().upper() not in {"FRONT", "RIGHT", "REAR", "LEFT"}:
            raise ValueError("機体の論理前方はFRONT/RIGHT/REAR/LEFTから選んでください")

    def _backup_current_files(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_dir = self.config_dir / "gui_backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        shutil.copy2(self.vehicle_path, backup_dir / self.vehicle_path.name)
        shutil.copy2(self.controller_path, backup_dir / self.controller_path.name)
        return backup_dir

    def _restore_backup(self, backup_dir: Path) -> None:
        for path in (self.vehicle_path, self.controller_path):
            source = backup_dir / path.name
            if source.exists():
                shutil.copy2(source, path)

    def _reload_internal_after_restore(self) -> None:
        vehicle = load_json_result(self.vehicle_path, default_vehicle_config())
        controller = load_json_result(self.controller_path, default_controller_mapping())
        if vehicle.loaded and controller.loaded:
            self._vehicle = copy.deepcopy(vehicle.data)
            self._controller = copy.deepcopy(controller.data)
            self._load_widgets()

    def _update_controller_mapping_summary(self) -> None:
        mapping = self._controller
        self.controller_mapping_summary.setText(
            f"軸: vx={mapping.get('axis_vx', '-')} / vy={mapping.get('axis_vy', '-')} / "
            f"omega={mapping.get('axis_omega', '-')}\n"
            f"反転: vx={mapping.get('invert_vx', False)} / vy={mapping.get('invert_vy', False)} / "
            f"omega={mapping.get('invert_omega', False)}\n"
            f"機体の論理前方={mapping.get('logical_front', 'FRONT')}\n"
            f"deadzone={mapping.get('deadzone', '-')} / linear={mapping.get('linear_scale', '-')} / "
            f"angular={mapping.get('angular_scale', '-')}\n"
            f"ARM={mapping.get('arm_buttons', [])} / SAFE={mapping.get('safe_button', '-')}"
        )

    def _set_save_state(self, text: str, level: str) -> None:
        colors = {"ok": "#86efac", "warn": "#fde68a", "error": "#fca5a5"}
        self.save_state_label.setText(text)
        self.save_state_label.setStyleSheet(f"color:{colors.get(level, '#dbeafe')}; font-weight:800;")

    @staticmethod
    def _number(widget: QSpinBox | QDoubleSpinBox) -> int | float:
        return int(widget.value()) if isinstance(widget, QSpinBox) else float(widget.value())

    @staticmethod
    def _set_value(widget: QWidget, value: Any) -> None:
        if isinstance(widget, QSpinBox):
            widget.setValue(int(float(value)))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))

    @staticmethod
    def _int_input(minimum: int, maximum: int, step: int = 1) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(max(1, step))
        return widget

    @staticmethod
    def _float_input(
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        return widget

    @staticmethod
    def _group(title: str, body: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(body)
        return box

    @staticmethod
    def _group_layout(title: str, body_layout: QFormLayout | QGridLayout) -> QGroupBox:
        box = QGroupBox(title)
        box.setLayout(body_layout)
        return box


def create_real_hardware_settings_tab(host: Any) -> QWidget:
    config_dir = getattr(host, "shared_runtime_config_dir", None)
    if config_dir is None:
        config_dir = Path(__file__).resolve().parents[4] / "config"
    widget = RealHardwareSettingsWidget(
        config_dir,
        host,
        apply_callback=getattr(host, "apply_real_hardware_settings", None),
    )
    host.real_hardware_settings_widget = widget
    return widget
