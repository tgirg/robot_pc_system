from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from .arduino_upload_widget import create_arduino_upload_panel
from .esp32_connection_widget import create_esp32_connection_panel
from .firmware_editor_widget import create_firmware_editor_panel
from .ui_helpers import boxed, make_button


def create_diagnostics_tab(host) -> QWidget:
    tab = QWidget()
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)

    layout.addWidget(create_esp32_connection_panel(host))
    layout.addWidget(create_firmware_editor_panel(host))
    tool_nav = QWidget()
    tool_nav_layout = QHBoxLayout(tool_nav)
    tool_nav_layout.addWidget(make_button("書き込みタブを開く", lambda: host.switch_to_tab("書き込み")))
    tool_nav_layout.addWidget(make_button("シリアルタブを開く", lambda: host.switch_to_tab("シリアル")))
    tool_nav_layout.addStretch(1)
    layout.addWidget(boxed("開発ツール", tool_nav))
    layout.addWidget(create_arduino_upload_panel(host))

    buttons = QWidget()
    button_layout = QHBoxLayout(buttons)
    for text, mode in [
        ("環境診断を実行", "environment"),
        ("COMポート確認", "serial"),
        ("カメラ確認", "camera"),
        ("全診断を実行", "all"),
    ]:
        button_layout.addWidget(make_button(text, lambda checked=False, m=mode: host._run_diagnostics(m)))
    button_layout.addStretch(1)
    layout.addWidget(boxed("診断操作", buttons))
    host.diagnostics_result_view.setPlainText(
        "診断ボタンを押すと結果を表示します。\n"
        "結果欄は選択してコピーできます。"
    )
    layout.addWidget(boxed("診断結果", host.diagnostics_result_view), 1)

    scroll.setWidget(content)
    outer.addWidget(scroll)
    return tab
