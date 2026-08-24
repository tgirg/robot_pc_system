from __future__ import annotations

from PySide6.QtWidgets import QLabel, QHBoxLayout, QLineEdit, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_button, set_monospace


def _log_page(view, clear_slot, copy_slot) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    buttons = QWidget()
    button_layout = QHBoxLayout(buttons)
    button_layout.addWidget(make_button("ログ消去", clear_slot))
    button_layout.addWidget(make_button("クリップボードへコピー", copy_slot))
    button_layout.addStretch(1)
    layout.addWidget(buttons)
    layout.addWidget(view, 1)
    return page


def _esp32_log_page(host) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    controls = QWidget()
    controls_layout = QHBoxLayout(controls)
    search = QLineEdit()
    search.setPlaceholderText("ログ検索 例: STATUS / IMU / LiDAR / MOTOR / DRIVE / FW / ERROR")
    filtered = QPlainTextEdit()
    filtered.setReadOnly(True)
    filtered.setPlaceholderText("検索語を入力すると、ESP32受信ログから一致行だけを表示します。空欄なら下の全ログを見てください。")
    filtered.setMaximumHeight(160)
    set_monospace(filtered)

    def update_filter() -> None:
        keyword = search.text().strip().lower()
        if not keyword:
            filtered.clear()
            return
        lines = [line for line in host.esp32_receive_log.toPlainText().splitlines() if keyword in line.lower()]
        filtered.setPlainText("\n".join(lines) if lines else "一致する行はありません。")

    search.textChanged.connect(update_filter)
    controls_layout.addWidget(search, 1)
    controls_layout.addWidget(make_button("ログ消去", host.clear_visible_logs))
    controls_layout.addWidget(make_button("クリップボードへコピー", host.copy_visible_logs))
    layout.addWidget(controls)
    layout.addWidget(boxed("検索結果", filtered))
    layout.addWidget(boxed("ESP32受信ログ（全文）", host.esp32_receive_log), 1)
    return page


def create_log_tab(host) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(10, 10, 10, 10)
    set_monospace(host.esp32_receive_log)
    tabs = QTabWidget()
    tabs.addTab(_esp32_log_page(host), "ESP32受信ログ")
    tabs.addTab(_log_page(host.log_view, host.clear_visible_logs, host.copy_visible_logs), "操作ログ")
    tabs.addTab(_log_page(host.diagnostics_log_view, host.clear_visible_logs, host.copy_visible_logs), "診断ログ")
    result_page = QWidget()
    result_layout = QVBoxLayout(result_page)
    result_buttons = QWidget()
    result_button_layout = QHBoxLayout(result_buttons)
    result_button_layout.addWidget(make_button("最新結果を開く", host.open_latest_hardware_check_result))
    result_button_layout.addWidget(make_button("結果フォルダを開く", host.open_hardware_check_folder))
    result_button_layout.addWidget(make_button("最新結果をコピー", host.copy_latest_hardware_check_result))
    result_button_layout.addStretch(1)
    result_layout.addWidget(result_buttons)
    host.latest_hardware_result_log_label = QLabel(host.latest_hardware_result_label.text())
    host.latest_hardware_result_log_label.setObjectName("diagnosticLabel")
    host.latest_hardware_result_log_label.setWordWrap(True)
    result_layout.addWidget(boxed("実機確認結果", host.latest_hardware_result_log_label))
    tabs.addTab(result_page, "実機確認結果")
    layout.addWidget(tabs)
    return tab
