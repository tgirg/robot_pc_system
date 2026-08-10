from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .motor_status_widget import create_motor_status_panel
from .ui_helpers import boxed, make_notice


def create_drive_tab(host) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(10, 10, 10, 10)
    host.drive_status_label = QLabel("現在指令: -\n左速度指令: -\n右速度指令: -")
    host.drive_status_label.setObjectName("diagnosticLabel")
    layout.addWidget(make_notice("現在は安全ダミーモードです。モータ出力: 無効 / IMU: ダミー / LiDAR: ダミー"))
    layout.addWidget(make_notice("走行操作は必ずPC側の安全レイヤを通ります。シミュレーションモードではESP32へ通常走行指令を送りません。"))
    layout.addWidget(boxed("現在指令", host.drive_status_label))
    layout.addWidget(host.control_panel)
    layout.addWidget(create_motor_status_panel(host))
    layout.addWidget(host.actuator_panel)
    layout.addStretch(1)
    return tab
