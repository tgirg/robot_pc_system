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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.gui_mechanism_model import (
    MechanismDiagnosticSnapshot,
    build_mechanism_diagnostic_snapshot,
)

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class MechanismDiagnosticWidget(QWidget):
    """Snapshot-only non-drive mechanism diagnostics with no command API."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mechanismDiagnosticWidget")
        self._fleet: Any | None = None
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._diagnostic: MechanismDiagnosticSnapshot | None = None
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def diagnostic_snapshot(self) -> MechanismDiagnosticSnapshot | None:
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

        title = QLabel("Mechanism Diagnostic")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "READ ONLY: non-drive mechanism inventory/telemetryがauthoritative shared snapshotに"
                "存在するときだけ表示します。manual actuation・DEBUG・Serial送信機能はありません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"mechanismDiagnosticSelect{robot_id}Button")
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
        self.fault_banner.setObjectName("mechanismDiagnosticFaultBanner")
        self.fault_banner.setWordWrap(True)
        self.fault_banner.setMinimumHeight(54)
        layout.addWidget(self.fault_banner)

        status_grid = QGridLayout()
        self.selected_state_label = self._detail_label("mechanismDiagnosticSelectedState")
        self.inventory_state_label = self._detail_label("mechanismDiagnosticInventoryState")
        status_grid.addWidget(boxed("Safety / readiness", self.selected_state_label), 0, 0)
        status_grid.addWidget(boxed("Mechanism inventory coverage", self.inventory_state_label), 0, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 2)
        layout.addLayout(status_grid)

        self.boundary_label = self._detail_label("mechanismDiagnosticBoundary")
        layout.addWidget(boxed("Authoritative data boundary", self.boundary_label))

        headers = (
            "Node ID",
            "Role",
            "Required",
            "Node state",
            "Ports",
            "Mapping",
            "Command",
            "State",
            "Limit",
            "Telemetry",
            "Fault",
        )
        self.mechanism_table = QTableWidget(0, len(headers))
        self.mechanism_table.setObjectName("mechanismDiagnosticTable")
        self.mechanism_table.setHorizontalHeaderLabels(headers)
        self.mechanism_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mechanism_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.mechanism_table.setAlternatingRowColors(True)
        self.mechanism_table.verticalHeader().setVisible(False)
        self.mechanism_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.mechanism_table.horizontalHeader().setStretchLastSection(True)
        self.mechanism_table.setMinimumHeight(230)
        layout.addWidget(boxed("Unmapped non-drive nodes (not confirmed mechanisms)", self.mechanism_table))

        self.empty_state_label = self._detail_label("mechanismDiagnosticEmptyState")
        layout.addWidget(self.empty_state_label)
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
        self.fault_banner.setText("WARNING: shared snapshot が未接続です。旧Mock/actuator値は表示しません。")
        self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
        self.selected_state_label.setText(f"{self._selected_robot} | OFFLINE | UNKNOWN | READY=false")
        self.inventory_state_label.setText("inventory=UNAVAILABLE")
        self.boundary_label.setText(
            "Node inventory, mechanism config, command/state, limits, telemetry, and fault mapping: unavailable"
        )
        self.mechanism_table.setRowCount(0)
        self.empty_state_label.setText("No shared mechanism snapshot")

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return

        diagnostic = build_mechanism_diagnostic_snapshot(robot)
        self._diagnostic = diagnostic
        self.snapshot_time_label.setText(f"snapshot: {diagnostic.timestamp_ms} ms")
        states = [diagnostic.robot_id, diagnostic.connection, diagnostic.safety_state]
        states.append("READY" if diagnostic.ready else "NOT_READY")
        states.append("ARMED" if diagnostic.armed else "DISARMED")
        self.selected_state_label.setText(" | ".join(states))
        self.inventory_state_label.setText(
            f"inventory={diagnostic.inventory_state}\n{diagnostic.inventory_summary}"
        )
        self.boundary_label.setText(
            f"drive-role nodes excluded={diagnostic.excluded_drive_nodes} (Drive Diagnostic owns them)\n"
            f"sensor-role nodes excluded={diagnostic.excluded_sensor_nodes} (future Sensor Diagnostic owns them)\n"
            "Legacy actuator buttons, hardware-profile notes, and candidate parts are not loaded as live state."
        )
        self._render_fault(diagnostic)
        self._render_nodes(diagnostic)
        if diagnostic.unmapped_nodes:
            self.empty_state_label.setText(
                "WARNING: node identity alone does not define a mechanism. Add an authoritative per-robot "
                "mechanism inventory and telemetry contract before mechanism rows can be confirmed."
            )
        else:
            self.empty_state_label.setText(
                "No confirmed non-drive mechanisms. Command/state/limit/telemetry remain N/A by design."
            )

    def _render_fault(self, diagnostic: MechanismDiagnosticSnapshot) -> None:
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
                f"FAULT | {diagnostic.fault} | "
                f"Safety response={diagnostic.safety_state}/{arm_state}"
            )
            self.fault_banner.setStyleSheet("background:#7f1d1d; color:#ffffff; padding:12px; font-weight:900;")
            return
        if diagnostic.warnings:
            self.fault_banner.setText("WARNING | " + " | ".join(diagnostic.warnings))
            self.fault_banner.setStyleSheet("background:#6b4f12; color:#fff7cc; padding:12px; font-weight:800;")
            return
        self.fault_banner.setText("No active robot fault or warning")
        self.fault_banner.setStyleSheet("background:#14532d; color:#dcfce7; padding:12px; font-weight:800;")

    def _render_nodes(self, diagnostic: MechanismDiagnosticSnapshot) -> None:
        self.mechanism_table.setRowCount(len(diagnostic.unmapped_nodes))
        for row, node in enumerate(diagnostic.unmapped_nodes):
            values = (
                node.node_id,
                node.role,
                "YES" if node.required else "NO",
                node.node_state,
                ", ".join(node.ports) or "-",
                node.mapping_state,
                node.command or "N/A",
                node.state or "N/A",
                node.limit or "N/A",
                node.telemetry or "N/A",
                node.fault or "N/A",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.mechanism_table.setItem(row, column, item)


def create_mechanism_diagnostic_tab(host: Any) -> MechanismDiagnosticWidget:
    widget = MechanismDiagnosticWidget()
    host.mechanism_diagnostic_widget = widget
    return widget
