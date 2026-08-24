from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


PALETTE = {
    "void": "#050706",
    "surface": "#0a100c",
    "panel": "#0d1710",
    "panel_alt": "#111c13",
    "grid": "#203827",
    "green": "#b7ff35",
    "green_dim": "#6c9f2f",
    "orange": "#ff8a1f",
    "yellow": "#ffe14a",
    "red": "#ff3b30",
    "text": "#e7f4d7",
    "muted": "#83937e",
}


def command_center_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget {{
        background:{PALETTE['void']}; color:{PALETTE['text']};
        font-family:"Yu Gothic UI", "Meiryo UI", Meiryo, sans-serif;
        font-size:13px;
    }}
    QWidget#commandCenterRoot {{ background:{PALETTE['void']}; }}
    QWidget#commandNavRail {{ background:#070c08; border:1px solid {PALETTE['green_dim']}; }}
    QLabel#commandRailTitle {{ color:{PALETTE['orange']}; font-size:19px; font-weight:900; letter-spacing:2px; }}
    QLabel#commandRailCode {{ color:{PALETTE['green_dim']}; font-family:Consolas; font-size:10px; }}
    QPushButton[commandNav="true"] {{
        background:#0a120c; color:{PALETTE['green']}; border:0;
        border-left:4px solid {PALETTE['green_dim']};
        border-right:1px solid #1a2e1e; text-align:left;
        padding:5px 9px; min-height:25px; font-size:11px; font-weight:800;
    }}
    QPushButton[commandNav="true"]:hover {{ background:#152318; border-left-color:{PALETTE['orange']}; color:#ffffff; }}
    QPushButton[commandNav="true"]:checked {{
        background:#24190d; color:{PALETTE['orange']}; border-left:7px solid {PALETTE['orange']};
        border-right:3px solid {PALETTE['yellow']};
    }}
    QTabWidget#commandCenterTabs::pane {{ border:0; background:transparent; }}
    QTabWidget#commandCenterTabs > QTabBar {{ width:0px; height:0px; }}
    QTabWidget::pane {{ border:1px solid {PALETTE['green_dim']}; background:#050806; }}
    QTabBar::tab {{
        background:#0a120c; color:{PALETTE['green']}; border:1px solid #29402e;
        border-bottom:3px solid #29402e; padding:9px 14px; font-weight:800;
    }}
    QTabBar::tab:hover {{ color:#ffffff; border-bottom-color:{PALETTE['yellow']}; }}
    QTabBar::tab:selected {{ background:#24190d; color:{PALETTE['orange']}; border-bottom-color:{PALETTE['orange']}; }}
    QGroupBox {{
        background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0c1710, stop:1 #08100b);
        border:1px solid {PALETTE['green_dim']}; border-left:4px solid {PALETTE['orange']};
        margin-top:13px; padding:11px 9px 8px 9px; font-weight:800;
    }}
    QGroupBox::title {{
        subcontrol-origin:margin; subcontrol-position:top left; left:11px;
        padding:1px 9px; color:{PALETTE['green']}; background:{PALETTE['void']};
    }}
    QPushButton {{
        background:#141c12; color:{PALETTE['orange']}; border:1px solid {PALETTE['orange']};
        border-left:5px solid {PALETTE['orange']}; padding:7px 11px; min-height:26px; font-weight:800;
    }}
    QPushButton:hover {{ background:#31200d; color:#ffffff; }}
    QPushButton:pressed {{ background:{PALETTE['orange']}; color:#000000; }}
    QPushButton:checked {{ background:#2a3513; color:{PALETTE['green']}; border-color:{PALETTE['green']}; }}
    QPushButton:disabled {{ background:#0b0e0b; color:#4c5549; border-color:#283027; }}
    QPushButton#emergencyButton {{ background:#420b08; color:#ffffff; border:2px solid {PALETTE['red']}; font-size:17px; }}
    QPushButton#emergencyButton:hover {{ background:#77110c; }}
    QPushButton[commandRole="preview"] {{ color:{PALETTE['green']}; border-color:{PALETTE['green_dim']}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTableWidget, QListWidget {{
        background:#030604; color:{PALETTE['text']}; border:1px solid #34543b;
        selection-background-color:#5a3610; selection-color:#ffffff;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border:2px solid {PALETTE['yellow']}; }}
    QHeaderView::section {{
        background:#132018; color:{PALETTE['green']}; border:0; border-right:1px solid #34543b;
        border-bottom:2px solid {PALETTE['orange']}; padding:6px; font-weight:900;
    }}
    QTableWidget {{ gridline-color:#1d3424; alternate-background-color:#09110c; }}
    QTableWidget::item {{ padding:4px; }}
    QScrollBar:vertical {{ background:#050806; width:12px; }}
    QScrollBar::handle:vertical {{ background:{PALETTE['green_dim']}; min-height:30px; }}
    QScrollBar:horizontal {{ background:#050806; height:12px; }}
    QScrollBar::handle:horizontal {{ background:{PALETTE['green_dim']}; min-width:30px; }}
    QCheckBox {{ spacing:8px; color:{PALETTE['text']}; }}
    QCheckBox::indicator {{ width:17px; height:17px; border:1px solid {PALETTE['green_dim']}; background:#020402; }}
    QCheckBox::indicator:checked {{ background:{PALETTE['green']}; border:3px solid #17200e; }}
    QSlider::groove:horizontal {{ height:5px; background:#203024; }}
    QSlider::handle:horizontal {{ width:18px; margin:-7px 0; background:{PALETTE['orange']}; border:1px solid {PALETTE['yellow']}; }}
    QLabel#modeNoticeLabel {{ color:{PALETTE['yellow']}; border-left:5px solid {PALETTE['yellow']}; padding:6px; background:#171609; font-weight:900; }}
    QLabel#modeLabel, QLabel#sectionTitle {{ color:{PALETTE['orange']}; font-size:19px; font-weight:900; }}
    QLabel#safetyLabel {{ color:{PALETTE['green']}; font-size:18px; font-weight:900; }}
    QLabel#esp32HeaderLabel, QLabel#commandLabel {{ color:{PALETTE['yellow']}; font-weight:900; }}
    QLabel#cardValue, QLabel#cardStatus, QLabel#largeValue {{ color:{PALETTE['green']}; font-size:20px; font-weight:900; }}
    QLabel#cardLabel, QLabel#cardDetail, QLabel#diagnosticLabel {{ color:#a7b7a1; }}
    QLabel#commandSectionTitle {{ color:{PALETTE['orange']}; font-size:21px; font-weight:900; letter-spacing:2px; }}
    QLabel#soundStatusLabel {{ color:{PALETTE['green']}; border:1px solid {PALETTE['green_dim']}; padding:7px; }}
    QLabel#soundStatusLabel[status="error"] {{ color:{PALETTE['red']}; border-color:{PALETTE['red']}; }}
    QToolTip {{ background:#0b120d; color:{PALETTE['yellow']}; border:1px solid {PALETTE['orange']}; }}
    *:focus {{ outline:1px solid {PALETTE['yellow']}; }}
    """


class CommandCenterHeader(QWidget):
    """Original cut-corner status fascia; it paints data, never controls it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setMaximumHeight(110)
        self.robot_text = "R- / UNBOUND"
        self.state_text = "SAFE / UNKNOWN"
        self.link_text = "LINK -- / TELEMETRY --"
        self.readiness_text = "START READY / NOT CONFIGURED"
        self.severity = "WARNING"

    def set_snapshot(self, robot) -> None:
        robot_id = str(getattr(getattr(robot, "robot_id", ""), "value", getattr(robot, "robot_id", ""))) or "R-"
        connection = str(getattr(getattr(robot, "connection", ""), "value", getattr(robot, "connection", ""))) or "UNKNOWN"
        safety = str(getattr(robot, "safety_state", "UNKNOWN"))
        ready = "READY" if bool(getattr(robot, "ready", False)) else "NOT READY"
        armed = "ARMED" if bool(getattr(robot, "armed", False)) else "DISARMED"
        backend = str(getattr(getattr(robot, "backend", ""), "value", getattr(robot, "backend", ""))) or "UNKNOWN"
        comm_age = getattr(robot, "communication_age_ms", None)
        telemetry_age = getattr(robot, "telemetry_age_ms", None)
        self.robot_text = f"{robot_id} / {connection} / {backend}"
        self.state_text = f"{safety} / {ready} / {armed}"
        self.link_text = f"LINK {comm_age if comm_age is not None else '--'} ms / TELEMETRY {telemetry_age if telemetry_age is not None else '--'} ms"
        competition = str(getattr(robot, "competition_state", "") or "")
        if competition == "READY_DISARMED":
            self.readiness_text = "START READY / WINDOW ACTIVE"
        elif competition == "ARMED_READY":
            self.readiness_text = "START READY / ARMED READY"
        elif competition == "ACTIVE":
            self.readiness_text = "START / RUNNING"
        elif competition == "BLOCKED":
            self.readiness_text = "FAIL / AUTO LOCK"
        else:
            self.readiness_text = "START READY / NOT CONFIGURED"
        self.severity = str(getattr(getattr(robot, "severity", ""), "value", getattr(robot, "severity", "WARNING")))
        self.update()

    def set_readiness_countdown(self, remaining_s: float | None) -> None:
        if remaining_s is not None:
            if remaining_s <= 0.0:
                self.readiness_text = "START READY / 00.0 s / DISPLAY ONLY"
            else:
                self.readiness_text = f"START READY / 残り {remaining_s:04.1f} s"
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        cut = 24.0
        polygon = QPolygonF([
            QPointF(rect.left() + cut, rect.top()),
            QPointF(rect.right() - cut, rect.top()),
            QPointF(rect.right(), rect.top() + cut),
            QPointF(rect.right(), rect.bottom() - cut),
            QPointF(rect.right() - cut, rect.bottom()),
            QPointF(rect.left() + cut, rect.bottom()),
            QPointF(rect.left(), rect.bottom() - cut),
            QPointF(rect.left(), rect.top() + cut),
        ])
        painter.setBrush(QColor("#09110b"))
        painter.setPen(QPen(QColor(PALETTE["orange"]), 3.0))
        painter.drawPolygon(polygon)
        painter.setPen(QPen(QColor("#25452d"), 1.0))
        for x in range(40, self.width(), 64):
            painter.drawLine(x, 10, x - 30, self.height() - 10)
        severity_color = PALETTE["red"] if self.severity == "ERROR" else PALETTE["yellow"] if self.severity == "WARNING" else PALETTE["green"]
        painter.setPen(QColor(PALETTE["orange"]))
        painter.setFont(QFont("Yu Gothic UI", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(28, 11, self.width() * 0.55, 20), Qt.AlignmentFlag.AlignLeft, "F3RC // TACTICAL COMMAND SYSTEM")
        painter.setPen(QColor(PALETTE["green"]))
        painter.setFont(QFont("Yu Gothic UI", 17, QFont.Weight.Black))
        painter.drawText(QRectF(28, 31, self.width() * 0.62, 31), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.robot_text)
        painter.setPen(QColor(severity_color))
        painter.setFont(QFont("Yu Gothic UI", 15, QFont.Weight.Black))
        painter.drawText(QRectF(28, 65, self.width() * 0.55, 27), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.state_text)
        right_x = self.width() * 0.61
        painter.setPen(QColor(PALETTE["muted"]))
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(right_x, 18, self.width() - right_x - 24, 22), Qt.AlignmentFlag.AlignRight, self.link_text)
        painter.setPen(QColor(severity_color))
        painter.setFont(QFont("Yu Gothic UI", 16, QFont.Weight.Black))
        painter.drawText(QRectF(right_x, 48, self.width() - right_x - 24, 38), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.readiness_text)


class CommandNavigationRail(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandNavRail")
        self.setMinimumWidth(176)
        self.setMaximumWidth(232)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(9, 13, 9, 13)
        self.layout.setSpacing(5)
        title = QLabel("OPERATION\nDIRECTIVE")
        title.setObjectName("commandRailTitle")
        code = QLabel("SYS:F3RC-CC\nMODE:LOCAL/OFFLINE\nAUTH:SNAPSHOT")
        code.setObjectName("commandRailCode")
        self.layout.addWidget(title)
        self.layout.addWidget(code)
        self.buttons: list[QPushButton] = []

    def add_destination(self, index: int, code: str, label: str, slot) -> QPushButton:
        button = QPushButton(f"{code}\n{label}")
        button.setCheckable(True)
        button.setProperty("commandNav", True)
        button.clicked.connect(lambda _checked=False, value=index: slot(value))
        self.layout.addWidget(button)
        self.buttons.append(button)
        return button

    def finish(self) -> None:
        self.layout.addStretch(1)

    def select(self, index: int) -> None:
        for button_index, button in enumerate(self.buttons):
            button.setChecked(button_index == index)
