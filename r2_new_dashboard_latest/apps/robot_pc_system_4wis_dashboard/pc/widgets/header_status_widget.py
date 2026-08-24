from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QWidget

from .ui_helpers import make_button


def create_header_status_widget(host) -> QGroupBox:
    box = QGroupBox("現在のモード / 安全状態 / ESP32接続 / 現在の指令")
    layout = QGridLayout(box)
    layout.addWidget(host.mode_label, 0, 0)
    layout.addWidget(host.safety_label, 0, 1)
    layout.addWidget(host.header_esp32_label, 0, 2)
    layout.addWidget(host.command_label, 0, 3)
    layout.addWidget(host.display_mode_label, 0, 4)

    actions = QWidget()
    action_layout = QHBoxLayout(actions)
    action_layout.setContentsMargins(0, 0, 0, 0)
    action_layout.setSpacing(6)
    action_layout.addWidget(make_button("全画面表示", host.enter_fullscreen, 38))
    action_layout.addWidget(make_button("通常表示に戻す", host.exit_fullscreen, 38))
    action_layout.addWidget(host.header_emergency_button)
    layout.addWidget(actions, 0, 5)

    layout.addWidget(host.mode_detail_label, 1, 0, 1, 6)
    layout.addWidget(host.mode_notice_label, 2, 0, 1, 6)
    layout.addWidget(host.global_notification_label, 3, 0, 1, 6)
    for column in range(4):
        layout.setColumnStretch(column, 1)
    layout.setColumnStretch(4, 0)
    layout.setColumnStretch(5, 0)
    box.setToolTip("Mockモードでは実機なしで動作確認できます。緊急停止はEscキーでも実行できます。")
    return box
