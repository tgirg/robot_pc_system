from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget


_BUSY_TEXT_PROPERTY = "_r2_original_text"
_WAIT_CURSOR_COUNT = 0


def set_busy(widget_or_button: QWidget, text: str | None = None, wait_cursor: bool = True) -> None:
    if isinstance(widget_or_button, QPushButton):
        if widget_or_button.property(_BUSY_TEXT_PROPERTY) is None:
            widget_or_button.setProperty(_BUSY_TEXT_PROPERTY, widget_or_button.text())
        if text:
            widget_or_button.setText(text)
        widget_or_button.setEnabled(False)
    if wait_cursor:
        push_wait_cursor()


def clear_busy(widget_or_button: QWidget, text: str | None = None, wait_cursor: bool = True) -> None:
    if isinstance(widget_or_button, QPushButton):
        original = widget_or_button.property(_BUSY_TEXT_PROPERTY)
        widget_or_button.setText(text or original or widget_or_button.text())
        widget_or_button.setProperty(_BUSY_TEXT_PROPERTY, None)
        widget_or_button.setEnabled(True)
    if wait_cursor:
        pop_wait_cursor()


def show_success(label: QLabel, message: str) -> None:
    _set_label(label, f"状態: {message}", "#86efac")


def show_error(label: QLabel, message: str) -> None:
    _set_label(label, f"状態: {message}", "#fca5a5")


def show_info(label: QLabel, message: str) -> None:
    _set_label(label, f"状態: {message}", "#dbeafe")


def append_operation_log(target: Any, message: str) -> None:
    if hasattr(target, "append_log"):
        target.append_log(message)
    elif hasattr(target, "_log"):
        target._log(message)


def format_elapsed_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60.0:
        return f"{seconds:.1f}秒"
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes}分{rest:.0f}秒"


def push_wait_cursor() -> None:
    global _WAIT_CURSOR_COUNT
    if _WAIT_CURSOR_COUNT == 0:
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    _WAIT_CURSOR_COUNT += 1


def pop_wait_cursor() -> None:
    global _WAIT_CURSOR_COUNT
    if _WAIT_CURSOR_COUNT <= 0:
        return
    _WAIT_CURSOR_COUNT -= 1
    if _WAIT_CURSOR_COUNT == 0:
        QApplication.restoreOverrideCursor()


def _set_label(label: QLabel, text: str, color: str) -> None:
    label.setText(text)
    label.setStyleSheet(f"color:{color}; font-weight:700;")


def timestamped(message: str) -> str:
    return f"{time.strftime('%H:%M:%S')} {message}"
