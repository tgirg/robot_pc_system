from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.gui_sensor_model import (
    SensorDiagnosticSnapshot,
    build_sensor_diagnostic_snapshot,
)

from .ui_helpers import boxed, make_notice, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class SensorDiagnosticWidget(QWidget):
    """Snapshot-only sensor diagnostics with no legacy sensor or Serial owner."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sensorDiagnosticWidget")
        self._fleet: Any | None = None
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._diagnostic: SensorDiagnosticSnapshot | None = None
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def diagnostic_snapshot(self) -> SensorDiagnosticSnapshot | None:
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Sensor Diagnostic")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "R2センサ確認一覧: RAW値は個別テスト後に反映します。旧Mock/DUMMY値は使いません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"sensorDiagnosticSelect{robot_id}Button")
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        self.snapshot_time_label = QLabel("snapshot: 未接続")
        selector.addWidget(self.snapshot_time_label)
        layout.addLayout(selector)

        self.fault_banner = QLabel()
        self.fault_banner.setObjectName("sensorDiagnosticFaultBanner")
        self.fault_banner.setWordWrap(True)
        self.fault_banner.setMinimumHeight(32)
        self.fault_banner.setMaximumHeight(48)
        layout.addWidget(self.fault_banner)

        status_grid = QGridLayout()
        self.selected_state_label = self._detail_label("sensorDiagnosticSelectedState")
        self.inventory_state_label = self._detail_label("sensorDiagnosticInventoryState")
        status_grid.addWidget(boxed("Safety / readiness", self.selected_state_label), 0, 0)
        status_grid.addWidget(boxed("Sensor inventory coverage", self.inventory_state_label), 0, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 2)
        layout.addLayout(status_grid)

        self.boundary_label = self._detail_label("sensorDiagnosticBoundary")
        layout.addWidget(boxed("Authoritative data boundary", self.boundary_label))

        sensor_headers = (
            "Sensor",
            "GPIO",
            "Purpose",
            "Connection",
            "RAW / Value",
            "Note",
        )
        self.sensor_table = QTableWidget(0, len(sensor_headers))
        self.sensor_table.setObjectName("sensorDiagnosticTable")
        self.sensor_table.setHorizontalHeaderLabels(sensor_headers)
        self._configure_table(self.sensor_table, minimum_height=360)
        self.sensor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sensor_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sensor_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sensor_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sensor_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.sensor_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(boxed("R2 sensor check list", self.sensor_table))

        node_headers = ("Node ID", "Required", "Node state", "Ports", "Mapping")
        self.unmapped_node_table = QTableWidget(0, len(node_headers))
        self.unmapped_node_table.setObjectName("sensorDiagnosticUnmappedNodeTable")
        self.unmapped_node_table.setHorizontalHeaderLabels(node_headers)
        self._configure_table(self.unmapped_node_table, minimum_height=90)
        self.unmapped_node_box = boxed("Unmapped sensor-role nodes", self.unmapped_node_table)
        layout.addWidget(self.unmapped_node_box)

        self.empty_state_label = self._detail_label("sensorDiagnosticEmptyState")
        layout.addWidget(self.empty_state_label)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(content)

    @staticmethod
    def _detail_label(object_name: str) -> QLabel:
        label = QLabel()
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    @staticmethod
    def _configure_table(table: QTableWidget, *, minimum_height: int) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(minimum_height)

    def _render_no_snapshot(self) -> None:
        for value, button in self._robot_buttons.items():
            button.setChecked(value == self._selected_robot)
        self._diagnostic = None
        self.snapshot_time_label.setText("snapshot: 未接続")
        self.fault_banner.setText("WARNING: shared snapshot が未接続です。旧Mock/DUMMY値は表示しません。")
        self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        self.selected_state_label.setText(f"{self._selected_robot} | OFFLINE | UNKNOWN | READY=false")
        self.inventory_state_label.setText("inventory=UNAVAILABLE")
        self.boundary_label.setText(
            "Sensor inventory, node mapping, value, unit, validity, stale, fault, and last update: unavailable"
        )
        self.sensor_table.setRowCount(0)
        self._fit_table_height(self.sensor_table)
        self.unmapped_node_table.setRowCount(0)
        self._fit_table_height(self.unmapped_node_table)
        self.unmapped_node_box.setVisible(False)
        self.empty_state_label.setText("No shared sensor snapshot")

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return

        diagnostic = build_sensor_diagnostic_snapshot(robot)
        self._diagnostic = diagnostic
        self.snapshot_time_label.setText(f"snapshot: {diagnostic.timestamp_ms} ms")
        states = [diagnostic.robot_id, diagnostic.connection, diagnostic.safety_state]
        states.append("READY" if diagnostic.ready else "NOT_READY")
        states.append("ARMED" if diagnostic.armed else "DISARMED")
        self.selected_state_label.setText(" | ".join(states))
        self.inventory_state_label.setText(
            f"inventory={diagnostic.inventory_state}\n{diagnostic.inventory_summary}"
        )
        telemetry_age = (
            f"{diagnostic.shared_telemetry_age_ms} ms"
            if diagnostic.shared_telemetry_age_ms is not None
            else "UNKNOWN"
        )
        self.boundary_label.setText(
            f"drive-role nodes excluded={diagnostic.excluded_drive_nodes} (Drive Diagnostic owns wheel encoders)\n"
            f"non-sensor nodes excluded={diagnostic.excluded_non_sensor_nodes} (Mechanism/other domains own them)\n"
            f"shared telemetry age={telemetry_age}; this is not assigned to an individual sensor\n"
            "R2 custom board GPIO names are shown as a check list; live RAW values are accepted only after "
            "individual serial checks. Legacy MockSensors, *_STATUS,DUMMY, and prototype LSB CSV values are not loaded as live state."
        )
        self._render_fault(diagnostic)
        self._render_sensors(diagnostic)
        self._render_unmapped_nodes(diagnostic)
        if diagnostic.unmapped_nodes:
            self.empty_state_label.setText(
                "WARNING: node identity alone does not define sensors. Add an authoritative per-robot sensor "
                "inventory, units, validity/stale policy, and telemetry mapping before sensor rows can be confirmed."
            )
        else:
            self.empty_state_label.setText(
                "R2 sensor rows are connection-check targets. Values remain UNKNOWN until each sensor is tested."
            )

    def _render_fault(self, diagnostic: SensorDiagnosticSnapshot) -> None:
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
            arm_state = "ARMED" if diagnostic.armed else "DISARMED"
            self.fault_banner.setText(
                f"FAULT | {diagnostic.fault} | Safety response={diagnostic.safety_state}/{arm_state}"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if diagnostic.warnings:
            self.fault_banner.setText("WARNING | " + " | ".join(diagnostic.warnings))
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
            return
        self.fault_banner.setText("No active robot fault or warning")
        self.fault_banner.setStyleSheet("background:#14532d; color:#dcfce7; padding:12px; font-weight:800;")

    def _render_sensors(self, diagnostic: SensorDiagnosticSnapshot) -> None:
        self.sensor_table.setRowCount(len(diagnostic.sensors))
        for row, sensor in enumerate(diagnostic.sensors):
            stale = "UNKNOWN" if sensor.stale is None else "YES" if sensor.stale else "NO"
            values = (
                sensor.sensor_name,
                sensor.gpio,
                sensor.purpose,
                sensor.connection,
                sensor.current_value if sensor.current_value is not None else "UNKNOWN",
                sensor.note or sensor.validity or stale,
            )
            self._set_row(self.sensor_table, row, values)
        self._fit_table_height(self.sensor_table)

    def _render_unmapped_nodes(self, diagnostic: SensorDiagnosticSnapshot) -> None:
        self.unmapped_node_table.setRowCount(len(diagnostic.unmapped_nodes))
        self.unmapped_node_box.setVisible(bool(diagnostic.unmapped_nodes))
        for row, node in enumerate(diagnostic.unmapped_nodes):
            values = (
                node.node_id,
                "YES" if node.required else "NO",
                node.node_state,
                ", ".join(node.ports) or "-",
                node.mapping_state,
            )
            self._set_row(self.unmapped_node_table, row, values)
        self._fit_table_height(self.unmapped_node_table)

    @staticmethod
    def _set_row(table: QTableWidget, row: int, values: tuple[object, ...]) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, item)

    @staticmethod
    def _fit_table_height(table: QTableWidget) -> None:
        rows = max(1, table.rowCount())
        row_height = 24
        table.verticalHeader().setDefaultSectionSize(row_height)
        height = table.horizontalHeader().height() + rows * row_height + 6
        table.setMinimumHeight(height)
        table.setMaximumHeight(height)


def create_sensor_diagnostic_tab(host: Any) -> SensorDiagnosticWidget:
    widget = SensorDiagnosticWidget()
    host.sensor_diagnostic_widget = widget
    return widget
