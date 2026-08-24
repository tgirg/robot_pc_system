from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)


_previous_qt_message_handler: Any = None
_qt_message_filter_installed = False
_wheel_guard: QObject | None = None


class _WheelGuard(QObject):
    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox, QTabBar)):
            return True
        return super().eventFilter(obj, event)


def safe_font_size(value: object, default: int = 10) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return default
    return size if size > 0 else default


def make_font(family: str = "Yu Gothic UI", point_size: object = 10) -> QFont:
    font = QFont(family)
    font.setPointSize(safe_font_size(point_size))
    return font


def install_qt_font_warning_filter() -> None:
    global _previous_qt_message_handler, _qt_message_filter_installed
    if _qt_message_filter_installed:
        return

    _previous_qt_message_handler = qInstallMessageHandler(_qt_message_handler)
    _qt_message_filter_installed = True


def install_input_wheel_guard(app: QApplication) -> None:
    global _wheel_guard
    if _wheel_guard is not None:
        return
    _wheel_guard = _WheelGuard(app)
    app.installEventFilter(_wheel_guard)


def _qt_message_handler(mode: QtMsgType, context, message: str) -> None:
    if message.startswith("QFont::setPointSize: Point size <= 0"):
        return
    if _previous_qt_message_handler is not None:
        _previous_qt_message_handler(mode, context, message)
        return
    print(message, file=sys.stderr)


def boxed(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(8, 14, 8, 8)
    layout.addWidget(widget)
    return box


def create_card(title: str, status: str = "-", value: str = "-", detail: str = "") -> QGroupBox:
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    status_label = QLabel(status)
    status_label.setObjectName("cardStatus")
    status_label.setWordWrap(True)
    value_label = QLabel(value)
    value_label.setObjectName("cardValue")
    value_label.setWordWrap(True)
    detail_label = QLabel(detail)
    detail_label.setObjectName("cardDetail")
    detail_label.setWordWrap(True)
    layout.addWidget(status_label)
    layout.addWidget(value_label)
    layout.addWidget(detail_label)
    return boxed(title, body)


def apply_card_style(widget: QWidget, importance: str = "normal") -> None:
    widget.setProperty("importance", importance)


def set_large_value_label(label: QLabel) -> None:
    label.setObjectName("largeValue")
    label.setWordWrap(True)


def set_section_title(label: QLabel) -> None:
    label.setObjectName("sectionTitle")
    label.setWordWrap(True)


def make_scroll_area(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    return scroll


def get_screen_size_category() -> str:
    screen = QApplication.primaryScreen()
    if screen is None:
        return "normal"
    width = screen.availableGeometry().width()
    if width < 1280:
        return "small"
    if width >= 1800:
        return "large"
    return "normal"


def make_button(text: str, slot=None, height: int = 44) -> QPushButton:
    button = QPushButton(text)
    button.setMinimumHeight(height)
    if slot is not None:
        button.clicked.connect(slot)
    return button


def make_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    label.setWordWrap(True)
    return label


def make_notice(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("modeNoticeLabel")
    label.setWordWrap(True)
    return label


def make_doc_button(host, title: str, relative_path: str) -> QPushButton:
    path = Path(relative_path)
    button = make_button(title, lambda: host.open_project_file(str(path).replace("\\", "/")))
    button.setToolTip(str(path))
    return button


def add_nav_button(layout: QHBoxLayout, host, text: str, tab_name: str) -> None:
    layout.addWidget(make_button(text, lambda: host.switch_to_tab(tab_name)))


def set_monospace(widget: QWidget) -> None:
    widget.setStyleSheet('font-family: Consolas, "Yu Gothic UI"; font-size: 14px;')


def stretch_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return label
