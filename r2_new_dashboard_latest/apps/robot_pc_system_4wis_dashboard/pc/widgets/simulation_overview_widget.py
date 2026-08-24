from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .ui_helpers import set_section_title


def create_simulation_tab(host) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)
    title = QLabel("シミュレーション")
    set_section_title(title)
    layout.addWidget(title)
    top = QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(host._box("仮想フィールド", host.map_widget), 4)
    side = QVBoxLayout()
    side.setSpacing(10)
    side.addWidget(host._simulation_controls_box())
    side.addWidget(host._auto_drive_box())
    side.addWidget(host._box("シミュレーション状態", host.simulation_status_label), 1)
    top.addLayout(side, 2)
    layout.addLayout(top, 1)
    layout.addWidget(host.simulation_control_panel, 0)
    return tab
