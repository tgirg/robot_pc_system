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
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.autonomy import RobotId
from pc_controller.gui_logs_model import CompetitionLogSourceSnapshot, load_competition_log_source
from pc_controller.gui_replay_model import ReplayCursorStore, ReplayScreenSnapshot

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _text(value: Any, fallback: str = "UNKNOWN") -> str:
    return fallback if value is None else str(value)


class ReplayWidget(QWidget):
    """Manual offline cursor over inert, validated Competition log records."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("replayWidget")
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._store = ReplayCursorStore(load_competition_log_source(None))
        self._screen: ReplayScreenSnapshot | None = None
        self._rendering = False
        self._build_ui()
        self._render_selected()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def screen_snapshot(self) -> ReplayScreenSnapshot | None:
        return self._screen

    def set_log_source(self, source: CompetitionLogSourceSnapshot) -> None:
        """Replace only the immutable local source; never execute its contents."""
        self._store.set_source(source)
        self._render_selected()

    def set_fleet_snapshot(self, fleet: Any) -> None:
        selected = _enum_value(getattr(fleet, "selected_robot", ""))
        if selected not in {"R1", "R2"}:
            raise ValueError("fleet selected_robot must be R1 or R2")
        if selected != self._selected_robot:
            self.select_robot(selected, emit=False)

    def select_robot(self, robot_id: str, *, emit: bool = True) -> None:
        if robot_id not in {"R1", "R2"}:
            raise ValueError("robot_id must be R1 or R2")
        self._selected_robot = robot_id
        self._render_selected()
        if emit:
            self.robot_selected.emit(robot_id)

    def _build_ui(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("Replay")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "OFFLINE VISUALIZATION ONLY: validated Competition JSONLのrecordを"
                "local cursorで確認します。recorded action/commandは再送・実行しません。"
                "ARM・Controller・Autonomy executor・state mutation・remote転送APIはありません。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット: "))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"replaySelect{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        layout.addLayout(selector)

        summary_grid = QGridLayout()
        self.source_label = self._detail_label("replaySource")
        self.cursor_label = self._detail_label("replayCursor")
        self.recorded_state_label = self._detail_label("replayRecordedState")
        summary_grid.addWidget(boxed("Validated source", self.source_label), 0, 0)
        summary_grid.addWidget(boxed("Local replay cursor", self.cursor_label), 0, 1)
        summary_grid.addWidget(boxed("Robot state last recorded by log", self.recorded_state_label), 0, 2)
        for column in range(3):
            summary_grid.setColumnStretch(column, 1)
        layout.addLayout(summary_grid)

        controls = QHBoxLayout()
        self.first_button = self._cursor_button("First", "replayFirstButton", self._first)
        self.previous_button = self._cursor_button("Previous", "replayPreviousButton", self._previous)
        self.next_button = self._cursor_button("Next", "replayNextButton", self._next)
        self.last_button = self._cursor_button("Last", "replayLastButton", self._last)
        controls.addWidget(self.first_button)
        controls.addWidget(self.previous_button)
        self.cursor_slider = QSlider(Qt.Orientation.Horizontal)
        self.cursor_slider.setObjectName("replayCursorSlider")
        self.cursor_slider.setMinimum(0)
        self.cursor_slider.setMaximum(0)
        self.cursor_slider.valueChanged.connect(self._select_index)
        controls.addWidget(self.cursor_slider, 1)
        controls.addWidget(self.next_button)
        controls.addWidget(self.last_button)
        layout.addLayout(controls)

        event_grid = QGridLayout()
        self.event_label = self._detail_label("replayCurrentEvent")
        self.context_label = self._detail_label("replayCurrentContext")
        self.boundary_label = self._detail_label("replayBoundary")
        event_grid.addWidget(boxed("Current recorded event", self.event_label), 0, 0)
        event_grid.addWidget(boxed("Current event context", self.context_label), 0, 1)
        event_grid.addWidget(boxed("Authority boundary", self.boundary_label), 0, 2)
        for column in range(3):
            event_grid.setColumnStretch(column, 1)
        layout.addLayout(event_grid)

        headers = (
            "Seq",
            "Time",
            "Scope",
            "Competition state",
            "Event",
            "Autonomy recorded",
            "Safety / arm recorded",
            "Reason",
        )
        self.timeline_table = QTableWidget(0, len(headers))
        self.timeline_table.setObjectName("replayTimelineTable")
        self.timeline_table.setHorizontalHeaderLabels(headers)
        self.timeline_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.timeline_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.timeline_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.timeline_table.setAlternatingRowColors(True)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        self.timeline_table.setMinimumHeight(330)
        self.timeline_table.cellClicked.connect(self._select_table_row)
        layout.addWidget(boxed("Retained robot + fleet timeline (manual local cursor)", self.timeline_table))
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
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    @staticmethod
    def _cursor_button(text: str, object_name: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.clicked.connect(slot)
        return button

    def _robot_id(self) -> RobotId:
        return RobotId(self._selected_robot)

    def _first(self) -> None:
        self._store.first(self._robot_id())
        self._render_selected()

    def _previous(self) -> None:
        self._store.move(self._robot_id(), -1)
        self._render_selected()

    def _next(self) -> None:
        self._store.move(self._robot_id(), 1)
        self._render_selected()

    def _last(self) -> None:
        self._store.last(self._robot_id())
        self._render_selected()

    def _select_index(self, index: int) -> None:
        if self._rendering or self._screen is None:
            return
        timeline = self._screen.timeline
        if 0 <= index < len(timeline):
            self._store.select_sequence(self._robot_id(), timeline[index].sequence)
            self._render_selected()

    def _select_table_row(self, row: int, column: int) -> None:
        del column
        if self._rendering or self._screen is None:
            return
        if 0 <= row < len(self._screen.timeline):
            self._store.select_sequence(self._robot_id(), self._screen.timeline[row].sequence)
            self._render_selected()

    def _render_selected(self) -> None:
        self._rendering = True
        try:
            screen = self._store.snapshot(self._robot_id())
            self._screen = screen
            for value, button in self._robot_buttons.items():
                button.setChecked(value == self._selected_robot)
            self.source_label.setText(
                f"availability={screen.availability}\n"
                f"status={screen.source_status}\n"
                f"session={_text(screen.session_id)}\n"
                f"path={_text(screen.source_path, 'NOT_CONFIGURED')}\n"
                f"validation={screen.validation_state}\n{screen.validation_message}"
            )
            self.cursor_label.setText(
                f"position={_text(screen.cursor_position)}/{screen.timeline_count}\n"
                f"sequence={_text(screen.current_sequence)}\n"
                f"timestamp={_text(screen.current_timestamp_ms)} ms\n"
                f"elapsed from recorded session start={_text(screen.elapsed_from_session_start_ms)} ms\n"
                f"retained sequence={_text(screen.retained_first_sequence)}..{_text(screen.retained_last_sequence)}\n"
                f"prefix truncated={screen.prefix_truncated} ({screen.truncated_record_count} records)"
            )
            self.recorded_state_label.setText(
                f"robot={screen.robot_id.value}\n"
                f"Autonomy={screen.autonomy_state}\n  basis={screen.autonomy_basis}\n"
                f"Safety={screen.safety_state}\n  basis={screen.safety_basis}\n"
                f"armed={screen.armed_state}\n  basis={screen.armed_basis}"
            )
            self.event_label.setText(
                f"scope={screen.current_scope}\n"
                f"Competition state={screen.competition_state}\n"
                f"transition={screen.state_transition}\n"
                f"event={screen.competition_event}\n"
                f"reason={screen.reason}"
            )
            self.context_label.setText(
                f"fault={screen.fault_context}\n"
                f"retry={screen.retry_context}\n"
                f"node={screen.node_context}\n"
                f"recorded data={screen.data_summary}"
            )
            self.boundary_label.setText(
                f"control={screen.control_boundary}\n"
                "Recorded actions are inert labels, not executable commands.\n"
                f"remote sync={screen.remote_sync_status}\n"
                f"remote transfer performed={screen.remote_transfer_performed}"
            )
            self._render_timeline(screen)
            self._render_controls(screen)
        finally:
            self._rendering = False

    def _render_controls(self, screen: ReplayScreenSnapshot) -> None:
        count = len(screen.timeline)
        index = screen.cursor_index or 0
        enabled = count > 0
        self.cursor_slider.setEnabled(enabled)
        self.cursor_slider.setMaximum(max(0, count - 1))
        self.cursor_slider.setValue(index)
        self.first_button.setEnabled(enabled and index > 0)
        self.previous_button.setEnabled(enabled and index > 0)
        self.next_button.setEnabled(enabled and index < count - 1)
        self.last_button.setEnabled(enabled and index < count - 1)

    def _render_timeline(self, screen: ReplayScreenSnapshot) -> None:
        self.timeline_table.setRowCount(len(screen.timeline))
        for row, event in enumerate(screen.timeline):
            values = (
                event.sequence,
                f"{event.timestamp_ms} ms",
                event.scope,
                event.competition_state,
                event.event,
                event.autonomy_state,
                f"{event.safety_state} / {event.armed_state}",
                event.reason,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.timeline_table.setItem(row, column, item)
        if screen.cursor_index is not None:
            self.timeline_table.selectRow(screen.cursor_index)
            item = self.timeline_table.item(screen.cursor_index, 0)
            if item is not None:
                self.timeline_table.scrollToItem(item)


def create_replay_tab(host: Any) -> ReplayWidget:
    widget = ReplayWidget()
    host.replay_widget = widget
    return widget
