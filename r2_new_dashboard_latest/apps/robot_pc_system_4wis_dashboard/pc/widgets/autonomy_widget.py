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

from pc_controller.gui_autonomy_model import AutonomyScreenSnapshot, build_autonomy_screen_snapshot

from .ui_helpers import boxed, make_notice, make_scroll_area, set_section_title


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _text(value: Any, fallback: str = "UNKNOWN") -> str:
    return fallback if value is None else str(value)


class AutonomyWidget(QWidget):
    """Read-only state-machine context with no direct transition controls."""

    robot_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("autonomyWidget")
        self._robots: dict[str, Any] = {}
        self._selected_robot = "R1"
        self._robot_buttons: dict[str, QPushButton] = {}
        self._screen: AutonomyScreenSnapshot | None = None
        self._build_ui()
        self._render_no_snapshot()

    @property
    def selected_robot(self) -> str:
        return self._selected_robot

    @property
    def screen_snapshot(self) -> AutonomyScreenSnapshot | None:
        return self._screen

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

        title = QLabel("Autonomy")
        set_section_title(title)
        layout.addWidget(title)
        layout.addWidget(
            make_notice(
                "READ ONLY STATE MACHINE: immutable snapshotだけを表示します。"
                "GUIはARM・START・STOP・SKIP・FALLBACK・state transitionを要求しません。"
                "HOLD/STOPはexecutor完了ではなくstate-machine request semanticです。"
            )
        )

        selector = QHBoxLayout()
        selector.addWidget(QLabel("表示ロボット:"))
        for robot_id in ("R1", "R2"):
            button = QPushButton(robot_id)
            button.setObjectName(f"autonomySelect{robot_id}Button")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, value=robot_id: self.select_robot(value))
            self._robot_buttons[robot_id] = button
            selector.addWidget(button)
        selector.addStretch(1)
        self.snapshot_time_label = QLabel("snapshot: 未接続")
        selector.addWidget(self.snapshot_time_label)
        layout.addLayout(selector)

        state_grid = QGridLayout()
        self.state_label = self._detail_label("autonomyState")
        self.mission_label = self._detail_label("autonomyMission")
        self.progress_label = self._detail_label("autonomyProgress")
        state_grid.addWidget(boxed("State ID / name / status", self.state_label), 0, 0)
        state_grid.addWidget(boxed("Mission / target", self.mission_label), 0, 1)
        state_grid.addWidget(boxed("Progress / next state", self.progress_label), 0, 2)
        for column in range(3):
            state_grid.setColumnStretch(column, 1)
        layout.addLayout(state_grid)

        policy_grid = QGridLayout()
        self.retry_label = self._detail_label("autonomyRetry")
        self.failure_policy_label = self._detail_label("autonomyFailurePolicy")
        self.reason_label = self._detail_label("autonomyReason")
        policy_grid.addWidget(boxed("Retry / timeout", self.retry_label), 0, 0)
        policy_grid.addWidget(boxed("STOP / SKIP / FALLBACK / HOLD context", self.failure_policy_label), 0, 1)
        policy_grid.addWidget(boxed("Blocked / terminal reason", self.reason_label), 0, 2)
        for column in range(3):
            policy_grid.setColumnStretch(column, 1)
        layout.addLayout(policy_grid)

        self.boundary_label = self._detail_label("autonomyBoundary")
        layout.addWidget(boxed("Authority boundary", self.boundary_label))

        headers = ("Time", "State", "Event", "Step", "Attempt", "Reason")
        self.event_table = QTableWidget(0, len(headers))
        self.event_table.setObjectName("autonomyEventTable")
        self.event_table.setHorizontalHeaderLabels(headers)
        self.event_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.event_table.setAlternatingRowColors(True)
        self.event_table.verticalHeader().setVisible(False)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setMinimumHeight(240)
        layout.addWidget(boxed("Recent state-machine events (snapshot last 20)", self.event_table))
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
        self._screen = None
        self.snapshot_time_label.setText("snapshot: 未接続")
        self.state_label.setText(f"{self._selected_robot} | SNAPSHOT_UNAVAILABLE")
        self.mission_label.setText("mission=UNKNOWN\ncurrent target=UNKNOWN")
        self.progress_label.setText("step=UNKNOWN\nnext state=UNKNOWN")
        self.retry_label.setText("attempt=UNKNOWN\ntimeout=UNKNOWN")
        self.failure_policy_label.setText("policy=UNKNOWN\nHOLD/STOP context=UNKNOWN")
        self.reason_label.setText("blocked reason=UNKNOWN\nterminal reason=UNKNOWN")
        self.boundary_label.setText("READ_ONLY_NO_TRANSITION_OR_EXECUTOR_API")
        self.event_table.setRowCount(0)

    def _render_selected(self) -> None:
        robot = self._robots.get(self._selected_robot)
        if robot is None:
            self._render_no_snapshot()
            return
        screen = build_autonomy_screen_snapshot(robot)
        self._screen = screen
        self.snapshot_time_label.setText(f"snapshot: {screen.snapshot_timestamp_ms} ms")
        binding = "BOUND" if screen.controller_configured else "UNBOUND"
        autonomy_binding = "CONFIGURED" if screen.autonomy_configured else "NOT_CONFIGURED"
        self.state_label.setText(
            f"{screen.robot_id.value} | controller={binding} | autonomy={autonomy_binding}\n"
            f"state ID={screen.state_id}\nstate name={screen.state_name}\nstatus={screen.status}"
        )
        self.mission_label.setText(
            f"mission={_text(screen.mission_id)}\n"
            f"current step={_text(screen.current_step)}\n"
            f"current target={_text(screen.current_target, 'NOT_DEFINED_IN_MISSION_MODEL')}"
        )
        self.progress_label.setText(
            f"step={_text(screen.step_position)}/{_text(screen.step_count)}\n"
            f"next step={_text(screen.next_step, 'NONE')}\n"
            f"next state={screen.next_state}\ncondition={screen.next_state_condition}"
        )
        self.retry_label.setText(
            f"attempt={_text(screen.attempt)} / max retries={_text(screen.max_retries)}\n"
            f"retry delay={_text(screen.retry_delay_ms)} ms\n"
            f"retry deadline={_text(screen.retry_deadline_ms)} ms / remaining={_text(screen.retry_remaining_ms)} ms\n"
            f"step timeout={screen.timeout_state}"
        )
        skipped = ", ".join(screen.skipped_steps) if screen.skipped_steps else "NONE"
        self.failure_policy_label.setText(
            f"on failure={_text(screen.failure_action)}\n"
            f"skipped steps={skipped}\n"
            f"fallback active={_text(screen.active_fallback_id, 'NONE')} / "
            f"configured={_text(screen.configured_fallback_id, 'NONE')}\n"
            f"HOLD request history={screen.hold_context}\n"
            f"STOP request history={screen.stop_context}"
        )
        self.reason_label.setText(
            f"blocked reason={_text(screen.blocked_reason, 'NONE')}\n"
            f"terminal reason={_text(screen.terminal_reason, 'NONE')}"
        )
        self.boundary_label.setText(
            f"control={screen.control_boundary}\n"
            f"executor confirmation={screen.executor_confirmation}\n"
            "No direct action controls are constructed on this screen."
        )
        self._render_events(screen)

    def _render_events(self, screen: AutonomyScreenSnapshot) -> None:
        events = tuple(reversed(screen.recent_events))
        self.event_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (
                f"{event.timestamp_ms} ms",
                event.state,
                event.event,
                event.step_id or "UNKNOWN",
                event.attempt if event.attempt is not None else "UNKNOWN",
                event.reason or "NONE",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.event_table.setItem(row, column, item)


def create_autonomy_tab(host: Any) -> AutonomyWidget:
    widget = AutonomyWidget()
    host.autonomy_widget = widget
    return widget
