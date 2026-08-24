from __future__ import annotations

from math import cos, pi, sin
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.gui_drive_model import DriveDiagnosticSnapshot, build_drive_diagnostic_snapshot

try:
    from ..steer_view_geometry import robot_angle_to_qt_rotation, robot_angle_to_screen_vector
except ImportError:
    from steer_view_geometry import robot_angle_to_qt_rotation, robot_angle_to_screen_vector
from .main_dashboard_widget import MotionVectorCanvas
from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _number(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError, OverflowError):
        return "-"


def _inversion(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "INVERTED" if value else "NORMAL"


class DriveLayoutCanvas(QWidget):
    """Four-wheel read-only command/observation visualization."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveDiagnosticWheelCanvas")
        self.setMinimumSize(430, 330)
        self._snapshot: DriveDiagnosticSnapshot | None = None

    @property
    def snapshot(self) -> DriveDiagnosticSnapshot | None:
        return self._snapshot

    def set_snapshot(self, snapshot: DriveDiagnosticSnapshot | None) -> None:
        self._snapshot = snapshot
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050806"))

        snapshot = self._snapshot
        if snapshot is None or not snapshot.wheels:
            painter.setPen(QColor("#6c9f2f"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "NO WHEEL SNAPSHOT")
            return

        rect = self.rect().adjusted(20, 34, -20, -30)
        body_w = min(rect.width() * 0.48, 230.0)
        body_h = min(rect.height() * 0.66, 220.0)
        body = QRectF(
            rect.center().x() - body_w / 2.0,
            rect.center().y() - body_h / 2.0,
            body_w,
            body_h,
        )
        painter.setPen(QPen(QColor("#ff8a1f"), 2.0))
        painter.setBrush(QColor("#0d1710"))
        painter.drawRoundedRect(body, 10.0, 10.0)
        painter.setPen(QPen(QColor("#b7ff35"), 3.0))
        painter.drawLine(body.center(), QPointF(body.center().x(), body.top() - 22.0))
        painter.drawLine(
            QPointF(body.center().x(), body.top() - 22.0),
            QPointF(body.center().x() - 7.0, body.top() - 10.0),
        )
        painter.drawLine(
            QPointF(body.center().x(), body.top() - 22.0),
            QPointF(body.center().x() + 7.0, body.top() - 10.0),
        )

        painter.setPen(QColor("#e7f4d7"))
        painter.drawText(12, 22, f"{snapshot.robot_id} / drive_type={snapshot.drive_type}")
        positions = (
            QPointF(body.left() + body_w * 0.13, body.top() + body_h * 0.18),
            QPointF(body.right() - body_w * 0.13, body.top() + body_h * 0.18),
            QPointF(body.left() + body_w * 0.13, body.bottom() - body_h * 0.18),
            QPointF(body.right() - body_w * 0.13, body.bottom() - body_h * 0.18),
        )
        for wheel, position in zip(snapshot.wheels[:4], positions):
            self._draw_wheel(painter, wheel, position, snapshot.steering_available)

        painter.setPen(QColor("#6c9f2f"))
        painter.drawText(
            QRectF(8.0, self.height() - 26.0, float(self.width() - 16), 20.0),
            Qt.AlignmentFlag.AlignCenter,
            "green=command / cyan=observed / red=fault",
        )

    def _draw_wheel(self, painter: QPainter, wheel, position: QPointF, steering_available: bool) -> None:
        angle = 0.0
        if steering_available:
            angle = wheel.observed_steering_deg
            if angle is None:
                angle = wheel.commanded_steering_deg
            angle = float(angle or 0.0)
        faulted = wheel.status in {"FAULT", "SAFETY_FAULT"}
        painter.save()
        painter.translate(position)
        painter.rotate(robot_angle_to_qt_rotation(angle))
        painter.setPen(QPen(QColor("#ff3b30" if faulted else "#b7ff35"), 2.0))
        painter.setBrush(QColor("#3a0907" if faulted else "#172017"))
        painter.drawRoundedRect(QRectF(-12.0, -31.0, 24.0, 62.0), 5.0, 5.0)
        painter.restore()

        direction_angle = angle + (180.0 if wheel.command_direction == "REVERSE" else 0.0)
        command_magnitude = abs(float(wheel.command_target or 0.0))
        if command_magnitude > 1e-9:
            self._draw_direction_arrow(painter, position, direction_angle, 50.0, QColor("#b7ff35"), 4.0)
        observed_magnitude = abs(float(wheel.observed_rpm or 0.0))
        if observed_magnitude > 1e-9:
            observed_angle = angle + (180.0 if float(wheel.observed_rpm) < 0.0 else 0.0)
            self._draw_direction_arrow(painter, position, observed_angle, 34.0, QColor("#ff8a1f"), 2.0)

        left_side = wheel.logical_index in (0, 2)
        label_rect = QRectF(
            position.x() - 125.0 if left_side else position.x() + 20.0,
            position.y() - 24.0,
            104.0,
            52.0,
        )
        painter.setPen(QColor("#ff8f86" if faulted else "#e7f4d7"))
        align = Qt.AlignmentFlag.AlignRight if left_side else Qt.AlignmentFlag.AlignLeft
        painter.drawText(
            label_rect,
            align | Qt.AlignmentFlag.AlignVCenter,
            f"{wheel.name}\n{wheel.status}",
        )

    @staticmethod
    def _draw_direction_arrow(
        painter: QPainter,
        start: QPointF,
        angle_deg: float,
        length: float,
        color: QColor,
        width: float,
    ) -> None:
        dx, dy = robot_angle_to_screen_vector(angle_deg)
        end = QPointF(start.x() + dx * length, start.y() + dy * length)
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(start, end)
        angle = pi / 2.0 - angle_deg * pi / 180.0
        head = QPolygonF(
            (
                end,
                QPointF(end.x() - 10.0 * cos(angle - pi / 6.0), end.y() - 10.0 * sin(angle - pi / 6.0)),
                QPointF(end.x() - 10.0 * cos(angle + pi / 6.0), end.y() - 10.0 * sin(angle + pi / 6.0)),
            )
        )
        painter.setBrush(color)
        painter.drawPolygon(head)


class DriveDiagnosticWidget(QWidget):
    """Snapshot-only Drive Diagnostic renderer with no command API."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("driveDiagnosticWidget")
        self._fleet: Any | None = None
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._diagnostic: DriveDiagnosticSnapshot | None = None
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def diagnostic_snapshot(self) -> DriveDiagnosticSnapshot | None:
        return self._diagnostic

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
        self._fleet = fleet
        self._robots = robots
        self.select_robot(selected, emit=False)

    def select_robot(self, robot_id: str, *, emit: bool = True) -> None:
        if robot_id not in {"R1", "R2"}:
            raise ValueError("robot_id must be R1 or R2")
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

        title = QLabel("Drive Diagnostic")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "READ ONLY: shared FleetDashboardSnapshot の表示専用です。"
                "ARM・走行・calibration・Serial送信機能はありません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"driveDiagnosticSelect{robot_id}Button")
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
        self.fault_banner.setObjectName("driveDiagnosticFaultBanner")
        self.fault_banner.setWordWrap(True)
        self.fault_banner.setMinimumHeight(54)
        layout.addWidget(self.fault_banner)

        status_grid = QGridLayout()
        self.selected_state_label = self._detail_label("driveDiagnosticSelectedState")
        self.node_state_label = self._detail_label("driveDiagnosticNodeState")
        status_grid.addWidget(boxed("Safety / readiness", self.selected_state_label), 0, 0)
        status_grid.addWidget(boxed("Drive node connection", self.node_state_label), 0, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        layout.addLayout(status_grid)

        visual_grid = QGridLayout()
        self.vector_canvas = MotionVectorCanvas()
        self.motion_label = self._detail_label("driveDiagnosticMotionValues")
        motion_body = QWidget()
        motion_layout = QVBoxLayout(motion_body)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        motion_layout.addWidget(self.vector_canvas)
        motion_layout.addWidget(self.motion_label)
        visual_grid.addWidget(boxed("推進方向 / 旋回ベクトル", motion_body), 0, 0)
        self.wheel_canvas = DriveLayoutCanvas()
        visual_grid.addWidget(boxed("Wheel command / observed", self.wheel_canvas), 0, 1)
        visual_grid.setColumnStretch(0, 1)
        visual_grid.setColumnStretch(1, 1)
        layout.addLayout(visual_grid)

        headers = (
            "Wheel",
            "Status",
            "Command",
            "Direction",
            "RPM obs",
            "PWM obs",
            "Steer cmd",
            "Steer obs",
            "Motor inv",
            "Servo inv",
            "Node link",
            "Fault",
        )
        self.wheel_table = QTableWidget(0, len(headers))
        self.wheel_table.setObjectName("driveDiagnosticWheelTable")
        self.wheel_table.setHorizontalHeaderLabels(headers)
        self.wheel_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wheel_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.wheel_table.setAlternatingRowColors(True)
        self.wheel_table.verticalHeader().setVisible(False)
        self.wheel_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.wheel_table.horizontalHeader().setStretchLastSection(True)
        self.wheel_table.setMinimumHeight(230)
        layout.addWidget(boxed("Per-wheel diagnostics", self.wheel_table))
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
        self.snapshot_time_label.setText("snapshot: 未接続")
        self.fault_banner.setText("WARNING: shared snapshot が未接続です。旧Mock/Serial値は表示しません。")
        self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        self.selected_state_label.setText(f"{self._selected_robot} | OFFLINE | UNKNOWN | READY=false")
        self.node_state_label.setText("communication=OFFLINE\ndrive node=UNKNOWN\nper-wheel mapping=UNAVAILABLE")
        self.motion_label.setText("vx=+0.00 / vy=+0.00 / magnitude=0.00\nomega=+0.00 / rotation=STOP / accepted=false")
        self.vector_canvas.set_motion(None)
        self.wheel_canvas.set_snapshot(None)
        self.wheel_table.setRowCount(0)

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return

        diagnostic = build_drive_diagnostic_snapshot(robot)
        self._diagnostic = diagnostic
        self.snapshot_time_label.setText(f"snapshot: {diagnostic.timestamp_ms} ms")
        states = [diagnostic.robot_id, diagnostic.drive_type, diagnostic.connection, diagnostic.safety_state]
        states.append("READY" if diagnostic.ready else "NOT_READY")
        states.append("ARMED" if diagnostic.armed else "DISARMED")
        self.selected_state_label.setText(" | ".join(states))
        self.node_state_label.setText(
            f"communication={diagnostic.connection}\n"
            f"drive node inventory={diagnostic.drive_node_state}\n"
            f"nodes={diagnostic.drive_node_summary}\n"
            "per-wheel mapping=not defined; role-level link shown for every wheel"
        )
        self._render_fault(diagnostic)
        motion = diagnostic.motion
        self.vector_canvas.set_motion(motion)
        heading = _number(motion.heading_deg, 1, " deg")
        self.motion_label.setText(
            f"vx={motion.vx:+.2f} / vy={motion.vy:+.2f} / magnitude={motion.magnitude:.2f} / heading={heading}\n"
            f"omega={motion.omega:+.2f} / rotation={motion.rotation_direction} / accepted={str(motion.accepted_by_safety).lower()}"
        )
        self.wheel_canvas.set_snapshot(diagnostic)
        self._render_wheels(diagnostic)

    def _render_fault(self, diagnostic: DriveDiagnosticSnapshot) -> None:
        event = diagnostic.fault_event
        if event is not None:
            self.fault_banner.setText(
                f"FAULT | source={event.source} | node={event.node_id or '-'} | reason={event.reason}\n"
                f"timestamp={event.timestamp_ms if event.timestamp_ms is not None else '-'} ms | "
                f"Safety response={event.safety_response}"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if diagnostic.fault:
            self.fault_banner.setText(
                f"FAULT | {diagnostic.fault} | Safety response={diagnostic.safety_state}/DISARMED"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if diagnostic.warnings:
            self.fault_banner.setText("WARNING | " + " | ".join(diagnostic.warnings))
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
            return
        self.fault_banner.setText("No active drive fault or warning")
        self.fault_banner.setStyleSheet("background:#14532d; color:#dcfce7; padding:12px; font-weight:800;")

    def _render_wheels(self, diagnostic: DriveDiagnosticSnapshot) -> None:
        self.wheel_table.setRowCount(len(diagnostic.wheels))
        for row, wheel in enumerate(diagnostic.wheels):
            if wheel.command_target is None or wheel.command_control is None:
                command = "-"
            else:
                command = f"{wheel.command_control.upper()} {wheel.command_target:+.1f}"
            steering_command = _number(wheel.commanded_steering_deg, 1, " deg")
            steering_observed = _number(wheel.observed_steering_deg, 1, " deg")
            if not diagnostic.steering_available:
                steering_command = steering_observed = "N/A"
            values = (
                wheel.name,
                wheel.status,
                command,
                wheel.command_direction,
                _number(wheel.observed_rpm, 1),
                _number(wheel.observed_pwm, 1),
                steering_command,
                steering_observed,
                _inversion(wheel.motor_inverted),
                _inversion(wheel.servo_inverted),
                wheel.node_link,
                wheel.fault or "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.wheel_table.setItem(row, column, item)


def create_drive_diagnostic_tab(host: Any) -> DriveDiagnosticWidget:
    widget = DriveDiagnosticWidget()
    host.drive_diagnostic_widget = widget
    return widget
