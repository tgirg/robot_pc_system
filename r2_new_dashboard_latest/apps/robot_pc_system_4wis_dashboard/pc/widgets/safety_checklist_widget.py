from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_button, make_notice


def create_safety_checklist_panel(host) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(make_notice("実モータ出力を有効にする前に、必ず全項目を確認してください。"))
    grid = QGridLayout()
    items = [
        "モータ出力が無効である",
        "ESP32通信が成功している",
        "STOP送信が成功している",
        "GND共通を確認した",
        "電源電圧を確認した",
        "LiDAR電圧を確認した",
        "IMU電圧を確認した",
        "モータドライバ型番を確認した",
        "配線写真を保存した",
        "モータを浮かせた状態で試験する",
    ]
    host.safety_checkboxes = []
    for index, text in enumerate(items):
        checkbox = QCheckBox(text)
        checkbox.setObjectName("diagnosticLabel")
        host.safety_checkboxes.append(checkbox)
        grid.addWidget(checkbox, index // 2, index % 2)
    layout.addLayout(grid)
    layout.addWidget(make_button("チェックをリセット", host.reset_real_hardware_safety_checks))
    return boxed("実機接続前チェックリスト", box)
