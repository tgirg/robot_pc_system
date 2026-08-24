from __future__ import annotations

from math import atan2, cos, hypot, pi, sin
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import boxed, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _optional_text(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value}{suffix}"


def _float_text(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError, OverflowError):
        return "-"


class MotionVectorCanvas(QWidget):
    """Read-only translation and rotation visualization for one snapshot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainDashboardVectorCanvas")
        self.setMinimumSize(300, 250)
        self._vx = 0.0
        self._vy = 0.0
        self._omega = 0.0
        self._accepted = False

    @property
    def motion(self) -> tuple[float, float, float, bool]:
        return self._vx, self._vy, self._omega, self._accepted

    def set_motion(self, motion: Any | None) -> None:
        if motion is None:
            self._vx = self._vy = self._omega = 0.0
            self._accepted = False
        else:
            try:
                self._vx = float(motion.vx)
                self._vy = float(motion.vy)
                self._omega = float(motion.omega)
            except (AttributeError, TypeError, ValueError, OverflowError):
                self._vx = self._vy = self._omega = 0.0
            self._accepted = bool(getattr(motion, "accepted_by_safety", False))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050806"))

        painter.setPen(QPen(QColor("#18351f"), 1.0))
        for offset in range(18, max(self.width(), self.height()), 24):
            painter.drawLine(offset, 0, 0, offset)

        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        robot_rect = QRectF(center.x() - 55.0, center.y() - 42.0, 110.0, 84.0)
        painter.setPen(QPen(QColor("#ff8a1f"), 3.0))
        painter.setBrush(QColor("#0d1710"))
        painter.drawRect(robot_rect)
        painter.setPen(QColor("#b7ff35"))
        painter.drawText(robot_rect, Qt.AlignmentFlag.AlignCenter, "ROBOT")

        magnitude = hypot(self._vx, self._vy)
        if magnitude > 1e-9:
            scale = min(1.0, magnitude)
            # Robot coordinates are +vx forward and +vy left.
            dx = -self._vy / magnitude * 82.0 * scale
            dy = -self._vx / magnitude * 82.0 * scale
            color = QColor("#b7ff35" if self._accepted else "#ffe14a")
            self._draw_arrow(painter, center, QPointF(center.x() + dx, center.y() + dy), color)

        if abs(self._omega) > 1e-9:
            painter.setPen(QPen(QColor("#ff8a1f"), 4.0))
            arc = QRectF(center.x() - 78.0, center.y() - 68.0, 156.0, 136.0)
            span = 250 * 16 if self._omega > 0.0 else -250 * 16
            painter.drawArc(arc, -35 * 16, span)
            painter.setPen(QColor("#ffe14a"))
            direction = "CCW" if self._omega > 0.0 else "CW"
            painter.drawText(
                QRectF(0.0, self.height() - 30.0, float(self.width()), 24.0),
                Qt.AlignmentFlag.AlignCenter,
                f"{direction}  omega={self._omega:+.2f}",
            )

        painter.setPen(QColor("#6c9f2f"))
        painter.drawText(10, 22, "+vx: forward / +vy: left")

    @staticmethod
    def _draw_arrow(painter: QPainter, start: QPointF, end: QPointF, color: QColor) -> None:
        painter.setPen(QPen(color, 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(start, end)
        angle = atan2(end.y() - start.y(), end.x() - start.x())
        head = QPolygonF(
            [
                end,
                QPointF(end.x() - 15.0 * cos(angle - pi / 6.0), end.y() - 15.0 * sin(angle - pi / 6.0)),
                QPointF(end.x() - 15.0 * cos(angle + pi / 6.0), end.y() - 15.0 * sin(angle + pi / 6.0)),
            ]
        )
        painter.setBrush(color)
        painter.drawPolygon(head)


class MainDashboardWidget(QWidget):
    """Renderer for immutable FleetDashboardSnapshot-like objects.

    The widget deliberately has no serial, ARM, drive, or calibration API.
    Selection changes only which already-supplied robot snapshot is displayed.
    """

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainDashboardWidget")
        self._fleet: Any | None = None
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._summary_labels: dict[str, QLabel] = {}
        self._robot_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

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
        self._render_summaries()
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

        title = QLabel("Main Dashboard")
        set_section_title(title)
        layout.addWidget(title)

        selector = QWidget()
        selector_layout = QHBoxLayout(selector)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"selectRobot{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector_layout.addWidget(button)
        selector_layout.addStretch(1)
        self.snapshot_time_label = QLabel("snapshot: 未接続")
        self.snapshot_time_label.setObjectName("cardDetail")
        selector_layout.addWidget(self.snapshot_time_label)
        layout.addWidget(selector)

        summaries = QGridLayout()
        summaries.setSpacing(10)
        for column, robot_id in enumerate(("R1", "R2")):
            label = QLabel()
            label.setObjectName(f"mainDashboard{robot_id}Summary")
            label.setWordWrap(True)
            label.setMinimumHeight(112)
            self._summary_labels[robot_id] = label
            summaries.addWidget(boxed(f"{robot_id} overview", label), 0, column)
        summaries.setColumnStretch(0, 1)
        summaries.setColumnStretch(1, 1)
        layout.addLayout(summaries)

        self.fault_banner = QLabel()
        self.fault_banner.setObjectName("mainDashboardFaultBanner")
        self.fault_banner.setWordWrap(True)
        self.fault_banner.setMinimumHeight(54)
        layout.addWidget(self.fault_banner)

        self.selected_state_label = QLabel()
        self.selected_state_label.setObjectName("mainDashboardSelectedState")
        self.selected_state_label.setWordWrap(True)
        layout.addWidget(boxed("Safety / readiness", self.selected_state_label))

        details = QGridLayout()
        details.setSpacing(10)
        self.communication_label = self._detail_label("mainDashboardCommunication")
        self.autonomy_label = self._detail_label("mainDashboardAutonomy")
        self.telemetry_label = self._detail_label("mainDashboardTelemetry")
        details.addWidget(boxed("Controller / communication", self.communication_label), 0, 0)
        details.addWidget(boxed("Autonomy / Competition", self.autonomy_label), 0, 1)
        details.addWidget(boxed("Telemetry", self.telemetry_label), 0, 2)
        for column in range(3):
            details.setColumnStretch(column, 1)
        layout.addLayout(details)

        lower = QGridLayout()
        lower.setSpacing(10)
        self.vector_canvas = MotionVectorCanvas()
        self.motion_label = self._detail_label("mainDashboardMotionValues")
        motion_body = QWidget()
        motion_layout = QVBoxLayout(motion_body)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        motion_layout.addWidget(self.vector_canvas)
        motion_layout.addWidget(self.motion_label)
        lower.addWidget(boxed("推進方向 / 旋回ベクトル", motion_body), 0, 0, 2, 1)

        self.node_table = self._table(("Node", "Role", "Required", "State", "Ports"), "mainDashboardNodeTable")
        self.wheel_table = self._table(
            ("Wheel", "Command", "Direction", "RPM", "PWM", "Steer cmd/obs", "Inversion", "Fault"),
            "mainDashboardWheelTable",
        )
        lower.addWidget(boxed("ESP32 / node status", self.node_table), 0, 1)
        lower.addWidget(boxed("Wheel status", self.wheel_table), 1, 1)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 2)
        layout.addLayout(lower)
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

    @staticmethod
    def _table(headers: tuple[str, ...], object_name: str) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setObjectName(object_name)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(170)
        return table

    def _render_no_snapshot(self) -> None:
        for robot_id, label in self._summary_labels.items():
            label.setText(f"{robot_id}: SNAPSHOT未接続\nOFFLINE / UNKNOWN\nbackend=UNBOUND")
        self._robot_buttons["R1"].setChecked(True)
        self.fault_banner.setText("WARNING: 共有Controller snapshotがまだ接続されていません。旧Mock/Serial値は表示しません。")
        self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        self.selected_state_label.setText("R1 | OFFLINE | UNKNOWN | READY=false")
        self.communication_label.setText("backend: UNBOUND\ncontroller: DISCONNECTED\ncommunication: OFFLINE")
        self.autonomy_label.setText("autonomy: UNKNOWN\nmission step: -\ncompetition: -")
        self.telemetry_label.setText("battery: -\ntelemetry age: -\nsequence: -")
        self.motion_label.setText("vx=+0.00 / vy=+0.00 / magnitude=0.00\nomega=+0.00 / rotation=STOP / accepted=false")
        self.vector_canvas.set_motion(None)
        self.node_table.setRowCount(0)
        self.wheel_table.setRowCount(0)

    def _render_summaries(self) -> None:
        timestamps = []
        for robot_id in ("R1", "R2"):
            snapshot = self._robots.get(robot_id)
            label = self._summary_labels[robot_id]
            if snapshot is None:
                label.setText(f"{robot_id}: SNAPSHOTなし\nOFFLINE / UNKNOWN")
                continue
            timestamps.append(int(getattr(snapshot, "timestamp_ms", 0)))
            tokens = [_enum_value(snapshot.connection), "READY" if snapshot.ready else "NOT_READY", snapshot.safety_state]
            if snapshot.arm_pending and "ARM_PENDING" not in tokens:
                tokens.append("ARM_PENDING")
            if snapshot.armed and "ARMED" not in tokens:
                tokens.append("ARMED")
            if snapshot.fault or snapshot.fault_event:
                tokens.append("FAULT")
            if snapshot.competition_state:
                tokens.append(f"COMPETITION={snapshot.competition_state}")
            autonomy_state = snapshot.autonomy.state or "UNKNOWN"
            step = snapshot.autonomy.current_step or "-"
            label.setText(
                f"{robot_id}: {' | '.join(tokens)}\n"
                f"backend={_enum_value(snapshot.backend)} / autonomy={autonomy_state} / step={step}\n"
                f"nodes={len(snapshot.nodes)} / warnings={len(snapshot.warnings)} / severity={_enum_value(snapshot.severity)}"
            )
        latest = max(timestamps) if timestamps else 0
        self.snapshot_time_label.setText(f"snapshot: {latest} ms" if latest else "snapshot: timestamp unknown")

    def _render_selected(self) -> None:
        snapshot = self._robots.get(self._selected_robot)
        if snapshot is None:
            self.selected_state_label.setText(f"{self._selected_robot} | SNAPSHOTなし | OFFLINE | UNKNOWN")
            self.fault_banner.setText("WARNING: 選択ロボットの共有snapshotがありません。")
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
            self.communication_label.setText("backend: UNBOUND\ncommunication: OFFLINE")
            self.autonomy_label.setText("autonomy: UNKNOWN\nmission step: -\ncompetition: -")
            self.telemetry_label.setText("battery: -\ntelemetry age: -\nsequence: -")
            self.motion_label.setText("vx=+0.00 / vy=+0.00 / magnitude=0.00\nomega=+0.00 / rotation=STOP / accepted=false")
            self.vector_canvas.set_motion(None)
            self.node_table.setRowCount(0)
            self.wheel_table.setRowCount(0)
            return

        states = [_enum_value(snapshot.connection), snapshot.safety_state]
        states.append("READY" if snapshot.ready else "NOT_READY")
        if snapshot.safe and "SAFE" not in states:
            states.append("SAFE")
        if snapshot.arm_pending and "ARM_PENDING" not in states:
            states.append("ARM_PENDING")
        if snapshot.armed and "ARMED" not in states:
            states.append("ARMED")
        if snapshot.fault or snapshot.fault_event:
            states.append("FAULT")
        if snapshot.competition_state:
            states.append(f"COMPETITION={snapshot.competition_state}")
        self.selected_state_label.setText(f"{self._selected_robot} | " + " | ".join(states))

        self._render_fault(snapshot)
        controller = snapshot.controller_name or "-"
        self.communication_label.setText(
            f"backend: {_enum_value(snapshot.backend)}\n"
            f"controller: {'CONNECTED' if snapshot.controller_connected else 'DISCONNECTED'} ({controller})\n"
            f"communication: {_enum_value(snapshot.connection)} / reconnect={snapshot.reconnect_phase or '-'}\n"
            f"RX age: {_optional_text(snapshot.communication_age_ms, ' ms')} / telemetry age: {_optional_text(snapshot.telemetry_age_ms, ' ms')}"
        )
        autonomy = snapshot.autonomy
        self.autonomy_label.setText(
            f"autonomy: {autonomy.state or 'UNKNOWN'} / mission={autonomy.mission_id or '-'}\n"
            f"current step: {autonomy.current_step or '-'} / attempt={autonomy.attempt or '-'}\n"
            f"fallback: {autonomy.fallback_id or '-'} / reason={autonomy.reason or '-'}\n"
            f"competition: {snapshot.competition_state or '-'}"
        )
        battery = _float_text(snapshot.battery_voltage_v, 2, " V")
        percent = _float_text(snapshot.battery_percent, 1, " %")
        self.telemetry_label.setText(
            f"battery: {battery} / {percent}\n"
            f"sequence: {_optional_text(snapshot.telemetry_sequence)} / fault_flags={_optional_text(snapshot.telemetry_fault_flags)}\n"
            f"drive type: {snapshot.drive_type} / timestamp={snapshot.timestamp_ms} ms"
        )

        motion = snapshot.motion
        self.vector_canvas.set_motion(motion)
        self.motion_label.setText(
            f"vx={motion.vx:+.2f} / vy={motion.vy:+.2f} / magnitude={motion.magnitude:.2f} / heading={_float_text(motion.heading_deg, 1, ' deg')}\n"
            f"omega={motion.omega:+.2f} / rotation={motion.rotation_direction} / accepted={str(motion.accepted_by_safety).lower()}"
        )
        self._render_nodes(snapshot.nodes)
        self._render_wheels(snapshot.wheels)

    def _render_fault(self, snapshot: Any) -> None:
        event = snapshot.fault_event
        if event is not None:
            node = event.node_id or "-"
            timestamp = _optional_text(event.timestamp_ms, " ms")
            self.fault_banner.setText(
                f"FAULT | severity={_enum_value(event.severity)} | source={event.source} | node={node}\n"
                f"reason={event.reason} | timestamp={timestamp} | Safety response={event.safety_response}"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if snapshot.fault:
            self.fault_banner.setText(f"FAULT | {snapshot.fault} | Safety response={snapshot.safety_state}/DISARMED")
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if snapshot.warnings:
            self.fault_banner.setText("WARNING | " + " | ".join(snapshot.warnings))
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
            return
        self.fault_banner.setText("No active fault or warning")
        self.fault_banner.setStyleSheet("background:#14532d; color:#dcfce7; padding:12px; font-weight:800;")

    def _render_nodes(self, nodes: Any) -> None:
        values = tuple(nodes)
        self.node_table.setRowCount(len(values))
        for row, node in enumerate(values):
            self._set_row(
                self.node_table,
                row,
                (
                    node.node_id,
                    node.role,
                    "YES" if node.required else "NO",
                    _enum_value(node.state),
                    ", ".join(node.ports) or "-",
                ),
            )

    def _render_wheels(self, wheels: Any) -> None:
        values = tuple(wheels)
        self.wheel_table.setRowCount(len(values))
        for row, wheel in enumerate(values):
            control = wheel.command_control or "-"
            command = f"{control} {_float_text(wheel.command_target, 1)}"
            steering = f"{_float_text(wheel.commanded_steering_deg, 1)} / {_float_text(wheel.observed_steering_deg, 1)}"
            inversion = f"motor={_optional_text(wheel.motor_inverted)} servo={_optional_text(wheel.servo_inverted)}"
            self._set_row(
                self.wheel_table,
                row,
                (
                    f"{wheel.name} ({wheel.logical_index})",
                    command,
                    wheel.command_direction,
                    _float_text(wheel.observed_rpm, 1),
                    _float_text(wheel.observed_pwm, 1),
                    steering,
                    inversion,
                    wheel.fault or "-",
                ),
            )

    @staticmethod
    def _set_row(table: QTableWidget, row: int, values: tuple[str, ...]) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, item)


def create_main_dashboard_tab(host: Any) -> MainDashboardWidget:
    widget = MainDashboardWidget()
    host.main_dashboard_widget = widget
    return widget
