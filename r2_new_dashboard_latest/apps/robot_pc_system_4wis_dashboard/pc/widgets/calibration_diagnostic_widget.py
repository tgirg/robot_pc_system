from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.gui_calibration_model import (
    CalibrationDiagnosticSnapshot,
    build_calibration_diagnostic_snapshot,
)
from pc_controller.gui_direction_model import (
    LOGICAL_FRONTS,
    DirectionCalibrationSnapshot,
    DirectionDraftStore,
)
from pc_controller.gui_parameter_model import (
    ParameterDraftStore,
    ParameterEditorSnapshot,
    ParameterRowSnapshot,
)
from pc_controller.gui_servo_angle_model import (
    ServoAngleAdjustmentSnapshot,
    ServoAngleDraftStore,
    ServoAngleRowSnapshot,
)
from pc_controller.gui_servo_zero_model import (
    ServoZeroAdjustmentSnapshot,
    ServoZeroDraftStore,
    ServoZeroRowSnapshot,
)

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class CalibrationDiagnosticWidget(QWidget):
    """Calibration, Direction, and Parameter local drafts with no output API."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("calibrationDiagnosticWidget")
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._diagnostic: CalibrationDiagnosticSnapshot | None = None
        self._adjustment: ServoZeroAdjustmentSnapshot | None = None
        self._angle_adjustment: ServoAngleAdjustmentSnapshot | None = None
        self._direction_adjustment: DirectionCalibrationSnapshot | None = None
        self._parameter_adjustment: ParameterEditorSnapshot | None = None
        self._drafts = ServoZeroDraftStore()
        self._angle_drafts = ServoAngleDraftStore()
        self._direction_drafts = DirectionDraftStore()
        self._parameter_drafts = ParameterDraftStore()
        self._editor_dirty = False
        self._angle_editor_dirty = False
        self._direction_editor_dirty = False
        self._parameter_editor_dirty = False
        self._parameter_syncing = False
        self._motor_invert_checks: list[QCheckBox] = []
        self._servo_invert_checks: list[QCheckBox] = []
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def diagnostic_snapshot(self) -> CalibrationDiagnosticSnapshot | None:
        return self._diagnostic

    @property
    def adjustment_snapshot(self) -> ServoZeroAdjustmentSnapshot | None:
        return self._adjustment

    @property
    def angle_adjustment_snapshot(self) -> ServoAngleAdjustmentSnapshot | None:
        return self._angle_adjustment

    @property
    def direction_adjustment_snapshot(self) -> DirectionCalibrationSnapshot | None:
        return self._direction_adjustment

    @property
    def parameter_adjustment_snapshot(self) -> ParameterEditorSnapshot | None:
        return self._parameter_adjustment

    def set_fleet_snapshot(self, fleet: Any) -> None:
        robots: dict[str, Any] = {}
        for snapshot in tuple(getattr(fleet, "robots", ())):
            robot_id = _enum_value(getattr(snapshot, "robot_id", ""))
            if robot_id not in {"R1", "R2"}:
                raise ValueError("fleet snapshot robot_id must be R1 or R2")
            if robot_id in robots:
                raise ValueError(f"duplicate fleet snapshot for {robot_id}")
            robots[robot_id] = snapshot
        selected = _enum_value(getattr(fleet, "selected_robot", ""))
        if selected not in {"R1", "R2"}:
            raise ValueError("fleet selected_robot must be R1 or R2")
        self._robots = robots
        self.select_robot(selected, emit=False)

    def select_robot(self, robot_id: str, *, emit: bool = True) -> None:
        if robot_id not in {"R1", "R2"}:
            raise ValueError("robot_id must be R1 or R2")
        if robot_id != self._selected_robot:
            self._editor_dirty = False
            self._angle_editor_dirty = False
            self._direction_editor_dirty = False
            self._parameter_editor_dirty = False
        self._selected_robot = robot_id
        for value, button in self._robot_buttons.items():
            button.setChecked(value == robot_id)
        self._render_selected()
        if emit:
            self.robot_selected.emit(robot_id)

    def _build_ui(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("Calibration / Direction / Parameters / Servo Zero / Servo Angle")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "LOCAL DRAFT ONLY / NO OUTPUT: ControllerAppのshared snapshotを監査し、"
                "Direction・Parameter・Servo Zero/Angle候補値はGUIメモリ内だけに保持します。"
                "DEBUG・Serial・ARM・actuation・config write APIはありません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"calibrationSelect{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        self.snapshot_time_label = QLabel("snapshot: 未接続")
        selector.addWidget(self.snapshot_time_label)
        layout.addLayout(selector)

        self.fault_banner = QLabel()
        self.fault_banner.setObjectName("calibrationFaultBanner")
        self.fault_banner.setWordWrap(True)
        self.fault_banner.setMinimumHeight(54)
        layout.addWidget(self.fault_banner)

        status_grid = QGridLayout()
        self.selected_state_label = self._detail_label("calibrationSelectedState")
        self.workflow_state_label = self._detail_label("calibrationWorkflowState")
        status_grid.addWidget(boxed("Safety / readiness", self.selected_state_label), 0, 0)
        status_grid.addWidget(boxed("Calibration workflow", self.workflow_state_label), 0, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 2)
        layout.addLayout(status_grid)

        self.boundary_label = self._detail_label("calibrationBoundary")
        layout.addWidget(boxed("Controller API / output boundary", self.boundary_label))

        direction_editor = QWidget()
        direction_grid = QGridLayout(direction_editor)
        direction_grid.setContentsMargins(8, 8, 8, 8)
        direction_grid.addWidget(QLabel("Controller inversion"), 0, 0)
        self.invert_vx_check = QCheckBox("invert_vx")
        self.invert_vy_check = QCheckBox("invert_vy")
        self.invert_omega_check = QCheckBox("invert_omega")
        for column, check in enumerate(
            (self.invert_vx_check, self.invert_vy_check, self.invert_omega_check),
            start=1,
        ):
            check.setObjectName(f"direction{check.text().replace('_', '').title()}Check")
            check.toggled.connect(self._mark_direction_editor_dirty)
            direction_grid.addWidget(check, 0, column)

        direction_grid.addWidget(QLabel("Logical front"), 0, 4)
        self.logical_front_combo = QComboBox()
        self.logical_front_combo.setObjectName("directionLogicalFrontCombo")
        self.logical_front_combo.addItems(LOGICAL_FRONTS)
        self.logical_front_combo.currentIndexChanged.connect(self._mark_direction_editor_dirty)
        direction_grid.addWidget(self.logical_front_combo, 0, 5)

        direction_grid.addWidget(QLabel("Preview raw vx"), 1, 0)
        self.direction_raw_vx_edit = QLineEdit("0.6")
        self.direction_raw_vx_edit.setObjectName("directionRawVxEdit")
        direction_grid.addWidget(self.direction_raw_vx_edit, 1, 1)
        direction_grid.addWidget(QLabel("raw vy"), 1, 2)
        self.direction_raw_vy_edit = QLineEdit("0.25")
        self.direction_raw_vy_edit.setObjectName("directionRawVyEdit")
        direction_grid.addWidget(self.direction_raw_vy_edit, 1, 3)
        direction_grid.addWidget(QLabel("raw omega"), 1, 4)
        self.direction_raw_omega_edit = QLineEdit("0.2")
        self.direction_raw_omega_edit.setObjectName("directionRawOmegaEdit")
        direction_grid.addWidget(self.direction_raw_omega_edit, 1, 5)
        for edit in (
            self.direction_raw_vx_edit,
            self.direction_raw_vy_edit,
            self.direction_raw_omega_edit,
        ):
            edit.textEdited.connect(self._mark_direction_editor_dirty)

        direction_grid.addWidget(QLabel("Wheel"), 2, 0)
        direction_grid.addWidget(QLabel("Motor inversion candidate"), 2, 1, 1, 2)
        direction_grid.addWidget(QLabel("Servo inversion candidate"), 2, 3, 1, 2)
        for index, name in enumerate(("FL", "FR", "RL", "RR"), start=3):
            logical_index = index - 3
            direction_grid.addWidget(QLabel(name), index, 0)
            motor_check = QCheckBox("inverted")
            motor_check.setObjectName(f"directionMotor{logical_index}InvertedCheck")
            motor_check.toggled.connect(self._mark_direction_editor_dirty)
            direction_grid.addWidget(motor_check, index, 1, 1, 2)
            servo_check = QCheckBox("direction_inverted")
            servo_check.setObjectName(f"directionServo{logical_index}InvertedCheck")
            servo_check.toggled.connect(self._mark_direction_editor_dirty)
            direction_grid.addWidget(servo_check, index, 3, 1, 2)
            self._motor_invert_checks.append(motor_check)
            self._servo_invert_checks.append(servo_check)

        self.direction_stage_button = QPushButton("STAGE / 方向候補検証")
        self.direction_stage_button.setObjectName("directionStageButton")
        self.direction_stage_button.clicked.connect(self._stage_direction_pending)
        direction_grid.addWidget(self.direction_stage_button, 7, 0, 1, 2)
        self.direction_revert_button = QPushButton("REVERT / 方向取消")
        self.direction_revert_button.setObjectName("directionRevertButton")
        self.direction_revert_button.clicked.connect(self._revert_direction_pending)
        direction_grid.addWidget(self.direction_revert_button, 7, 2)
        self.direction_apply_button = QPushButton("APPLY / 利用不可")
        self.direction_apply_button.setObjectName("directionApplyButton")
        self.direction_apply_button.setEnabled(False)
        direction_grid.addWidget(self.direction_apply_button, 7, 3)
        self.direction_save_button = QPushButton("SAVE / 利用不可")
        self.direction_save_button.setObjectName("directionSaveButton")
        self.direction_save_button.setEnabled(False)
        direction_grid.addWidget(self.direction_save_button, 7, 4, 1, 2)
        self.direction_editor_state_label = self._detail_label("directionEditorState")
        direction_grid.addWidget(self.direction_editor_state_label, 8, 0, 1, 6)
        layout.addWidget(boxed("Direction / Coordinate local draft and preview (no output)", direction_editor))

        direction_headers = ("Semantic", "Axis", "Current invert", "Pending invert", "Saved invert", "Validation")
        self.direction_controller_table = QTableWidget(0, len(direction_headers))
        self.direction_controller_table.setObjectName("directionControllerTable")
        self.direction_controller_table.setHorizontalHeaderLabels(direction_headers)
        self.direction_controller_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.direction_controller_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.direction_controller_table.verticalHeader().setVisible(False)
        self.direction_controller_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.direction_controller_table.horizontalHeader().setStretchLastSection(True)
        self.direction_controller_table.setMinimumHeight(155)
        layout.addWidget(boxed("Controller input correction (separate from machine/motor/servo direction)", self.direction_controller_table))

        wheel_direction_headers = (
            "Wheel", "Motor current", "Motor pending", "Motor saved",
            "Servo current", "Servo pending", "Servo saved", "Servo calibrated", "Validation",
        )
        self.direction_wheel_table = QTableWidget(0, len(wheel_direction_headers))
        self.direction_wheel_table.setObjectName("directionWheelTable")
        self.direction_wheel_table.setHorizontalHeaderLabels(wheel_direction_headers)
        self.direction_wheel_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.direction_wheel_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.direction_wheel_table.verticalHeader().setVisible(False)
        self.direction_wheel_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.direction_wheel_table.horizontalHeader().setStretchLastSection(True)
        self.direction_wheel_table.setMinimumHeight(205)
        layout.addWidget(boxed("Per-wheel physical direction audit", self.direction_wheel_table))

        self.direction_preview_label = self._detail_label("directionPreview")
        layout.addWidget(boxed("No-motion vector preview", self.direction_preview_label))

        parameter_editor = QWidget()
        parameter_grid = QGridLayout(parameter_editor)
        parameter_grid.setContentsMargins(8, 8, 8, 8)
        parameter_grid.addWidget(QLabel("Parameter"), 0, 0)
        self.parameter_combo = QComboBox()
        self.parameter_combo.setObjectName("parameterEditorCombo")
        self.parameter_combo.currentIndexChanged.connect(self._parameter_selection_changed)
        parameter_grid.addWidget(self.parameter_combo, 0, 1, 1, 2)
        parameter_grid.addWidget(QLabel("Local candidate"), 0, 3)
        self.parameter_spin = QDoubleSpinBox()
        self.parameter_spin.setObjectName("parameterEditorSpin")
        self.parameter_spin.setDecimals(3)
        self.parameter_spin.valueChanged.connect(self._parameter_spin_changed)
        parameter_grid.addWidget(self.parameter_spin, 0, 4)
        self.parameter_slider = QSlider(Qt.Orientation.Horizontal)
        self.parameter_slider.setObjectName("parameterEditorSlider")
        self.parameter_slider.valueChanged.connect(self._parameter_slider_changed)
        parameter_grid.addWidget(self.parameter_slider, 1, 0, 1, 5)
        self.parameter_stage_button = QPushButton("STAGE / 候補検証")
        self.parameter_stage_button.setObjectName("parameterStageButton")
        self.parameter_stage_button.clicked.connect(self._stage_parameter_pending)
        parameter_grid.addWidget(self.parameter_stage_button, 2, 0, 1, 2)
        self.parameter_revert_button = QPushButton("REVERT / 候補取消")
        self.parameter_revert_button.setObjectName("parameterRevertButton")
        self.parameter_revert_button.clicked.connect(self._revert_parameter_pending)
        parameter_grid.addWidget(self.parameter_revert_button, 2, 2)
        self.parameter_apply_button = QPushButton("APPLY / 利用不可")
        self.parameter_apply_button.setObjectName("parameterApplyButton")
        self.parameter_apply_button.setEnabled(False)
        parameter_grid.addWidget(self.parameter_apply_button, 2, 3)
        self.parameter_save_button = QPushButton("SAVE / 利用不可")
        self.parameter_save_button.setObjectName("parameterSaveButton")
        self.parameter_save_button.setEnabled(False)
        parameter_grid.addWidget(self.parameter_save_button, 2, 4)
        self.parameter_editor_state_label = self._detail_label("parameterEditorState")
        parameter_grid.addWidget(self.parameter_editor_state_label, 3, 0, 1, 5)
        layout.addWidget(boxed("Parameter / Slider local draft (bounded PC runtime clamps only)", parameter_editor))

        parameter_headers = (
            "Key", "Group", "Current effective", "Pending", "Saved/controller-loaded",
            "Valid range", "Validation", "Revert", "Apply", "Authoritative source",
        )
        self.parameter_table = QTableWidget(0, len(parameter_headers))
        self.parameter_table.setObjectName("parameterEditorTable")
        self.parameter_table.setHorizontalHeaderLabels(parameter_headers)
        self.parameter_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parameter_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.parameter_table.verticalHeader().setVisible(False)
        self.parameter_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.parameter_table.horizontalHeader().setStretchLastSection(True)
        self.parameter_table.setMinimumHeight(255)
        layout.addWidget(boxed("Parameter current / pending / saved audit", self.parameter_table))

        editor = QWidget()
        editor_grid = QGridLayout(editor)
        editor_grid.setContentsMargins(8, 8, 8, 8)
        editor_grid.addWidget(QLabel("Servo"), 0, 0)
        self.servo_combo = QComboBox()
        self.servo_combo.setObjectName("servoZeroServoCombo")
        self.servo_combo.currentIndexChanged.connect(self._servo_selection_changed)
        editor_grid.addWidget(self.servo_combo, 0, 1)
        editor_grid.addWidget(QLabel("center_us candidate"), 0, 2)
        self.center_edit = QLineEdit()
        self.center_edit.setObjectName("servoZeroCenterEdit")
        self.center_edit.textEdited.connect(self._mark_editor_dirty)
        editor_grid.addWidget(self.center_edit, 0, 3)
        editor_grid.addWidget(QLabel("trim_deg candidate"), 0, 4)
        self.trim_edit = QLineEdit()
        self.trim_edit.setObjectName("servoZeroTrimEdit")
        self.trim_edit.textEdited.connect(self._mark_editor_dirty)
        editor_grid.addWidget(self.trim_edit, 0, 5)
        self.stage_button = QPushButton("STAGE / 原点候補検証")
        self.stage_button.setObjectName("servoZeroStageButton")
        self.stage_button.clicked.connect(self._stage_pending)
        editor_grid.addWidget(self.stage_button, 1, 0, 1, 2)
        self.revert_button = QPushButton("REVERT / 原点取消")
        self.revert_button.setObjectName("servoZeroRevertButton")
        self.revert_button.clicked.connect(self._revert_pending)
        editor_grid.addWidget(self.revert_button, 1, 2)
        self.apply_button = QPushButton("APPLY / 実機利用不可")
        self.apply_button.setObjectName("servoZeroApplyButton")
        self.apply_button.setEnabled(False)
        editor_grid.addWidget(self.apply_button, 1, 3)
        self.save_button = QPushButton("SAVE / 利用不可")
        self.save_button.setObjectName("servoZeroSaveButton")
        self.save_button.setEnabled(False)
        editor_grid.addWidget(self.save_button, 1, 4, 1, 2)
        self.editor_state_label = self._detail_label("servoZeroEditorState")
        editor_grid.addWidget(self.editor_state_label, 2, 0, 1, 6)
        editor_grid.setColumnStretch(1, 1)
        editor_grid.setColumnStretch(3, 1)
        editor_grid.setColumnStretch(5, 1)
        layout.addWidget(boxed("Servo Zero local draft (no config write / no output)", editor))

        angle_editor = QWidget()
        angle_grid = QGridLayout(angle_editor)
        angle_grid.setContentsMargins(8, 8, 8, 8)
        angle_grid.addWidget(QLabel("Servo"), 0, 0)
        self.angle_servo_combo = QComboBox()
        self.angle_servo_combo.setObjectName("servoAngleServoCombo")
        self.angle_servo_combo.currentIndexChanged.connect(self._angle_servo_selection_changed)
        angle_grid.addWidget(self.angle_servo_combo, 0, 1)
        angle_grid.addWidget(QLabel("min_us candidate"), 0, 2)
        self.min_pulse_edit = QLineEdit()
        self.min_pulse_edit.setObjectName("servoAngleMinPulseEdit")
        self.min_pulse_edit.textEdited.connect(self._mark_angle_editor_dirty)
        angle_grid.addWidget(self.min_pulse_edit, 0, 3)
        angle_grid.addWidget(QLabel("max_us candidate"), 0, 4)
        self.max_pulse_edit = QLineEdit()
        self.max_pulse_edit.setObjectName("servoAngleMaxPulseEdit")
        self.max_pulse_edit.textEdited.connect(self._mark_angle_editor_dirty)
        angle_grid.addWidget(self.max_pulse_edit, 0, 5)
        angle_grid.addWidget(QLabel("min_angle_deg candidate"), 1, 0)
        self.min_angle_edit = QLineEdit()
        self.min_angle_edit.setObjectName("servoAngleMinAngleEdit")
        self.min_angle_edit.textEdited.connect(self._mark_angle_editor_dirty)
        angle_grid.addWidget(self.min_angle_edit, 1, 1)
        angle_grid.addWidget(QLabel("max_angle_deg candidate"), 1, 2)
        self.max_angle_edit = QLineEdit()
        self.max_angle_edit.setObjectName("servoAngleMaxAngleEdit")
        self.max_angle_edit.textEdited.connect(self._mark_angle_editor_dirty)
        angle_grid.addWidget(self.max_angle_edit, 1, 3)
        self.angle_stage_button = QPushButton("STAGE / 角度候補検証")
        self.angle_stage_button.setObjectName("servoAngleStageButton")
        self.angle_stage_button.clicked.connect(self._stage_angle_pending)
        angle_grid.addWidget(self.angle_stage_button, 2, 0, 1, 2)
        self.angle_revert_button = QPushButton("REVERT / 角度取消")
        self.angle_revert_button.setObjectName("servoAngleRevertButton")
        self.angle_revert_button.clicked.connect(self._revert_angle_pending)
        angle_grid.addWidget(self.angle_revert_button, 2, 2)
        self.angle_apply_button = QPushButton("APPLY / 実機利用不可")
        self.angle_apply_button.setObjectName("servoAngleApplyButton")
        self.angle_apply_button.setEnabled(False)
        angle_grid.addWidget(self.angle_apply_button, 2, 3)
        self.angle_save_button = QPushButton("SAVE / 利用不可")
        self.angle_save_button.setObjectName("servoAngleSaveButton")
        self.angle_save_button.setEnabled(False)
        angle_grid.addWidget(self.angle_save_button, 2, 4, 1, 2)
        self.angle_editor_state_label = self._detail_label("servoAngleEditorState")
        angle_grid.addWidget(self.angle_editor_state_label, 3, 0, 1, 6)
        angle_grid.setColumnStretch(1, 1)
        angle_grid.setColumnStretch(3, 1)
        angle_grid.setColumnStretch(5, 1)
        layout.addWidget(boxed("Servo Angle endpoint draft (no config write / no output)", angle_editor))

        headers = (
            "Robot", "Servo", "Logical", "Channel", "Current center_us", "Current trim",
            "Command angle", "Observed angle", "Calibrated", "Pending", "Saved",
            "Validation", "Revert", "Apply state",
        )
        self.servo_table = QTableWidget(0, len(headers))
        self.servo_table.setObjectName("calibrationServoTable")
        self.servo_table.setHorizontalHeaderLabels(headers)
        self.servo_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.servo_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.servo_table.setAlternatingRowColors(True)
        self.servo_table.verticalHeader().setVisible(False)
        self.servo_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.servo_table.horizontalHeader().setStretchLastSection(True)
        self.servo_table.setMinimumHeight(250)
        layout.addWidget(boxed("Servo zero / angle configuration audit", self.servo_table))

        angle_headers = (
            "Robot", "Servo", "Current pulses", "Current angles", "Direction", "Command", "Observed",
            "Pending endpoints", "Saved endpoints", "Validation", "Revert", "Apply", "Physical evidence",
        )
        self.angle_table = QTableWidget(0, len(angle_headers))
        self.angle_table.setObjectName("calibrationServoAngleTable")
        self.angle_table.setHorizontalHeaderLabels(angle_headers)
        self.angle_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.angle_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.angle_table.setAlternatingRowColors(True)
        self.angle_table.verticalHeader().setVisible(False)
        self.angle_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.angle_table.horizontalHeader().setStretchLastSection(True)
        self.angle_table.setMinimumHeight(230)
        layout.addWidget(boxed("Servo Angle endpoint audit", self.angle_table))

        self.state_note_label = self._detail_label("calibrationStateNote")
        layout.addWidget(self.state_note_label)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(make_scroll_area(content))

    @staticmethod
    def _detail_label(object_name: str) -> QLabel:
        label = QLabel()
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _render_no_snapshot(self) -> None:
        for value, button in self._robot_buttons.items():
            button.setChecked(value == self._selected_robot)
        self._diagnostic = None
        self._adjustment = None
        self._angle_adjustment = None
        self._direction_adjustment = None
        self._parameter_adjustment = None
        self.snapshot_time_label.setText("snapshot: 未接続")
        self.selected_state_label.setText(f"{self._selected_robot} | OFFLINE | UNKNOWN | READY=false")
        self.workflow_state_label.setText("workflow=UNAVAILABLE")
        self.boundary_label.setText("Calibration controller API=UNAVAILABLE | output=BLOCKED")
        self.fault_banner.setText("WARNING: shared snapshot が未接続です。")
        self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        self.servo_table.setRowCount(0)
        self.direction_controller_table.setRowCount(0)
        self.direction_wheel_table.setRowCount(0)
        self.direction_preview_label.setText("No shared Direction snapshot | output=BLOCKED")
        self._sync_direction_editor(None)
        self.parameter_table.setRowCount(0)
        self._sync_parameter_editor(None)
        self._sync_servo_editor(None)
        self.angle_table.setRowCount(0)
        self._sync_angle_editor(None)
        self.state_note_label.setText("No shared calibration snapshot")

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return
        diagnostic = build_calibration_diagnostic_snapshot(robot)
        self._diagnostic = diagnostic
        adjustment = self._drafts.build(diagnostic)
        angle_adjustment = self._angle_drafts.build(diagnostic)
        direction_adjustment = self._direction_drafts.build(
            robot,
            preview_input=self._direction_preview_input(),
        )
        parameter_adjustment = self._parameter_drafts.build(robot)
        self._adjustment = adjustment
        self._angle_adjustment = angle_adjustment
        self._direction_adjustment = direction_adjustment
        self._parameter_adjustment = parameter_adjustment
        self.snapshot_time_label.setText(f"snapshot: {diagnostic.timestamp_ms} ms")
        states = [diagnostic.robot_id, diagnostic.connection, diagnostic.safety_state]
        states.append("READY" if diagnostic.ready else "NOT_READY")
        states.append("ARMED" if diagnostic.armed else "DISARMED")
        self.selected_state_label.setText(" | ".join(states))
        self.workflow_state_label.setText(
            f"direction workflow={direction_adjustment.workflow_state} | "
            f"parameter workflow={parameter_adjustment.workflow_state} | "
            f"zero workflow={adjustment.workflow_state} | angle workflow={angle_adjustment.workflow_state}\n"
            f"current/saved=controller-loaded config | zero local pending={adjustment.pending_count} | "
            f"angle local pending={angle_adjustment.pending_count} | "
            f"direction pending fields={direction_adjustment.pending_count}\n"
            f"parameter local pending={parameter_adjustment.pending_count} "
            f"(invalid={parameter_adjustment.invalid_count})\n"
            "validation/revert are local-only; apply/save remain blocked"
        )
        self.boundary_label.setText(
            f"Controller API={diagnostic.controller_api_state}\noutput={diagnostic.output_state}\n"
            "Editor changes only create a local draft and can never produce immediate hardware output. "
            "Future output requires SAFE -> explicit DEBUG -> one bounded servo -> confirm/save -> SAFE."
        )
        self._render_fault(diagnostic)
        self._render_direction(direction_adjustment)
        self._render_parameters(parameter_adjustment)
        self._render_servos(adjustment)
        self._render_angles(angle_adjustment)
        self._sync_direction_editor(direction_adjustment)
        self._sync_parameter_editor(parameter_adjustment)
        self._sync_servo_editor(adjustment)
        self._sync_angle_editor(angle_adjustment)
        if diagnostic.servos:
            self.state_note_label.setText(
                "Saved values are the controller-loaded config snapshot, not a live disk reread. "
                "Pending values exist only in this widget's memory. Validation is numeric/config-range evidence only; "
                "angle drafts use the controller-loaded center/trim/direction base. Physical zero, linkage angle, "
                "Direction drafts keep controller input, machine axes, motor polarity, servo direction, and logical front separate. "
                "Parameter sliders are limited to documented PC runtime clamps and do not write on movement or staging. "
                "DPI, config persistence, physical direction, and hardware output are unvalidated."
            )
        else:
            self.state_note_label.setText("No authoritative servo configuration is available for this robot.")

    def _render_fault(self, diagnostic: CalibrationDiagnosticSnapshot) -> None:
        event = diagnostic.fault_event
        if event is not None:
            self.fault_banner.setText(
                f"FAULT | source={event.source} | node={event.node_id or '-'} | reason={event.reason}\n"
                f"Safety response={event.safety_response} | calibration output remains BLOCKED"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
        elif diagnostic.fault:
            self.fault_banner.setText(f"FAULT | {diagnostic.fault} | calibration output remains BLOCKED")
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
        elif diagnostic.warnings:
            self.fault_banner.setText("WARNING | " + " | ".join(diagnostic.warnings))
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        else:
            self.fault_banner.setText("No active robot fault or warning | calibration output BLOCKED")
            self.fault_banner.setStyleSheet("background:#14532d; color:#dcfce7; padding:12px; font-weight:800;")

    def _render_direction(self, adjustment: DirectionCalibrationSnapshot) -> None:
        self.direction_controller_table.setRowCount(len(adjustment.controller_rows))
        for row, item in enumerate(adjustment.controller_rows):
            values = (
                item.semantic,
                _value(item.axis_index),
                _direction_value(item.current_inverted),
                _direction_value(item.pending_inverted, pending=True),
                _direction_value(item.saved_inverted),
                item.validation,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.direction_controller_table.setItem(row, column, cell)

        self.direction_wheel_table.setRowCount(len(adjustment.wheel_rows))
        for row, item in enumerate(adjustment.wheel_rows):
            values = (
                item.logical_name,
                _direction_value(item.current_motor_inverted),
                _direction_value(item.pending_motor_inverted, pending=True),
                _direction_value(item.saved_motor_inverted),
                _direction_value(item.current_servo_inverted),
                _direction_value(item.pending_servo_inverted, pending=True),
                _direction_value(item.saved_servo_inverted),
                "UNKNOWN" if item.servo_calibrated is None else "YES" if item.servo_calibrated else "NO",
                item.validation,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.direction_wheel_table.setItem(row, column, cell)

        preview = adjustment.preview
        self.direction_preview_label.setText(
            f"Machine convention: +X={adjustment.machine_x_positive} / +Y={adjustment.machine_y_positive} / "
            f"+omega={adjustment.machine_omega_positive}\n"
            f"Logical front current={adjustment.current_logical_front} / "
            f"pending={adjustment.pending_logical_front or 'NONE'} / saved={adjustment.saved_logical_front}\n"
            f"Affected axes: {adjustment.affected_axes}\n"
            f"raw controller: {_vector(preview.raw_controller)}\n"
            f"corrected controller: {_vector(preview.corrected_controller)}\n"
            f"machine-relative scaled: {_vector(preview.machine_relative)}\n"
            f"logical-front transformed: {_vector(preview.logical_front_transformed)}\n"
            f"final vx/vy/omega preview: {_vector(preview.final_command_preview)}\n"
            f"preview={preview.validation} | draft={adjustment.validation} | "
            f"pivot_direction_inverted={_direction_value(adjustment.pivot_direction_inverted)} "
            "(separate pure-pivot motion correction; not applied to this coordinate preview)"
        )

    def _render_servos(self, adjustment: ServoZeroAdjustmentSnapshot) -> None:
        self.servo_table.setRowCount(len(adjustment.rows))
        for row, servo in enumerate(adjustment.rows):
            pending = _pending(servo.pending_center_us_text, servo.pending_trim_deg_text)
            saved = f"{_value(servo.saved_center_us)} us / {_value(servo.saved_trim_deg)} deg"
            values = (
                adjustment.robot_id,
                servo.logical_name,
                servo.logical_index,
                _value(servo.channel),
                _value(servo.current_center_us),
                _value(servo.current_trim_deg),
                _angle(servo.current_command_angle_deg),
                _angle(servo.observed_angle_deg),
                "UNKNOWN" if servo.calibrated is None else "YES" if servo.calibrated else "NO",
                pending,
                saved,
                servo.validation,
                servo.revert_state,
                servo.apply_state,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.servo_table.setItem(row, column, item)

    def _render_parameters(self, adjustment: ParameterEditorSnapshot) -> None:
        self.parameter_table.setRowCount(len(adjustment.rows))
        for row, parameter in enumerate(adjustment.rows):
            pending = "NONE" if parameter.pending_raw is None else parameter.pending_raw
            valid_range = (
                f"{_parameter_value(parameter.minimum, parameter.step)}.."
                f"{_parameter_value(parameter.maximum, parameter.step)} {parameter.unit}"
            )
            values = (
                parameter.key,
                parameter.group,
                _parameter_value(parameter.current_value, parameter.step),
                pending,
                _parameter_value(parameter.saved_controller_loaded_value, parameter.step),
                valid_range,
                parameter.validation,
                parameter.revert_state,
                parameter.apply_state,
                parameter.source,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.parameter_table.setItem(row, column, item)

    def _render_angles(self, adjustment: ServoAngleAdjustmentSnapshot) -> None:
        self.angle_table.setRowCount(len(adjustment.rows))
        for row, servo in enumerate(adjustment.rows):
            current_pulses = f"{_value(servo.current_min_us)} / {_value(servo.current_max_us)} us"
            current_angles = (
                f"{_value(servo.current_min_angle_deg)} / {_value(servo.current_max_angle_deg)} deg"
            )
            pending = _angle_pending(servo)
            saved = (
                f"{_value(servo.saved_min_us)}..{_value(servo.saved_max_us)} us | "
                f"{_value(servo.saved_min_angle_deg)}..{_value(servo.saved_max_angle_deg)} deg"
            )
            direction = (
                "UNKNOWN"
                if servo.direction_inverted is None
                else "INVERTED" if servo.direction_inverted else "NORMAL"
            )
            values = (
                adjustment.robot_id,
                servo.logical_name,
                current_pulses,
                current_angles,
                direction,
                _angle(servo.current_command_angle_deg),
                _angle(servo.observed_angle_deg),
                pending,
                saved,
                servo.validation,
                servo.revert_state,
                servo.apply_state,
                servo.hardware_validation_state,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.angle_table.setItem(row, column, item)

    def _sync_direction_editor(self, adjustment: DirectionCalibrationSnapshot | None) -> None:
        configured = bool(adjustment is not None and adjustment.configured)
        controls = (
            self.invert_vx_check,
            self.invert_vy_check,
            self.invert_omega_check,
            self.logical_front_combo,
            self.direction_raw_vx_edit,
            self.direction_raw_vy_edit,
            self.direction_raw_omega_edit,
            self.direction_stage_button,
            *self._motor_invert_checks,
            *self._servo_invert_checks,
        )
        for control in controls:
            control.setEnabled(configured)
        self.direction_revert_button.setEnabled(
            bool(adjustment is not None and adjustment.revert_state == "AVAILABLE_LOCAL_ONLY")
        )
        if adjustment is None or not configured:
            self.direction_editor_state_label.setText("No configured Direction source for selected robot | output=BLOCKED")
            return

        if not self._direction_editor_dirty:
            controller_values = tuple(
                row.pending_inverted if row.pending_inverted is not None else row.current_inverted
                for row in adjustment.controller_rows
            )
            for check, value in zip(
                (self.invert_vx_check, self.invert_vy_check, self.invert_omega_check),
                controller_values,
            ):
                check.blockSignals(True)
                check.setChecked(bool(value))
                check.blockSignals(False)
            front = adjustment.pending_logical_front or adjustment.current_logical_front
            self.logical_front_combo.blockSignals(True)
            front_index = self.logical_front_combo.findText(front)
            self.logical_front_combo.setCurrentIndex(max(0, front_index))
            self.logical_front_combo.blockSignals(False)
            for row, motor_check, servo_check in zip(
                adjustment.wheel_rows,
                self._motor_invert_checks,
                self._servo_invert_checks,
            ):
                motor = row.pending_motor_inverted if row.pending_motor_inverted is not None else row.current_motor_inverted
                servo = row.pending_servo_inverted if row.pending_servo_inverted is not None else row.current_servo_inverted
                motor_check.blockSignals(True)
                motor_check.setChecked(bool(motor))
                motor_check.blockSignals(False)
                servo_check.blockSignals(True)
                servo_check.setChecked(bool(servo))
                servo_check.blockSignals(False)

        self.direction_editor_state_label.setText(
            f"{adjustment.robot_id} | current=runtime/controller-loaded | pending=widget memory | "
            f"saved logical front={adjustment.saved_logical_front} | validation={adjustment.validation} | "
            f"revert={adjustment.revert_state} | apply={adjustment.apply_state} | save={adjustment.save_state} | "
            f"output={adjustment.output_state}"
        )

    def _sync_servo_editor(self, adjustment: ServoZeroAdjustmentSnapshot | None) -> None:
        rows = () if adjustment is None else adjustment.rows
        desired = tuple((row.logical_index, f"{row.logical_name} / logical {row.logical_index}") for row in rows)
        current = tuple(
            (self.servo_combo.itemData(index), self.servo_combo.itemText(index))
            for index in range(self.servo_combo.count())
        )
        selected_index = self.servo_combo.currentData()
        if current != desired:
            self.servo_combo.blockSignals(True)
            self.servo_combo.clear()
            for logical_index, label in desired:
                self.servo_combo.addItem(label, logical_index)
            if selected_index is not None:
                index = self.servo_combo.findData(selected_index)
                if index >= 0:
                    self.servo_combo.setCurrentIndex(index)
            self.servo_combo.blockSignals(False)
        enabled = bool(rows)
        self.servo_combo.setEnabled(enabled)
        self.center_edit.setEnabled(enabled)
        self.trim_edit.setEnabled(enabled)
        self.stage_button.setEnabled(enabled)
        if not enabled:
            self.center_edit.clear()
            self.trim_edit.clear()
            self.revert_button.setEnabled(False)
            self.editor_state_label.setText("No configured servo for the selected robot | output=BLOCKED")
            return
        self._load_selected_editor(force=False)

    def _sync_parameter_editor(self, adjustment: ParameterEditorSnapshot | None) -> None:
        rows = () if adjustment is None else adjustment.rows
        desired = tuple((row.key, f"{row.label} [{row.unit}]") for row in rows)
        current = tuple(
            (self.parameter_combo.itemData(index), self.parameter_combo.itemText(index))
            for index in range(self.parameter_combo.count())
        )
        selected_key = self.parameter_combo.currentData()
        if current != desired:
            self.parameter_combo.blockSignals(True)
            self.parameter_combo.clear()
            for key, label in desired:
                self.parameter_combo.addItem(label, key)
            if selected_key is not None:
                index = self.parameter_combo.findData(selected_key)
                if index >= 0:
                    self.parameter_combo.setCurrentIndex(index)
            self.parameter_combo.blockSignals(False)
        enabled = bool(adjustment is not None and adjustment.configured and rows)
        self.parameter_combo.setEnabled(enabled)
        self.parameter_spin.setEnabled(enabled)
        self.parameter_slider.setEnabled(enabled)
        self.parameter_stage_button.setEnabled(enabled)
        if not enabled:
            self.parameter_revert_button.setEnabled(False)
            self.parameter_editor_state_label.setText(
                "No configured bounded Parameter source for selected robot | output=BLOCKED"
            )
            return
        self._load_selected_parameter(force=False)

    def _sync_angle_editor(self, adjustment: ServoAngleAdjustmentSnapshot | None) -> None:
        rows = () if adjustment is None else adjustment.rows
        desired = tuple((row.logical_index, f"{row.logical_name} / logical {row.logical_index}") for row in rows)
        current = tuple(
            (self.angle_servo_combo.itemData(index), self.angle_servo_combo.itemText(index))
            for index in range(self.angle_servo_combo.count())
        )
        selected_index = self.angle_servo_combo.currentData()
        if current != desired:
            self.angle_servo_combo.blockSignals(True)
            self.angle_servo_combo.clear()
            for logical_index, label in desired:
                self.angle_servo_combo.addItem(label, logical_index)
            if selected_index is not None:
                index = self.angle_servo_combo.findData(selected_index)
                if index >= 0:
                    self.angle_servo_combo.setCurrentIndex(index)
            self.angle_servo_combo.blockSignals(False)
        enabled = bool(rows)
        self.angle_servo_combo.setEnabled(enabled)
        self.min_pulse_edit.setEnabled(enabled)
        self.max_pulse_edit.setEnabled(enabled)
        self.min_angle_edit.setEnabled(enabled)
        self.max_angle_edit.setEnabled(enabled)
        self.angle_stage_button.setEnabled(enabled)
        if not enabled:
            self.min_pulse_edit.clear()
            self.max_pulse_edit.clear()
            self.min_angle_edit.clear()
            self.max_angle_edit.clear()
            self.angle_revert_button.setEnabled(False)
            self.angle_editor_state_label.setText(
                "No configured servo for the selected robot | angle output=BLOCKED"
            )
            return
        self._load_selected_angle_editor(force=False)

    def _servo_selection_changed(self, _index: int) -> None:
        self._editor_dirty = False
        self._load_selected_editor(force=True)

    def _angle_servo_selection_changed(self, _index: int) -> None:
        self._angle_editor_dirty = False
        self._load_selected_angle_editor(force=True)

    def _parameter_selection_changed(self, _index: int) -> None:
        self._parameter_editor_dirty = False
        self._load_selected_parameter(force=True)

    def _mark_editor_dirty(self, _text: str) -> None:
        self._editor_dirty = True

    def _mark_angle_editor_dirty(self, _text: str) -> None:
        self._angle_editor_dirty = True

    def _mark_direction_editor_dirty(self, _value: object) -> None:
        self._direction_editor_dirty = True

    def _parameter_spin_changed(self, value: float) -> None:
        if self._parameter_syncing:
            return
        row = self._selected_parameter_row()
        if row is None:
            return
        self._parameter_editor_dirty = True
        slider_value = round((value - row.minimum) / row.step)
        self._parameter_syncing = True
        self.parameter_slider.setValue(slider_value)
        self._parameter_syncing = False

    def _parameter_slider_changed(self, value: int) -> None:
        if self._parameter_syncing:
            return
        row = self._selected_parameter_row()
        if row is None:
            return
        self._parameter_editor_dirty = True
        candidate = row.minimum + value * row.step
        self._parameter_syncing = True
        self.parameter_spin.setValue(candidate)
        self._parameter_syncing = False

    def _direction_preview_input(self) -> tuple[str, str, str]:
        return (
            self.direction_raw_vx_edit.text(),
            self.direction_raw_vy_edit.text(),
            self.direction_raw_omega_edit.text(),
        )

    def _selected_adjustment_row(self) -> ServoZeroRowSnapshot | None:
        if self._adjustment is None:
            return None
        logical_index = self.servo_combo.currentData()
        for row in self._adjustment.rows:
            if row.logical_index == logical_index:
                return row
        return None

    def _selected_angle_row(self) -> ServoAngleRowSnapshot | None:
        if self._angle_adjustment is None:
            return None
        logical_index = self.angle_servo_combo.currentData()
        for row in self._angle_adjustment.rows:
            if row.logical_index == logical_index:
                return row
        return None

    def _selected_parameter_row(self) -> ParameterRowSnapshot | None:
        if self._parameter_adjustment is None:
            return None
        key = self.parameter_combo.currentData()
        for row in self._parameter_adjustment.rows:
            if row.key == key:
                return row
        return None

    def _load_selected_editor(self, *, force: bool) -> None:
        row = self._selected_adjustment_row()
        if row is None:
            return
        if force or not self._editor_dirty:
            center = row.pending_center_us_text
            trim = row.pending_trim_deg_text
            self.center_edit.setText(str(row.current_center_us) if center is None else center)
            self.trim_edit.setText(str(row.current_trim_deg) if trim is None else trim)
            self._editor_dirty = False
        self.revert_button.setEnabled(row.has_pending)
        self.editor_state_label.setText(
            f"{row.robot_id}/{row.logical_name} channel={_value(row.channel)} | "
            f"allowed center range={_value(row.min_us)} < value < {_value(row.max_us)} | "
            f"validation={row.validation} | revert={row.revert_state} | "
            f"apply={row.apply_state} | save={row.save_state}"
        )

    def _load_selected_angle_editor(self, *, force: bool) -> None:
        row = self._selected_angle_row()
        if row is None:
            return
        if force or not self._angle_editor_dirty:
            values = (
                (row.pending_min_us_text, row.current_min_us),
                (row.pending_max_us_text, row.current_max_us),
                (row.pending_min_angle_deg_text, row.current_min_angle_deg),
                (row.pending_max_angle_deg_text, row.current_max_angle_deg),
            )
            edits = (self.min_pulse_edit, self.max_pulse_edit, self.min_angle_edit, self.max_angle_edit)
            for edit, (pending, current) in zip(edits, values):
                edit.setText(str(current) if pending is None else pending)
            self._angle_editor_dirty = False
        self.angle_revert_button.setEnabled(row.has_pending)
        direction = (
            "UNKNOWN"
            if row.direction_inverted is None
            else "INVERTED" if row.direction_inverted else "NORMAL"
        )
        self.angle_editor_state_label.setText(
            f"{row.robot_id}/{row.logical_name} channel={_value(row.channel)} | "
            f"center={_value(row.current_center_us)} us | trim={_value(row.current_trim_deg)} deg | "
            f"direction={direction} (read-only) | validation={row.validation} | "
            f"physical={row.hardware_validation_state} | apply={row.apply_state} | save={row.save_state}"
        )

    def _load_selected_parameter(self, *, force: bool) -> None:
        row = self._selected_parameter_row()
        if row is None:
            return
        steps = round((row.maximum - row.minimum) / row.step)
        self._parameter_syncing = True
        self.parameter_spin.setRange(row.minimum, row.maximum)
        self.parameter_spin.setSingleStep(row.step)
        self.parameter_spin.setDecimals(0 if row.step >= 1.0 else 3)
        self.parameter_slider.setRange(0, steps)
        self.parameter_slider.setSingleStep(1)
        if force or not self._parameter_editor_dirty:
            value = row.pending_value if row.pending_value is not None else row.current_value
            value = row.minimum if value is None else value
            self.parameter_spin.setValue(value)
            self.parameter_slider.setValue(round((value - row.minimum) / row.step))
            self._parameter_editor_dirty = False
        self._parameter_syncing = False
        self.parameter_revert_button.setEnabled(row.pending_raw is not None)
        self.parameter_editor_state_label.setText(
            f"{row.key} | current effective={_parameter_value(row.current_value, row.step)} | "
            f"pending={row.pending_raw or 'NONE'} | "
            f"saved/controller-loaded={_parameter_value(row.saved_controller_loaded_value, row.step)} | "
            f"range={row.minimum:g}..{row.maximum:g} {row.unit} | validation={row.validation} | "
            f"revert={row.revert_state} | apply={row.apply_state} | slider movement=no output"
        )

    def _stage_pending(self) -> None:
        if self._diagnostic is None:
            return
        logical_index = self.servo_combo.currentData()
        if logical_index is None:
            return
        self._editor_dirty = False
        self._adjustment = self._drafts.stage(
            self._diagnostic,
            int(logical_index),
            center_us_text=self.center_edit.text(),
            trim_deg_text=self.trim_edit.text(),
        )
        self._render_selected()

    def _stage_direction_pending(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None or not bool(getattr(robot, "configured", False)):
            return
        self._direction_editor_dirty = False
        self._direction_adjustment = self._direction_drafts.stage(
            robot,
            invert_vx=self.invert_vx_check.isChecked(),
            invert_vy=self.invert_vy_check.isChecked(),
            invert_omega=self.invert_omega_check.isChecked(),
            logical_front=self.logical_front_combo.currentText(),
            motor_inverted=tuple(check.isChecked() for check in self._motor_invert_checks),
            servo_inverted=tuple(check.isChecked() for check in self._servo_invert_checks),
            preview_input=self._direction_preview_input(),
        )
        self._render_selected()

    def _revert_direction_pending(self) -> None:
        self._direction_editor_dirty = False
        self._direction_drafts.revert(self._selected_robot)
        self._render_selected()

    def _stage_parameter_pending(self) -> None:
        robot = self._robots.get(self._selected_robot)
        key = self.parameter_combo.currentData()
        if robot is None or not bool(getattr(robot, "configured", False)) or key is None:
            return
        self._parameter_editor_dirty = False
        self._parameter_adjustment = self._parameter_drafts.stage(
            robot,
            str(key),
            self.parameter_spin.value(),
        )
        self._render_selected()

    def _revert_parameter_pending(self) -> None:
        key = self.parameter_combo.currentData()
        if key is None:
            return
        self._parameter_editor_dirty = False
        self._parameter_drafts.revert(self._selected_robot, str(key))
        self._render_selected()

    def _revert_pending(self) -> None:
        if self._diagnostic is None:
            return
        logical_index = self.servo_combo.currentData()
        if logical_index is None:
            return
        self._editor_dirty = False
        self._drafts.revert(self._diagnostic.robot_id, int(logical_index))
        self._render_selected()

    def _stage_angle_pending(self) -> None:
        if self._diagnostic is None:
            return
        logical_index = self.angle_servo_combo.currentData()
        if logical_index is None:
            return
        self._angle_editor_dirty = False
        self._angle_adjustment = self._angle_drafts.stage(
            self._diagnostic,
            int(logical_index),
            min_us_text=self.min_pulse_edit.text(),
            max_us_text=self.max_pulse_edit.text(),
            min_angle_deg_text=self.min_angle_edit.text(),
            max_angle_deg_text=self.max_angle_edit.text(),
        )
        self._render_selected()

    def _revert_angle_pending(self) -> None:
        if self._diagnostic is None:
            return
        logical_index = self.angle_servo_combo.currentData()
        if logical_index is None:
            return
        self._angle_editor_dirty = False
        self._angle_drafts.revert(self._diagnostic.robot_id, int(logical_index))
        self._render_selected()


def _value(value: object | None) -> str:
    return "UNKNOWN" if value is None else str(value)


def _angle(value: float | None) -> str:
    return "UNKNOWN" if value is None else f"{value:+.1f} deg"


def _direction_value(value: bool | None, *, pending: bool = False) -> str:
    if value is None:
        return "NONE" if pending else "UNKNOWN"
    return "INVERTED" if value else "NORMAL"


def _vector(stage: object) -> str:
    values = (getattr(stage, "vx", None), getattr(stage, "vy", None), getattr(stage, "omega", None))
    if any(value is None for value in values):
        return "vx=UNKNOWN / vy=UNKNOWN / omega=UNKNOWN"
    return f"vx={float(values[0]):+.4f} / vy={float(values[1]):+.4f} / omega={float(values[2]):+.4f}"


def _parameter_value(value: float | None, step: float) -> str:
    if value is None:
        return "UNKNOWN"
    if step >= 1.0:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _pending(center_us_text: str | None, trim_deg_text: str | None) -> str:
    if center_us_text is None and trim_deg_text is None:
        return "NONE"
    return f"{center_us_text or 'INVALID'} us / {trim_deg_text or 'INVALID'} deg"


def _angle_pending(row: ServoAngleRowSnapshot) -> str:
    if not row.has_pending:
        return "NONE"
    return (
        f"{row.pending_min_us_text or 'INVALID'}..{row.pending_max_us_text or 'INVALID'} us | "
        f"{row.pending_min_angle_deg_text or 'INVALID'}.."
        f"{row.pending_max_angle_deg_text or 'INVALID'} deg"
    )


def create_calibration_diagnostic_tab(host: Any) -> CalibrationDiagnosticWidget:
    widget = CalibrationDiagnosticWidget()
    host.calibration_diagnostic_widget = widget
    return widget
