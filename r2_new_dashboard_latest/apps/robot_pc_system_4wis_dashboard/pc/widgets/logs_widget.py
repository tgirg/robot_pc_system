from __future__ import annotations

from pathlib import Path
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
from pc_controller.gui_logs_model import (
    CompetitionLogSourceSnapshot,
    LogsScreenSnapshot,
    build_logs_screen_snapshot,
    load_competition_log_source,
)

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _text(value: Any, fallback: str = "UNKNOWN") -> str:
    return fallback if value is None else str(value)


class LogsWidget(QWidget):
    """Read-only viewer for one explicitly selected local Competition log."""

    robot_selected = Signal(str)
    source_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logsWidget")
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._source_path: str | Path | None = None
        self._source: CompetitionLogSourceSnapshot = load_competition_log_source(None)
        self._screen: LogsScreenSnapshot | None = None
        self._build_ui()
        self._render_selected()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def screen_snapshot(self) -> LogsScreenSnapshot | None:
        return self._screen

    @property
    def source_snapshot(self) -> CompetitionLogSourceSnapshot:
        return self._source

    def set_competition_log_path(self, log_path: str | Path | None) -> None:
        """Bind one explicit path; no directory scanning or write occurs."""
        self._source_path = log_path
        self._source = load_competition_log_source(log_path)
        self.reload_button.setEnabled(log_path is not None)
        self._render_selected()
        self.source_changed.emit(self._source)

    def reload_competition_log(self) -> None:
        """Re-read only the currently bound local path."""
        self._source = load_competition_log_source(self._source_path)
        self._render_selected()
        self.source_changed.emit(self._source)

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

        title = QLabel("Logs")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "READ ONLY LOCAL LOG: 明示指定されたCompetition JSONLだけを検証・表示します。"
                "自動探索・Serial・ARM・Competition操作・remote転送・削除は行いません。"
                "記録されていないSafety/fault/retry/node値はUNKNOWNです。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット: "))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"logsSelect{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        self.reload_button = QPushButton("Reload explicit local log")
        self.reload_button.setObjectName("logsReloadButton")
        self.reload_button.setEnabled(False)
        self.reload_button.clicked.connect(self.reload_competition_log)
        selector.addWidget(self.reload_button)
        layout.addLayout(selector)

        summary_grid = QGridLayout()
        self.source_label = self._detail_label("logsSource")
        self.session_label = self._detail_label("logsSession")
        self.boundary_label = self._detail_label("logsBoundary")
        summary_grid.addWidget(boxed("Local source / validation", self.source_label), 0, 0)
        summary_grid.addWidget(boxed("Session / records", self.session_label), 0, 1)
        summary_grid.addWidget(boxed("Authority / remote boundary", self.boundary_label), 0, 2)
        for column in range(3):
            summary_grid.setColumnStretch(column, 1)
        layout.addLayout(summary_grid)

        headers = (
            "Seq",
            "Time",
            "Scope",
            "State transition",
            "Competition event",
            "Autonomy",
            "Safety / armed",
            "Fault",
            "Retry",
            "Node",
            "Reason",
            "Data",
        )
        self.event_table = QTableWidget(0, len(headers))
        self.event_table.setObjectName("competitionLogsEventTable")
        self.event_table.setHorizontalHeaderLabels(headers)
        self.event_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.event_table.setAlternatingRowColors(True)
        self.event_table.verticalHeader().setVisible(False)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setMinimumHeight(350)
        layout.addWidget(boxed("Validated Competition events (fleet + selected robot, newest 200)", self.event_table))
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

    def _render_selected(self) -> None:
        screen = build_logs_screen_snapshot(self._source, RobotId(self._selected_robot))
        self._screen = screen
        for value, button in self._robot_buttons.items():
            button.setChecked(value == self._selected_robot)
        self.source_label.setText(
            f"status={screen.source_status}\n"
            f"kind={screen.source_kind}\n"
            f"path={_text(screen.source_path, 'NOT_CONFIGURED')}\n"
            f"validation={screen.validation_state}\n{screen.validation_message}"
        )
        self.session_label.setText(
            f"robot filter={screen.robot_id.value} + FLEET\n"
            f"session={_text(screen.session_id)}\n"
            f"records total/retained={screen.total_record_count}/{screen.retained_record_count}\n"
            f"matching/displayed={screen.matching_record_count}/{screen.displayed_record_count}\n"
            f"source truncated={screen.truncated_record_count} / display hidden={screen.hidden_matching_record_count}\n"
            f"time={_text(screen.first_timestamp_ms)}..{_text(screen.last_timestamp_ms)} ms\n"
            f"final state={_text(screen.final_competition_state)} / finalized={screen.finalized}"
        )
        self.boundary_label.setText(
            "control=READ_ONLY_NO_COMPETITION_OR_CONTROLLER_API\n"
            f"remote sync={screen.remote_sync_status}\n"
            f"remote transfer performed={screen.remote_transfer_performed}\n"
            "Fault History/session events are not merged into this persistent log."
        )
        self._render_events(screen)

    def _render_events(self, screen: LogsScreenSnapshot) -> None:
        entries = tuple(reversed(screen.entries))
        self.event_table.setRowCount(len(entries))
        for row, event in enumerate(entries):
            values = (
                event.sequence,
                f"{event.timestamp_ms} ms",
                event.scope,
                event.state_transition,
                f"{event.event}\nstate={event.competition_state}",
                event.autonomy_state,
                f"{event.safety_state}\n{event.armed_state}",
                event.fault_context,
                event.retry_context,
                event.node_context,
                event.reason,
                event.data_summary,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.event_table.setItem(row, column, item)


def create_logs_tab(host: Any) -> LogsWidget:
    widget = LogsWidget()
    host.logs_widget = widget
    return widget
