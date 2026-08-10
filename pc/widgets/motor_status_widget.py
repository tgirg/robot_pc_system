from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_notice


def create_motor_status_panel(host) -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    host.motor_status_label = QLabel("モータ出力：無効（安全ダミー）\n左指令: -\n右指令: -\nMOTOR_DUMMY: 未受信")
    host.motor_status_label.setObjectName("diagnosticLabel")
    layout.addWidget(make_notice("MOTOR_OUTPUT_ENABLED は既定で 0 です。実PWM出力は行いません。"))
    layout.addWidget(host.motor_status_label)
    return boxed("モータ出力状態", panel)
