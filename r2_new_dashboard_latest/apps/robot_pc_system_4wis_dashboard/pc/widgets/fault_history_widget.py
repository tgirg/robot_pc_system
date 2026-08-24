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

from pc_controller.autonomy import RobotId
from pc_controller.gui_fault_history_model import FaultHistorySnapshot, FaultHistoryStore

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class FaultHistoryWidget(QWidget):
    """Session-local fault/warning history with acknowledgement-only controls."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("faultHistoryWidget")
        self._fleet: Any | None = None
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._history_store = FaultHistoryStore()
        self._history: FaultHistorySnapshot | None = None
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def history_snapshot(self) -> FaultHistorySnapshot | None:
        return self._history

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
        self._history_store.ingest_fleet(fleet)
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

        title = QLabel("Fault / Warning History")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "READ ONLY ROBOT STATE: immutable shared snapshotsのevent edgeだけをGUI session内に保持します。"
                "Acknowledgementはlocal view metadataで、Safety root cause・ARM・Serial・configを変更しません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"faultHistorySelect{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        self.snapshot_time_label = QLabel("snapshot: 未接続")
        selector.addWidget(self.snapshot_time_label)
        layout.addLayout(selector)

        status_grid = QGridLayout()
        self.selected_state_label = self._detail_label("faultHistorySelectedState")
        self.counts_label = self._detail_label("faultHistoryCounts")
        status_grid.addWidget(boxed("History state", self.selected_state_label), 0, 0)
        status_grid.addWidget(boxed("Counts", self.counts_label), 0, 1)
        status_grid.setColumnStretch(0, 2)
        status_grid.setColumnStretch(1, 1)
        layout.addLayout(status_grid)

        self.boundary_label = self._detail_label("faultHistoryBoundary")
        layout.addWidget(boxed("Retention / acknowledgement boundary", self.boundary_label))

        headers = (
            "State",
            "Severity",
            "Source",
            "Node",
            "Reason",
            "Timestamp",
            "Safety response",
            "Acknowledgement",
        )
        self.history_table = QTableWidget(0, len(headers))
        self.history_table.setObjectName("faultHistoryTable")
        self.history_table.setHorizontalHeaderLabels(headers)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setMinimumHeight(300)
        self.history_table.itemSelectionChanged.connect(self._update_action_state)
        layout.addWidget(boxed("Session events (newest first)", self.history_table))

        actions = QHBoxLayout()
        self.acknowledge_button = QPushButton("Acknowledge selected locally")
        self.acknowledge_button.setObjectName("faultHistoryAcknowledgeButton")
        self.acknowledge_button.clicked.connect(self._acknowledge_selected)
        actions.addWidget(self.acknowledge_button)
        self.unacknowledge_button = QPushButton("Mark selected unacknowledged")
        self.unacknowledge_button.setObjectName("faultHistoryUnacknowledgeButton")
        self.unacknowledge_button.clicked.connect(self._unacknowledge_selected)
        actions.addWidget(self.unacknowledge_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.action_notice = self._detail_label("faultHistoryActionNotice")
        self.action_notice.setText(
            "No clear/delete/apply control is provided. Acknowledging an active event never makes the robot READY."
        )
        layout.addWidget(self.action_notice)
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
        self._history = None
        self.snapshot_time_label.setText("snapshot: 未接続")
        self.selected_state_label.setText(f"{self._selected_robot} | SNAPSHOT_UNAVAILABLE")
        self.counts_label.setText("active=0 / total=0 / unacknowledged=0")
        self.boundary_label.setText(
            "retention=SESSION_MEMORY_ONLY / timestamp=UNKNOWN / acknowledgement=LOCAL_VIEW_ONLY"
        )
        self.history_table.setRowCount(0)
        self._update_action_state()

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return
        history = self._history_store.build(robot)
        self._history = history
        self.snapshot_time_label.setText(f"snapshot: {history.snapshot_timestamp_ms} ms")
        binding = "BOUND" if history.configured else "UNBOUND"
        self.selected_state_label.setText(f"{history.robot_id.value} | {binding} | SESSION_HISTORY")
        self.counts_label.setText(
            f"active={history.active_count} / total={len(history.entries)} / "
            f"unacknowledged={history.unacknowledged_count}"
        )
        self.boundary_label.setText(
            f"retention={history.retention_state}\n"
            f"acknowledgement={history.acknowledgement_state}\n"
            "SOURCE timestamp is retained when provided; FIRST_OBSERVED is the GUI snapshot time, not exact event time."
        )
        self._render_entries(history)

    def _render_entries(self, history: FaultHistorySnapshot) -> None:
        selected_event_id = None
        selected_item = self.history_table.item(self.history_table.currentRow(), 0)
        if selected_item is not None:
            selected_event_id = selected_item.data(Qt.ItemDataRole.UserRole)
        self.history_table.setRowCount(len(history.entries))
        selected_row = None
        for row, entry in enumerate(history.entries):
            values = (
                "ACTIVE" if entry.active else "CLEARED",
                _enum_value(entry.severity),
                entry.source,
                entry.node_id or "UNKNOWN",
                entry.reason,
                f"{entry.timestamp_ms} ms ({entry.timestamp_basis})",
                entry.safety_response,
                "ACKNOWLEDGED" if entry.acknowledged else "UNACKNOWLEDGED",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole, entry.event_id)
                self.history_table.setItem(row, column, item)
            if entry.event_id == selected_event_id:
                selected_row = row
        if selected_row is None:
            self.history_table.clearSelection()
        else:
            self.history_table.selectRow(selected_row)
        self._update_action_state()

    def _selected_entry(self):
        row = self.history_table.currentRow()
        if row < 0 or self._history is None:
            return None
        item = self.history_table.item(row, 0)
        event_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return next((entry for entry in self._history.entries if entry.event_id == event_id), None)

    def _update_action_state(self) -> None:
        entry = self._selected_entry()
        self.acknowledge_button.setEnabled(entry is not None and not entry.acknowledged)
        self.unacknowledge_button.setEnabled(entry is not None and entry.acknowledged)

    def _acknowledge_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._history_store.acknowledge(RobotId(self._selected_robot), entry.event_id)
        self._render_selected()

    def _unacknowledge_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._history_store.unacknowledge(RobotId(self._selected_robot), entry.event_id)
        self._render_selected()


def create_fault_history_tab(host: Any) -> FaultHistoryWidget:
    widget = FaultHistoryWidget()
    host.fault_history_widget = widget
    return widget
