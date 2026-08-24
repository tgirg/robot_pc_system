from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from ..field import FieldModel, FieldObject, FieldRect, FieldRenderer
    from ..odometry import OdometryState
    from ..sensors import is_sensor_active, status_label
except ImportError:
    from field import FieldModel, FieldObject, FieldRect, FieldRenderer
    from odometry import OdometryState
    from sensors import is_sensor_active, status_label


SCALE_OPTIONS = {
    "自動": None,
    "50%": 0.50,
    "100%": 1.00,
    "150%": 1.50,
    "200%": 2.00,
}

OBJECT_TEMPLATES = {
    "black_brick": {
        "label": "黒レンガ",
        "width_mm": 240.0,
        "height_mm": 120.0,
        "color": "#111827",
    },
    "white_brick": {
        "label": "白レンガ",
        "width_mm": 240.0,
        "height_mm": 120.0,
        "color": "#f8fafc",
    },
    "watering_can": {
        "label": "じょうろ",
        "width_mm": 220.0,
        "height_mm": 180.0,
        "color": "#38bdf8",
    },
    "generic": {
        "label": "確認オブジェクト",
        "width_mm": 180.0,
        "height_mm": 180.0,
        "color": "#facc15",
    },
}


class TestFieldCanvas(QWidget):
    mouse_mm_changed = Signal(float, float)
    field_clicked = Signal(float, float)
    object_selected = Signal(str)
    object_dragged = Signal(str, float, float)

    def __init__(self, field_model: FieldModel) -> None:
        super().__init__()
        self.setMinimumSize(720, 430)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.model = field_model
        self.renderer = FieldRenderer(field_model)
        self.state = OdometryState()
        self.trail: list[tuple[float, float]] = []
        self.scale_mode = "auto"
        self.manual_scale = 1.0
        self.display_mode = "official"
        self.show_grid = True
        self.show_zone_labels = True
        self.show_walls = True
        self.show_lines = True
        self.show_trail = True
        self.show_lidar = False
        self.lidar_active = False
        self.show_mouse_coordinate = True
        self.show_r1 = True
        self.show_r2 = True
        self.show_coordinate_label = True
        self.show_dimensions = True
        self.show_objects = True
        self.object_edit_mode = False
        self.mouse_mm: tuple[float, float] | None = None
        self.last_px_per_mm = 1.0
        self.r1_pose = field_model.get_robot_initial_pose("r1")
        self.selected_object_name = ""
        self.drag_object_name = ""
        self.drag_offset_mm = (0.0, 0.0)

    def set_scale(self, mode: str, value: float | None = None) -> None:
        self.scale_mode = mode
        if value is not None:
            self.manual_scale = max(0.1, min(5.0, float(value)))
        self.update()

    def set_r1_pose(self, pose: tuple[float, float, float]) -> None:
        self.r1_pose = pose
        self.update()

    def set_selected_object(self, object_name: str) -> None:
        self.selected_object_name = object_name
        self.update()

    def set_display_options(
        self,
        *,
        display_mode: str | None = None,
        show_grid: bool | None = None,
        show_zone_labels: bool | None = None,
        show_walls: bool | None = None,
        show_lines: bool | None = None,
        show_trail: bool | None = None,
        show_lidar: bool | None = None,
        lidar_active: bool | None = None,
        show_mouse_coordinate: bool | None = None,
        show_r1: bool | None = None,
        show_r2: bool | None = None,
        show_coordinate_label: bool | None = None,
        show_dimensions: bool | None = None,
        show_objects: bool | None = None,
        object_edit_mode: bool | None = None,
    ) -> None:
        if display_mode is not None:
            self.display_mode = display_mode
        if show_grid is not None:
            self.show_grid = show_grid
        if show_zone_labels is not None:
            self.show_zone_labels = show_zone_labels
        if show_walls is not None:
            self.show_walls = show_walls
        if show_lines is not None:
            self.show_lines = show_lines
        if show_trail is not None:
            self.show_trail = show_trail
        if show_lidar is not None:
            self.show_lidar = show_lidar
        if lidar_active is not None:
            self.lidar_active = lidar_active
        if show_mouse_coordinate is not None:
            self.show_mouse_coordinate = show_mouse_coordinate
        if show_r1 is not None:
            self.show_r1 = show_r1
        if show_r2 is not None:
            self.show_r2 = show_r2
        if show_coordinate_label is not None:
            self.show_coordinate_label = show_coordinate_label
        if show_dimensions is not None:
            self.show_dimensions = show_dimensions
        if show_objects is not None:
            self.show_objects = show_objects
        if object_edit_mode is not None:
            self.object_edit_mode = object_edit_mode
        self.update()

    def update_state(self, state: OdometryState, append_trail: bool = True) -> None:
        self.state = state
        if state.has_data:
            point = (state.x_mm, state.y_mm)
            if append_trail and (not self.trail or math.hypot(self.trail[-1][0] - point[0], self.trail[-1][1] - point[1]) >= 1.0):
                self.trail.append(point)
                if len(self.trail) > 3000:
                    self.trail = self.trail[-3000:]
        self.update()

    def clear_trail(self) -> None:
        self.trail.clear()
        if self.state.has_data:
            self.trail.append((self.state.x_mm, self.state.y_mm))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050806"))
        zoom = 1.0 if self.scale_mode == "auto" else self.manual_scale
        self.last_px_per_mm = self.renderer.fit_to_widget(self.width(), self.height(), zoom)

        self.renderer.draw_field_background(painter)
        if self.display_mode == "official":
            self.renderer.draw_zones(painter, show_labels=self.show_zone_labels)
            if self.show_grid:
                self.renderer.draw_grid(painter)
            if self.show_lines:
                self.renderer.draw_lines(painter)
            if self.show_walls:
                self.renderer.draw_wood_frame(painter)
        else:
            self._draw_simple_field(painter)

        if self.show_objects:
            self.renderer.draw_objects(painter, show_labels=True)
            if self.object_edit_mode:
                self._draw_object_edit_hint(painter)

        if self.show_trail and len(self.trail) >= 2:
            self.renderer.draw_odometry_trail(painter, self.trail)
        if self.state.has_data and self.show_trail:
            self.renderer.draw_start_line(painter, self.state.start_x_mm, self.state.start_y_mm, self.state.x_mm, self.state.y_mm)
        if self.state.has_data and self.show_lidar and self.lidar_active:
            self.renderer.draw_lidar_rays(painter, self.state.x_mm, self.state.y_mm, self.state.theta_deg)

        if self.show_r1:
            self.renderer.draw_robot(
                painter,
                self.r1_pose[0],
                self.r1_pose[1],
                self.r1_pose[2],
                label=self.model.get_robot_label("r1"),
                color=self.model.get_robot_color("r1"),
                show_coordinate_label=self.show_coordinate_label,
            )
        if self.show_r2 and self.state.has_data:
            self.renderer.draw_robot(
                painter,
                self.state.x_mm,
                self.state.y_mm,
                self.state.theta_deg,
                label=self.model.get_robot_label("r2"),
                color=self.model.get_robot_color("r2"),
                show_coordinate_label=self.show_coordinate_label,
                large=True,
            )

        if self.show_mouse_coordinate and self.mouse_mm is not None:
            self.renderer.draw_mouse_coordinate(painter, self.mouse_mm[0], self.mouse_mm[1])

    def mouseMoveEvent(self, event) -> None:
        x_mm, y_mm = self.renderer.px_to_mm(event.position().x(), event.position().y())
        self.mouse_mm = (x_mm, y_mm)
        self.mouse_mm_changed.emit(x_mm, y_mm)
        if self.object_edit_mode and self.drag_object_name:
            left = x_mm - self.drag_offset_mm[0]
            top = y_mm - self.drag_offset_mm[1]
            self.object_dragged.emit(self.drag_object_name, left, top)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            x_mm, y_mm = self.renderer.px_to_mm(event.position().x(), event.position().y())
            if self.object_edit_mode and self.show_objects:
                item = self.model.get_object_at(x_mm, y_mm)
                if item is not None:
                    self.drag_object_name = item.name
                    self.drag_offset_mm = (x_mm - item.rect.x_mm, y_mm - item.rect.y_mm)
                    self.object_selected.emit(item.name)
                    return
            self.field_clicked.emit(x_mm, y_mm)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_object_name = ""
            self.drag_offset_mm = (0.0, 0.0)

    def leaveEvent(self, event) -> None:
        self.mouse_mm = None
        self.mouse_mm_changed.emit(float("nan"), float("nan"))
        self.update()

    def _draw_simple_field(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#dbeafe"), 2))
        top_left = self.renderer.mm_to_px(0, 0)
        bottom_right = self.renderer.mm_to_px(self.model.width_mm, self.model.height_mm)
        painter.drawRect(QRectF(top_left.x(), top_left.y(), bottom_right.x() - top_left.x(), bottom_right.y() - top_left.y()))
        if self.show_grid:
            self.renderer.draw_grid(painter)

    def _draw_object_edit_hint(self, painter: QPainter) -> None:
        for item in self.model.get_objects():
            selected = item.name == self.selected_object_name
            painter.setPen(QPen(QColor("#f472b6") if selected else QColor("#facc15"), 3 if selected else 2, Qt.PenStyle.DashLine))
            rect = item.rect
            top_left = self.renderer.mm_to_px(rect.left, rect.top)
            painter.drawRect(
                QRectF(
                    top_left.x() - 4,
                    top_left.y() - 4,
                    rect.width_mm * self.renderer.scale_px_per_mm + 8,
                    rect.height_mm * self.renderer.scale_px_per_mm + 8,
                )
            )


class TestFieldWidget(QWidget):
    reset_simulation_requested = Signal()
    r2_position_reset_requested = Signal()
    r2_pose_correction_requested = Signal(float, float, float)
    imu_only_field_requested = Signal()
    imu_only_field_stop_requested = Signal()
    optical_apply_toggled = Signal(bool)
    optical_zero_requested = Signal()
    optical_calibration_requested = Signal(str, float)
    object_layout_saved = Signal(bool, str)

    def __init__(
        self,
        field_width_mm: float = 4500.0,
        field_height_mm: float = 2400.0,
        *,
        field_path: str | None = None,
    ) -> None:
        super().__init__()
        self._field_path = field_path
        self.field_model = FieldModel.load(field_path)
        self.field_width_mm, self.field_height_mm = self.field_model.get_field_size()
        self.r1_start_pose = self._robot_start_pose_inside_line("r1")
        self.r2_start_pose = self._robot_start_pose_inside_line("r2")
        self.r1_pose = self.r1_start_pose
        self.state = OdometryState()
        self.unit = "mm"
        self.current_zone = "-"
        self.nearest_wall_mm: float | None = None
        self.current_scale_text = "自動"
        self.display_mode_text = "公式"
        self.mouse_coord_text = "マウス座標: -"
        self.sensor_statuses = {
            "imu": "未接続",
            "lidar": "未接続",
            "encoder": "未接続",
            "odom": "未接続",
            "distance": "未接続",
            "line": "未接続",
            "color": "未接続",
        }
        self.lidar_values = (0.0, 0.0, 0.0, 0.0)
        self.lidar_active = False
        self.sensor_age_text = ""
        self.objects_dirty = False
        self.selected_object_name = ""
        self.object_counter = len(self.field_model.get_objects())

        self.canvas = TestFieldCanvas(self.field_model)
        self.canvas.set_r1_pose(self.r1_pose)

        self.field_info_label = QLabel("")
        self.robot_position_label = QLabel("")
        self.r2_motion_label = QLabel("")
        self.sensor_status_label = QLabel("")
        self.lidar_detail_label = QLabel("")
        self.optical_detail_label = QLabel("")
        self.optical_calibration_label = QLabel("")
        self.display_status_label = QLabel("")
        self.object_status_label = QLabel("")
        self.mouse_label = QLabel(self.mouse_coord_text)
        self.warning_label = QLabel("")

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["公式フィールド表示", "簡易フィールド表示"])
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(list(SCALE_OPTIONS.keys()))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["mm", "cm", "m"])
        self.object_type_combo = QComboBox()
        for kind, template in OBJECT_TEMPLATES.items():
            self.object_type_combo.addItem(str(template["label"]), kind)
        self.object_select_combo = QComboBox()
        self.move_step_combo = QComboBox()
        for step in (10, 50, 100, 500):
            self.move_step_combo.addItem(f"{step} mm", step)
        self.move_step_combo.setCurrentIndex(2)
        self.object_x_spin = QSpinBox()
        self.object_x_spin.setRange(0, int(self.field_model.width_mm))
        self.object_x_spin.setSuffix(" mm")
        self.object_x_spin.setSingleStep(10)
        self.object_y_spin = QSpinBox()
        self.object_y_spin.setRange(0, int(self.field_model.height_mm))
        self.object_y_spin.setSuffix(" mm")
        self.object_y_spin.setSingleStep(10)
        self.object_orientation_spin = QSpinBox()
        self.object_orientation_spin.setRange(-180, 179)
        self.object_orientation_spin.setSuffix(" deg")
        self.object_orientation_spin.setSingleStep(5)
        self.object_bottom_combo = QComboBox()
        for label, value in [
            ("未設定 / NOT CONFIGURED", "NOT_CONFIGURED"),
            ("下面 / BOTTOM", "BOTTOM"),
            ("上面 / TOP", "TOP"),
            ("前面 / FRONT", "FRONT"),
            ("後面 / REAR", "REAR"),
            ("左面 / LEFT", "LEFT"),
            ("右面 / RIGHT", "RIGHT"),
        ]:
            self.object_bottom_combo.addItem(label, value)
        self.r2_x_spin = QSpinBox()
        self.r2_x_spin.setRange(0, int(self.field_model.width_mm))
        self.r2_x_spin.setSuffix(" mm")
        self.r2_x_spin.setSingleStep(10)
        self.r2_y_spin = QSpinBox()
        self.r2_y_spin.setRange(0, int(self.field_model.height_mm))
        self.r2_y_spin.setSuffix(" mm")
        self.r2_y_spin.setSingleStep(10)
        self.r2_theta_spin = QSpinBox()
        self.r2_theta_spin.setRange(0, 359)
        self.r2_theta_spin.setSuffix(" deg")
        self.r2_theta_spin.setSingleStep(5)
        self.optical_calibration_distance_spin = QDoubleSpinBox()
        self.optical_calibration_distance_spin.setRange(1.0, 5000.0)
        self.optical_calibration_distance_spin.setValue(500.0)
        self.optical_calibration_distance_spin.setSuffix(" mm")
        self.optical_calibration_distance_spin.setSingleStep(10.0)

        self.r1_check = QCheckBox("R1表示")
        self.r2_check = QCheckBox("R2表示")
        self.coordinate_check = QCheckBox("座標ラベル")
        self.dimension_check = QCheckBox("寸法表示")
        self.sensor_check = QCheckBox("センサ状態表示")
        self.grid_check = QCheckBox("グリッド")
        self.zone_check = QCheckBox("ゾーン名")
        self.wall_check = QCheckBox("壁/木枠")
        self.line_check = QCheckBox("ライン")
        self.trail_check = QCheckBox("軌跡")
        self.lidar_check = QCheckBox("LiDARレイ")
        self.mouse_check = QCheckBox("マウス座標")
        self.object_check = QCheckBox("オブジェクト表示")
        self.object_edit_check = QCheckBox("オブジェクト編集モード")
        self.optical_apply_check = QCheckBox("光学式位置反映")
        self.optical_apply_check.setChecked(True)
        self.object_help_label = QLabel("編集モードONで、空き場所クリックで追加、オブジェクトをドラッグで移動できます。")
        self.object_help_label.setWordWrap(True)
        for check in [
            self.r1_check,
            self.r2_check,
            self.coordinate_check,
            self.dimension_check,
            self.sensor_check,
            self.grid_check,
            self.zone_check,
            self.wall_check,
            self.line_check,
            self.trail_check,
            self.mouse_check,
            self.object_check,
        ]:
            check.setChecked(True)
        self.lidar_check.setChecked(False)
        self.object_edit_check.setChecked(False)

        self._build_layout()
        self._connect()
        self.reset_all(emit_signal=False)

    def _build_layout(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(self.canvas, 5)

        side = QWidget()
        side.setMinimumWidth(390)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)
        self.dimension_box = self._dimension_box()
        self.sensor_box = self._sensor_box()
        side_layout.addWidget(self.dimension_box)
        side_layout.addWidget(self._robot_box())
        side_layout.addWidget(self._pose_correction_box())
        side_layout.addWidget(self._motion_box())
        side_layout.addWidget(self._optical_box())
        side_layout.addWidget(self.sensor_box)
        side_layout.addWidget(self._display_box())
        side_layout.addWidget(self._object_box())
        side_layout.addWidget(self._reset_box())
        side_layout.addStretch(1)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setMinimumWidth(420)
        side_scroll.setWidget(side)
        root.addWidget(side_scroll, 2)

    def _dimension_box(self) -> QGroupBox:
        box = QGroupBox("フィールド寸法")
        layout = QVBoxLayout(box)
        self.field_info_label.setWordWrap(True)
        layout.addWidget(self.field_info_label)
        return box

    def _robot_box(self) -> QGroupBox:
        box = QGroupBox("R1/R2位置")
        layout = QVBoxLayout(box)
        self.robot_position_label.setWordWrap(True)
        self.mouse_label.setWordWrap(True)
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.robot_position_label)
        layout.addWidget(self.mouse_label)
        layout.addWidget(self.warning_label)
        return box

    def _pose_correction_box(self) -> QGroupBox:
        box = QGroupBox("R2位置補正")
        layout = QGridLayout(box)
        layout.addWidget(QLabel("X"), 0, 0)
        layout.addWidget(self.r2_x_spin, 0, 1)
        layout.addWidget(QLabel("Y"), 1, 0)
        layout.addWidget(self.r2_y_spin, 1, 1)
        layout.addWidget(QLabel("θ"), 2, 0)
        layout.addWidget(self.r2_theta_spin, 2, 1)
        apply_button = QPushButton("入力位置を反映")
        mouse_button = QPushButton("マウス位置へ反映")
        imu_only_button = QPushButton("IMU慣性推定開始")
        imu_stop_button = QPushButton("IMU慣性推定停止")
        reset_position_button = QPushButton("位置リセット")
        apply_button.clicked.connect(self.apply_r2_pose_correction)
        mouse_button.clicked.connect(self.apply_r2_pose_at_mouse)
        imu_only_button.clicked.connect(self.imu_only_field_requested.emit)
        imu_stop_button.clicked.connect(self.imu_only_field_stop_requested.emit)
        reset_position_button.clicked.connect(self.request_r2_position_reset)
        layout.addWidget(apply_button, 3, 0, 1, 2)
        layout.addWidget(mouse_button, 4, 0, 1, 2)
        layout.addWidget(imu_only_button, 5, 0, 1, 2)
        layout.addWidget(imu_stop_button, 6, 0, 1, 2)
        layout.addWidget(reset_position_button, 7, 0, 1, 2)
        return box

    def _motion_box(self) -> QGroupBox:
        box = QGroupBox("R2移動量")
        layout = QVBoxLayout(box)
        self.r2_motion_label.setWordWrap(True)
        layout.addWidget(self.r2_motion_label)
        return box

    def _sensor_box(self) -> QGroupBox:
        box = QGroupBox("センサ状態")
        layout = QVBoxLayout(box)
        self.sensor_status_label.setWordWrap(True)
        self.lidar_detail_label.setWordWrap(True)
        layout.addWidget(self.sensor_status_label)
        layout.addWidget(self.lidar_detail_label)
        return box

    def _optical_box(self) -> QGroupBox:
        box = QGroupBox("光学式反映")
        layout = QVBoxLayout(box)
        self.optical_detail_label.setWordWrap(True)
        layout.addWidget(self.optical_detail_label)
        layout.addWidget(self.optical_apply_check)
        reset_position_button = QPushButton("位置リセット")
        reset_position_button.clicked.connect(self.request_r2_position_reset)
        layout.addWidget(reset_position_button)
        zero_button = QPushButton("光学式ゼロ点設定")
        zero_button.clicked.connect(self.optical_zero_requested.emit)
        layout.addWidget(zero_button)
        self.optical_calibration_label.setWordWrap(True)
        self.optical_calibration_label.setText(
            "キャリブレーション: ゼロ点設定後、センサを実際に動かした距離を入力してscaleを保存します。"
        )
        layout.addWidget(self.optical_calibration_label)
        calibration_row = QHBoxLayout()
        calibration_row.addWidget(QLabel("実測距離"))
        calibration_row.addWidget(self.optical_calibration_distance_spin)
        layout.addLayout(calibration_row)
        x_button = QPushButton("X scale保存")
        y_button = QPushButton("Y scale保存")
        x_button.clicked.connect(lambda: self.optical_calibration_requested.emit("x", self.optical_calibration_distance_spin.value()))
        y_button.clicked.connect(lambda: self.optical_calibration_requested.emit("y", self.optical_calibration_distance_spin.value()))
        button_row = QHBoxLayout()
        button_row.addWidget(x_button)
        button_row.addWidget(y_button)
        layout.addLayout(button_row)
        return box

    def _display_box(self) -> QGroupBox:
        box = QGroupBox("表示設定")
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("表示モード"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(QLabel("表示倍率"))
        layout.addWidget(self.scale_combo)
        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("表示単位"))
        unit_row.addWidget(self.unit_combo)
        layout.addLayout(unit_row)

        checks = QGridLayout()
        check_list = [
            self.r1_check,
            self.r2_check,
            self.coordinate_check,
            self.dimension_check,
            self.sensor_check,
            self.grid_check,
            self.zone_check,
            self.wall_check,
            self.line_check,
            self.trail_check,
            self.lidar_check,
            self.mouse_check,
        ]
        for index, check in enumerate(check_list):
            checks.addWidget(check, index // 2, index % 2)
        layout.addLayout(checks)
        self.display_status_label.setWordWrap(True)
        layout.addWidget(self.display_status_label)
        return box

    def _object_box(self) -> QGroupBox:
        box = QGroupBox("オブジェクト編集")
        layout = QVBoxLayout(box)
        layout.addWidget(self.object_check)
        layout.addWidget(self.object_edit_check)
        layout.addWidget(self.object_help_label)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("選択中"))
        select_row.addWidget(self.object_select_combo, 1)
        layout.addLayout(select_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("追加する物"))
        type_row.addWidget(self.object_type_combo, 1)
        layout.addLayout(type_row)

        add_row = QHBoxLayout()
        add_button = QPushButton("マウス位置に追加")
        center_button = QPushButton("中央に追加")
        duplicate_button = QPushButton("選択を複製")
        delete_button = QPushButton("選択削除")
        add_button.clicked.connect(self.add_object_at_mouse)
        center_button.clicked.connect(self.add_object_at_center)
        duplicate_button.clicked.connect(self.duplicate_selected_object)
        delete_button.clicked.connect(self.delete_selected_object)
        add_row.addWidget(add_button)
        add_row.addWidget(center_button)
        layout.addLayout(add_row)

        edit_row = QHBoxLayout()
        edit_row.addWidget(duplicate_button)
        edit_row.addWidget(delete_button)
        layout.addLayout(edit_row)

        coord_grid = QGridLayout()
        coord_grid.addWidget(QLabel("X"), 0, 0)
        coord_grid.addWidget(self.object_x_spin, 0, 1)
        coord_grid.addWidget(QLabel("Y"), 1, 0)
        coord_grid.addWidget(self.object_y_spin, 1, 1)
        coord_grid.addWidget(QLabel("向き"), 2, 0)
        coord_grid.addWidget(self.object_orientation_spin, 2, 1)
        coord_grid.addWidget(QLabel("下面"), 3, 0)
        coord_grid.addWidget(self.object_bottom_combo, 3, 1)
        apply_button = QPushButton("座標・向き・下面を反映")
        apply_button.clicked.connect(self.apply_selected_object_pose)
        coord_grid.addWidget(apply_button, 0, 2, 4, 1)
        layout.addLayout(coord_grid)

        persistence_row = QHBoxLayout()
        save_button = QPushButton("配置をYAMLへ保存")
        reload_button = QPushButton("保存済み配置を再読込")
        save_button.clicked.connect(self.save_object_layout)
        reload_button.clicked.connect(self.reload_object_layout)
        persistence_row.addWidget(save_button)
        persistence_row.addWidget(reload_button)
        layout.addLayout(persistence_row)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("移動量"))
        step_row.addWidget(self.move_step_combo, 1)
        layout.addLayout(step_row)

        move_grid = QGridLayout()
        move_buttons = [
            ("上へ", lambda: self.nudge_selected_object(0.0, -self._move_step_mm()), 0, 1),
            ("左へ", lambda: self.nudge_selected_object(-self._move_step_mm(), 0.0), 1, 0),
            ("右へ", lambda: self.nudge_selected_object(self._move_step_mm(), 0.0), 1, 2),
            ("下へ", lambda: self.nudge_selected_object(0.0, self._move_step_mm()), 2, 1),
        ]
        for text, slot, row, col in move_buttons:
            button = QPushButton(text)
            button.clicked.connect(slot)
            move_grid.addWidget(button, row, col)
        layout.addLayout(move_grid)
        self.object_status_label.setWordWrap(True)
        layout.addWidget(self.object_status_label)
        return box

    def _reset_box(self) -> QGroupBox:
        box = QGroupBox("リセット")
        layout = QGridLayout(box)
        buttons = [
            ("R2位置リセット", lambda: self.reset_r2_to_start(emit_signal=True)),
            ("軌跡リセット", self.clear_trail),
            ("オブジェクト配置リセット", self.reset_objects),
            ("全体リセット", lambda: self.reset_all(emit_signal=True)),
        ]
        for index, (text, slot) in enumerate(buttons):
            button = QPushButton(text)
            button.setMinimumHeight(36)
            button.clicked.connect(slot)
            layout.addWidget(button, index // 2, index % 2)
        return box

    def _connect(self) -> None:
        self.unit_combo.currentTextChanged.connect(self.set_unit)
        self.mode_combo.currentTextChanged.connect(self._apply_display_options)
        self.scale_combo.currentTextChanged.connect(self.set_scale_option)
        self.object_type_combo.currentTextChanged.connect(lambda _text: self._refresh_labels())
        self.move_step_combo.currentTextChanged.connect(lambda _text: self._refresh_labels())
        self.object_select_combo.currentIndexChanged.connect(self._select_object_from_combo)
        for check in [
            self.r1_check,
            self.r2_check,
            self.coordinate_check,
            self.dimension_check,
            self.sensor_check,
            self.grid_check,
            self.zone_check,
            self.wall_check,
            self.line_check,
            self.trail_check,
            self.lidar_check,
            self.mouse_check,
            self.object_check,
            self.object_edit_check,
        ]:
            check.toggled.connect(self._apply_display_options)
        self.canvas.mouse_mm_changed.connect(self._update_mouse_coord)
        self.canvas.field_clicked.connect(self._handle_field_click)
        self.canvas.object_selected.connect(self.select_object)
        self.canvas.object_dragged.connect(self.move_object_to)
        self.optical_apply_check.toggled.connect(self.optical_apply_toggled.emit)

    def update_from_pose(
        self,
        source: str,
        x_mm: float | None,
        y_mm: float | None,
        theta_deg: float | None,
        has_data: bool = True,
        source_note: str = "",
    ) -> None:
        if not has_data or x_mm is None or y_mm is None or theta_deg is None:
            self._set_r2_pose(*self.r2_start_pose, "未接続", source_note or "R2スタート位置を表示しています。", append_trail=False, reset_distance=True)
            return

        if source in {"ダミー", "Mock"}:
            self._set_r2_pose(*self.r2_start_pose, "DUMMY", "DUMMYの姿勢値は実フィールド位置として扱わず、R2スタート位置を表示します。", append_trail=False, reset_distance=True)
            return

        self._set_r2_pose(float(x_mm), float(y_mm), float(theta_deg), source, source_note, append_trail=True)

    def update_sensor_status(self, data, source: str = "Mock", show_values: bool = True) -> None:
        if not show_values:
            statuses = {key: "未接続" for key in self.sensor_statuses}
            lidar_values = (0.0, 0.0, 0.0, 0.0)
        else:
            statuses = {
                "imu": status_label(getattr(data, "imu_status", "未接続")),
                "lidar": status_label(getattr(data, "lidar_status", "未接続")),
                "encoder": status_label(getattr(data, "encoder_status", "未接続")),
                "odom": status_label(getattr(data, "odom_status", "未接続")),
                "distance": status_label(getattr(data, "distance_status", "未接続")),
                "line": status_label(getattr(data, "line_status", "未接続")),
                "color": status_label(getattr(data, "color_status", "未接続")),
            }
            if is_sensor_active(getattr(data, "lidar_status", "未接続")):
                lidar_values = (
                    self._sanitize_distance(getattr(data, "lidar_front_mm", 0.0)),
                    self._sanitize_distance(getattr(data, "lidar_left_mm", 0.0)),
                    self._sanitize_distance(getattr(data, "lidar_right_mm", 0.0)),
                    self._sanitize_distance(getattr(data, "lidar_rear_mm", 0.0)),
                )
            else:
                lidar_values = (0.0, 0.0, 0.0, 0.0)

        self.sensor_statuses = statuses
        self.lidar_values = lidar_values
        self.sensor_age_text = getattr(data, "sensor_age_text", "") if show_values else ""
        self.lidar_active = statuses["lidar"] == "OK"
        self.canvas.set_display_options(lidar_active=self.lidar_active)
        self._refresh_labels()

    def update_optical_odometry_status(self, summary: dict) -> None:
        status = str(summary.get("status", "未接続"))
        source = str(summary.get("source", "NONE"))
        raw_dx = float(summary.get("raw_dx", 0.0) or 0.0)
        raw_dy = float(summary.get("raw_dy", 0.0) or 0.0)
        delta_x = float(summary.get("delta_x_mm", 0.0) or 0.0)
        delta_y = float(summary.get("delta_y_mm", 0.0) or 0.0)
        total_x = float(summary.get("total_x_mm", 0.0) or 0.0)
        total_y = float(summary.get("total_y_mm", 0.0) or 0.0)
        total_x_count = float(summary.get("total_x_count", 0.0) or 0.0)
        total_y_count = float(summary.get("total_y_count", 0.0) or 0.0)
        applying = bool(summary.get("applying", False))
        reason = str(summary.get("last_reject_reason", ""))
        state_text = "反映中" if applying else f"停止中{(' / ' + reason) if reason else ''}"
        self.optical_detail_label.setText(
            "光学式オドメトリ\n"
            f"状態: {status} / 入力: {source}\n"
            f"raw dx {raw_dx:.0f} / raw dy {raw_dy:.0f}\n"
            f"ΔX {delta_x:.1f} mm / ΔY {delta_y:.1f} mm\n"
            f"累積count X {total_x_count:.0f} / Y {total_y_count:.0f}\n"
            f"累積X {total_x:.1f} mm / 累積Y {total_y:.1f} mm\n"
            f"R2位置反映: {state_text}"
        )

    def reset_r1_to_start(self) -> None:
        self.r1_pose = self.r1_start_pose
        self.canvas.set_r1_pose(self.r1_pose)
        self._refresh_labels()

    def reset_r2_to_start(self, emit_signal: bool = False) -> None:
        self._set_r2_pose(*self.r2_start_pose, "初期位置", "R2をR2スタートゾーンへ戻しました。", append_trail=False, reset_distance=True)
        self.canvas.clear_trail()
        if emit_signal:
            self.reset_simulation_requested.emit()

    def request_r2_position_reset(self) -> None:
        self._set_r2_pose(*self.r2_start_pose, "位置リセット", "R2をR2スタートゾーンへ戻しました。", append_trail=False, reset_distance=True)
        self.canvas.clear_trail()
        self.r2_position_reset_requested.emit()

    def clear_trail(self) -> None:
        self.canvas.clear_trail()
        self._refresh_labels()

    def reset_objects(self) -> None:
        self.field_model.reset_objects()
        self.objects_dirty = False
        self.selected_object_name = ""
        self.object_counter = len(self.field_model.get_objects())
        self.canvas.set_selected_object("")
        self.canvas.update()
        self._refresh_labels()

    def add_object_at_mouse(self) -> None:
        if self.canvas.mouse_mm is None:
            self.warning_label.setText("フィールド上にマウスを置いてから追加してください。")
            return
        self.add_object_at(self.canvas.mouse_mm[0], self.canvas.mouse_mm[1])

    def add_object_at_center(self) -> None:
        self.add_object_at(self.field_model.width_mm / 2.0, self.field_model.height_mm / 2.0)

    def add_object_at(self, center_x_mm: float, center_y_mm: float) -> None:
        template = self._current_object_template()
        width = float(template["width_mm"])
        height = float(template["height_mm"])
        x_mm, y_mm = self._clamp_object_position(center_x_mm - width / 2.0, center_y_mm - height / 2.0, width, height)
        self.object_counter += 1
        kind = str(self.object_type_combo.currentData() or "generic")
        item = FieldObject(
            name=f"{kind}_{self.object_counter}",
            label_ja=str(template["label"]),
            rect=FieldRect(x_mm, y_mm, width, height),
            color=str(template["color"]),
            kind=kind,
            source_note="テストフィールド編集モードで追加",
            orientation_deg=0.0,
            bottom_face="NOT_CONFIGURED",
        )
        self.field_model.add_object(item)
        self.select_object(item.name)
        self.objects_dirty = True
        self.object_check.setChecked(True)
        self.canvas.update()
        self._refresh_labels()

    def duplicate_selected_object(self) -> None:
        item = self._selected_object()
        if item is None:
            self.warning_label.setText("複製するオブジェクトを選択してください。")
            return
        offset = max(80.0, min(180.0, item.rect.width_mm))
        x_mm, y_mm = self._clamp_object_position(
            item.rect.x_mm + offset,
            item.rect.y_mm + offset,
            item.rect.width_mm,
            item.rect.height_mm,
        )
        self.object_counter += 1
        copied = FieldObject(
            name=f"{item.kind}_{self.object_counter}",
            label_ja=item.label_ja,
            rect=FieldRect(x_mm, y_mm, item.rect.width_mm, item.rect.height_mm),
            color=item.color,
            kind=item.kind,
            source_note="テストフィールド編集モードで複製",
            orientation_deg=item.orientation_deg,
            bottom_face=item.bottom_face,
        )
        self.field_model.add_object(copied)
        self.select_object(copied.name)
        self.objects_dirty = True
        self.object_check.setChecked(True)
        self.canvas.update()
        self._refresh_labels()

    def delete_selected_object(self) -> None:
        if not self.selected_object_name:
            self.warning_label.setText("削除するオブジェクトを選択してください。")
            return
        if self.field_model.remove_object(self.selected_object_name):
            self.selected_object_name = ""
            self.canvas.set_selected_object("")
            self.objects_dirty = True
            self.canvas.update()
            self._refresh_labels()

    def nudge_selected_object(self, dx_mm: float, dy_mm: float) -> None:
        item = self._selected_object()
        if item is None:
            self.warning_label.setText("移動するオブジェクトを選択してください。")
            return
        x_mm, y_mm = self._clamp_object_position(item.rect.x_mm + dx_mm, item.rect.y_mm + dy_mm, item.rect.width_mm, item.rect.height_mm)
        self.move_object_to(item.name, x_mm, y_mm)

    def apply_selected_object_position(self) -> None:
        self.apply_selected_object_pose()

    def apply_selected_object_pose(self) -> None:
        item = self._selected_object()
        if item is None:
            self.warning_label.setText("座標・向き・下面を反映するオブジェクトを選択してください。")
            return
        x_mm, y_mm = self._clamp_object_position(
            float(self.object_x_spin.value()),
            float(self.object_y_spin.value()),
            item.rect.width_mm,
            item.rect.height_mm,
        )
        if self.field_model.update_object_pose(
            item.name,
            x_mm=x_mm,
            y_mm=y_mm,
            orientation_deg=float(self.object_orientation_spin.value()),
            bottom_face=str(self.object_bottom_combo.currentData() or "NOT_CONFIGURED"),
        ):
            self.objects_dirty = True
            self.object_check.setChecked(True)
            self.canvas.update()
            self._refresh_labels()

    def save_object_layout(self) -> None:
        try:
            path = self.field_model.save_objects(self._field_path)
        except (OSError, ValueError, TypeError) as exc:
            message = f"配置保存失敗: {exc}"
            self.warning_label.setText(message)
            self.object_layout_saved.emit(False, message)
            return
        self.objects_dirty = False
        message = f"配置保存済み: {path}"
        self.warning_label.setText(message)
        self.object_layout_saved.emit(True, message)
        self._refresh_labels()

    def reload_object_layout(self) -> None:
        try:
            loaded = FieldModel.load(self._field_path)
        except (OSError, ValueError, TypeError) as exc:
            message = f"配置再読込失敗: {exc}"
            self.warning_label.setText(message)
            self.object_layout_saved.emit(False, message)
            return
        self.field_model.objects = loaded.get_objects()
        self.field_model._default_objects = list(loaded.get_objects())
        self.field_model.source_path = loaded.source_path
        self.object_counter = len(self.field_model.get_objects())
        self.objects_dirty = False
        self.selected_object_name = ""
        self.canvas.set_selected_object("")
        self.canvas.update()
        self.warning_label.setText("保存済み配置を再読込しました。")
        self._refresh_labels()

    def move_object_to(self, object_name: str, x_mm: float, y_mm: float) -> None:
        item = next((obj for obj in self.field_model.get_objects() if obj.name == object_name), None)
        if item is None:
            return
        x_mm, y_mm = self._clamp_object_position(x_mm, y_mm, item.rect.width_mm, item.rect.height_mm)
        if self.selected_object_name != object_name:
            self.selected_object_name = object_name
            self.canvas.set_selected_object(object_name)
        if self.field_model.move_object(object_name, x_mm, y_mm):
            self.objects_dirty = True
            self.object_check.setChecked(True)
            self.canvas.update()
            self._refresh_labels()

    def select_object(self, object_name: str) -> None:
        self.selected_object_name = object_name
        self.canvas.set_selected_object(object_name)
        self._refresh_labels()

    def _select_object_from_combo(self) -> None:
        object_name = str(self.object_select_combo.currentData() or "")
        if object_name == self.selected_object_name:
            return
        self.selected_object_name = object_name
        self.canvas.set_selected_object(object_name)
        self.canvas.update()
        self._refresh_labels()

    def _handle_field_click(self, x_mm: float, y_mm: float) -> None:
        if not self.object_edit_check.isChecked():
            return
        if not self.field_model.is_inside_field(x_mm, y_mm):
            self.warning_label.setText("フィールド外には配置できません。")
            return
        item = self.field_model.get_object_at(x_mm, y_mm)
        if item is not None:
            self.select_object(item.name)
            return
        self.add_object_at(x_mm, y_mm)

    def apply_r2_pose_correction(self) -> None:
        self.r2_pose_correction_requested.emit(
            float(self.r2_x_spin.value()),
            float(self.r2_y_spin.value()),
            float(self.r2_theta_spin.value()),
        )

    def apply_r2_pose_at_mouse(self) -> None:
        if self.canvas.mouse_mm is None:
            self.warning_label.setText("フィールド上にマウスを置いてから反映してください。")
            return
        x_mm, y_mm = self.canvas.mouse_mm
        if not self.field_model.is_inside_field(x_mm, y_mm):
            self.warning_label.setText("フィールド外の位置は反映できません。")
            return
        self.r2_x_spin.setValue(int(round(x_mm)))
        self.r2_y_spin.setValue(int(round(y_mm)))
        self.apply_r2_pose_correction()

    def _selected_object(self) -> FieldObject | None:
        for item in self.field_model.get_objects():
            if item.name == self.selected_object_name:
                return item
        return None

    def _current_object_template(self) -> dict[str, object]:
        kind = str(self.object_type_combo.currentData() or "generic")
        return OBJECT_TEMPLATES.get(kind, OBJECT_TEMPLATES["generic"])

    def _move_step_mm(self) -> float:
        return float(self.move_step_combo.currentData() or 100)

    def _refresh_object_combo(self, selected: FieldObject | None = None) -> None:
        current_name = selected.name if selected is not None else self.selected_object_name
        self.object_select_combo.blockSignals(True)
        self.object_select_combo.clear()
        self.object_select_combo.addItem("なし", "")
        selected_index = 0
        for index, item in enumerate(self.field_model.get_objects(), start=1):
            self.object_select_combo.addItem(f"{item.label_ja} / X {item.rect.x_mm:.0f} / Y {item.rect.y_mm:.0f}", item.name)
            if item.name == current_name:
                selected_index = index
        self.object_select_combo.setCurrentIndex(selected_index)
        self.object_select_combo.blockSignals(False)
        self._sync_object_controls(selected)

    def _sync_object_controls(self, selected: FieldObject | None = None) -> None:
        item = selected if selected is not None else self._selected_object()
        enabled = item is not None
        self.object_x_spin.setEnabled(enabled)
        self.object_y_spin.setEnabled(enabled)
        self.object_orientation_spin.setEnabled(enabled)
        self.object_bottom_combo.setEnabled(enabled)
        if item is None:
            self.object_x_spin.setValue(0)
            self.object_y_spin.setValue(0)
            self.object_orientation_spin.setValue(0)
            self.object_bottom_combo.setCurrentIndex(0)
            return
        self.object_x_spin.blockSignals(True)
        self.object_y_spin.blockSignals(True)
        self.object_orientation_spin.blockSignals(True)
        self.object_bottom_combo.blockSignals(True)
        self.object_x_spin.setValue(int(round(item.rect.x_mm)))
        self.object_y_spin.setValue(int(round(item.rect.y_mm)))
        self.object_orientation_spin.setValue(int(round(item.orientation_deg)))
        face_index = self.object_bottom_combo.findData(item.bottom_face)
        self.object_bottom_combo.setCurrentIndex(max(0, face_index))
        self.object_x_spin.blockSignals(False)
        self.object_y_spin.blockSignals(False)
        self.object_orientation_spin.blockSignals(False)
        self.object_bottom_combo.blockSignals(False)

    def _clamp_object_position(self, x_mm: float, y_mm: float, width_mm: float, height_mm: float) -> tuple[float, float]:
        return (
            max(0.0, min(self.field_model.width_mm - width_mm, float(x_mm))),
            max(0.0, min(self.field_model.height_mm - height_mm, float(y_mm))),
        )

    def reset_all(self, emit_signal: bool = False) -> None:
        self.reset_r1_to_start()
        self._set_r2_pose(*self.r2_start_pose, "初期位置", "全体リセットを実行しました。", append_trail=False, reset_distance=True)
        self.canvas.clear_trail()
        self.reset_objects()
        self.sensor_statuses = {key: "未接続" for key in self.sensor_statuses}
        self.lidar_values = (0.0, 0.0, 0.0, 0.0)
        self.lidar_active = False
        self.canvas.set_display_options(lidar_active=False)
        if emit_signal:
            self.reset_simulation_requested.emit()
        self._refresh_labels()

    def set_start_to_current(self) -> None:
        if not self.state.has_data:
            return
        self.state.start_x_mm = self.state.x_mm
        self.state.start_y_mm = self.state.y_mm
        self.state.total_distance_mm = 0.0
        self.state.last_x_mm = self.state.x_mm
        self.state.last_y_mm = self.state.y_mm
        self.canvas.clear_trail()
        self._refresh_labels()

    def set_scale_option(self, text: str) -> None:
        self.current_scale_text = text
        value = SCALE_OPTIONS.get(text)
        if value is None:
            self.canvas.set_scale("auto")
        else:
            self.canvas.set_scale("manual", value)
        self._refresh_labels()

    def set_unit(self, unit: str) -> None:
        self.unit = unit
        self._refresh_labels()

    def summary_text(self) -> str:
        return (
            "テストフィールド\n"
            "フィールドモデル: F3RC2026公式寸法\n"
            "座標系: mm / 左上原点\n"
            f"表示モード: {self.display_mode_text}\n"
            f"R2現在位置: X {self.state.x_mm:.0f} mm / Y {self.state.y_mm:.0f} mm / θ {self.state.theta_deg:.1f} deg\n"
            f"現在ゾーン: {self.current_zone}\n"
            f"最近傍壁までの距離: {(self.nearest_wall_mm or 0.0):.0f} mm\n"
            f"累積移動距離: {self.state.total_distance_mm:.0f} mm\n"
            f"LiDAR: {self.sensor_statuses['lidar']}"
        )

    def _set_r2_pose(
        self,
        x_mm: float,
        y_mm: float,
        theta_deg: float,
        source: str,
        warning: str = "",
        append_trail: bool = True,
        reset_distance: bool = False,
    ) -> None:
        now = time.time()
        if not self.state.has_data or reset_distance:
            total_distance = 0.0
            start_x = self.r2_start_pose[0]
            start_y = self.r2_start_pose[1]
        else:
            step_mm = math.hypot(x_mm - self.state.last_x_mm, y_mm - self.state.last_y_mm)
            total_distance = self.state.total_distance_mm + step_mm
            start_x = self.state.start_x_mm
            start_y = self.state.start_y_mm

        self.state = OdometryState(
            source=source,
            x_mm=x_mm,
            y_mm=y_mm,
            theta_deg=theta_deg,
            total_distance_mm=total_distance,
            start_x_mm=start_x,
            start_y_mm=start_y,
            last_x_mm=x_mm,
            last_y_mm=y_mm,
            updated_at=now,
            has_data=True,
            warning=warning,
        )
        self.current_zone = self.field_model.get_zone_at(x_mm, y_mm)
        self.nearest_wall_mm = self.field_model.distance_to_nearest_wall(x_mm, y_mm)
        self.canvas.update_state(self.state, append_trail=append_trail)
        self._refresh_labels()

    def _apply_display_options(self) -> None:
        self.display_mode_text = "公式" if self.mode_combo.currentText().startswith("公式") else "簡易"
        self.dimension_box.setVisible(self.dimension_check.isChecked())
        self.sensor_box.setVisible(self.sensor_check.isChecked())
        self.canvas.set_display_options(
            display_mode="official" if self.display_mode_text == "公式" else "simple",
            show_grid=self.grid_check.isChecked(),
            show_zone_labels=self.zone_check.isChecked(),
            show_walls=self.wall_check.isChecked(),
            show_lines=self.line_check.isChecked(),
            show_trail=self.trail_check.isChecked(),
            show_lidar=self.lidar_check.isChecked(),
            lidar_active=self.lidar_active,
            show_mouse_coordinate=self.mouse_check.isChecked(),
            show_r1=self.r1_check.isChecked(),
            show_r2=self.r2_check.isChecked(),
            show_coordinate_label=self.coordinate_check.isChecked(),
            show_dimensions=self.dimension_check.isChecked(),
            show_objects=self.object_check.isChecked(),
            object_edit_mode=self.object_edit_check.isChecked(),
        )
        self._refresh_labels()

    def _update_mouse_coord(self, x_mm: float, y_mm: float) -> None:
        if math.isnan(x_mm) or math.isnan(y_mm):
            self.mouse_coord_text = "マウス座標: -"
        else:
            inside = "フィールド内" if self.field_model.is_inside_field(x_mm, y_mm) else "フィールド外"
            self.mouse_coord_text = f"マウス座標: X {x_mm:.0f} mm / Y {y_mm:.0f} mm / {inside}"
        self.mouse_label.setText(self.mouse_coord_text)

    def _refresh_labels(self) -> None:
        self.r2_x_spin.blockSignals(True)
        self.r2_y_spin.blockSignals(True)
        self.r2_theta_spin.blockSignals(True)
        self.r2_x_spin.setValue(int(round(max(0.0, min(self.field_model.width_mm, self.state.x_mm)))))
        self.r2_y_spin.setValue(int(round(max(0.0, min(self.field_model.height_mm, self.state.y_mm)))))
        self.r2_theta_spin.setValue(int(round(self.state.theta_deg)) % 360)
        self.r2_x_spin.blockSignals(False)
        self.r2_y_spin.blockSignals(False)
        self.r2_theta_spin.blockSignals(False)
        dx_start = self.state.x_mm - self.state.start_x_mm
        dy_start = self.state.y_mm - self.state.start_y_mm
        distance_from_start = math.hypot(dx_start, dy_start)
        r1_zone = self.field_model.get_zone_at(self.r1_pose[0], self.r1_pose[1])
        r2_zone = self.current_zone
        self.field_info_label.setText(
            "フィールド: 4500 x 2400 mm\n"
            "木材: 38 x 89 mm\n"
            "通常ライン幅: 19 mm\n"
            "橙ライン幅: 38 mm\n"
            "寸法公差: ±5%\n"
            "座標系: 左上原点 / X右方向 / Y下方向\n"
            "寸法は公式図面をもとにした表示です。実フィールドでは誤差が出る可能性があります。"
        )
        self.robot_position_label.setText(
            f"R1: X {self.r1_pose[0]:.0f} mm / Y {self.r1_pose[1]:.0f} mm / θ {self.r1_pose[2]:.0f} deg\n"
            f"R1現在ゾーン: {r1_zone}\n"
            f"R2: X {self.state.x_mm:.0f} mm / Y {self.state.y_mm:.0f} mm / θ {self.state.theta_deg:.1f} deg\n"
            f"R2現在ゾーン: {r2_zone}\n"
            f"最近傍壁までの距離: {(self.nearest_wall_mm or 0.0):.0f} mm"
        )
        self.r2_motion_label.setText(
            f"スタートからの距離: {self._format_main(distance_from_start)}\n"
            f"累積移動距離: {self._format_main(self.state.total_distance_mm)}\n"
            f"X方向移動量: {dx_start:.0f} mm\n"
            f"Y方向移動量: {dy_start:.0f} mm"
        )
        self.sensor_status_label.setText(
            f"IMU: {self.sensor_statuses['imu']} / LiDAR: {self.sensor_statuses['lidar']}\n"
            f"エンコーダ: {self.sensor_statuses['encoder']} / 光学式オドメトリ: {self.sensor_statuses['odom']}\n"
            f"距離センサ: {self.sensor_statuses['distance']} / ライン/カラー: {self.sensor_statuses['line']}/{self.sensor_statuses['color']}"
        )
        if self.sensor_age_text:
            self.sensor_status_label.setText(self.sensor_status_label.text() + "\n受信信頼度: " + self.sensor_age_text)
        self.lidar_detail_label.setText(
            f"LiDAR: {self.sensor_statuses['lidar']}\n"
            f"前: {self.lidar_values[0]:.0f} mm / 左: {self.lidar_values[1]:.0f} mm / "
            f"右: {self.lidar_values[2]:.0f} mm / 後: {self.lidar_values[3]:.0f} mm\n"
            "LiDARレイはLiDAR状態がOKのときだけ表示します。"
        )
        self.display_status_label.setText(
            f"表示モード: {self.display_mode_text}\n"
            f"表示倍率: {self.current_scale_text} / スケール: {self.canvas.last_px_per_mm:.4f} px/mm"
        )
        object_count = len(self.field_model.get_objects())
        edit_state = "ON" if self.object_edit_check.isChecked() else "OFF"
        selected = self._selected_object()
        self._refresh_object_combo(selected)
        selected_text = f"{selected.label_ja} / 左上X {selected.rect.x_mm:.0f} / 左上Y {selected.rect.y_mm:.0f}" if selected else "なし"
        self.object_status_label.setText(
            f"登録オブジェクト: {object_count}件\n"
            f"編集モード: {edit_state}\n"
            f"選択中: {selected_text}\n"
            f"追加種類: {self.object_type_combo.currentText()}\n"
            f"移動量: {self._move_step_mm():.0f} mm\n"
            f"配置状態: {'変更あり' if self.objects_dirty else 'デフォルト'}"
        )
        self.warning_label.setText(self.state.warning)

    def _format_main(self, value_mm: float) -> str:
        if self.unit == "cm":
            return f"{value_mm / 10.0:.1f} cm"
        if self.unit == "m":
            return f"{value_mm / 1000.0:.3f} m"
        return f"{value_mm:.0f} mm"

    def _robot_start_pose_inside_line(self, robot_name: str) -> tuple[float, float, float]:
        x_mm, y_mm, theta_deg = self.field_model.get_robot_initial_pose(robot_name)
        start_zone = self.field_model.get_robot_start_zone(robot_name)
        rect = self.field_model.get_zone_rect(start_zone)
        if rect is None:
            return x_mm, y_mm, theta_deg

        tape_width = float(self.field_model.tape.get("normal_width_mm", 19.0))
        marker_radius = 135.0 if robot_name.lower() == "r2" else 90.0
        inset = max(tape_width + 10.0, marker_radius + tape_width)
        if rect.width_mm <= inset * 2.0 or rect.height_mm <= inset * 2.0:
            inset = min(rect.width_mm, rect.height_mm) * 0.25

        x_mm = min(max(float(x_mm), rect.left + inset), rect.right - inset)
        y_mm = min(max(float(y_mm), rect.top + inset), rect.bottom - inset)
        return x_mm, y_mm, float(theta_deg)

    @staticmethod
    def _sanitize_distance(value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(number) or math.isinf(number) or number < 0 or number > 10000:
            return 0.0
        return number
