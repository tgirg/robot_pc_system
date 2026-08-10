from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class ControlPanel(QWidget):
    command_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        drive_box = QGroupBox("走行操作")
        drive_layout = QHBoxLayout(drive_box)
        drive_layout.setContentsMargins(10, 14, 10, 10)
        for text, command in [
            ("前進", "DRIVE VEL 100 100"),
            ("停止", "DRIVE STOP"),
            ("左旋回", "DRIVE VEL -80 80"),
            ("右旋回", "DRIVE VEL 80 -80"),
            ("緊急停止", "EMERGENCY_STOP"),
        ]:
            button = QPushButton(text)
            button.setMinimumHeight(48)
            button.setToolTip(self._tooltip(command))
            button.clicked.connect(lambda checked=False, cmd=command: self.command_requested.emit(cmd))
            if command == "EMERGENCY_STOP":
                button.setObjectName("emergencyButton")
                button.setMinimumWidth(160)
            drive_layout.addWidget(button)
        layout.addWidget(drive_box)

    def _tooltip(self, command: str) -> str:
        tooltips = {
            "DRIVE VEL 100 100": "PCから左右速度を指定して前進します。",
            "DRIVE STOP": "走行出力を停止します。",
            "DRIVE VEL -80 80": "左を後退、右を前進にして左旋回します。",
            "DRIVE VEL 80 -80": "左を前進、右を後退にして右旋回します。",
            "EMERGENCY_STOP": "モータ出力をすぐ停止します。Escキーでも実行できます。",
        }
        return tooltips.get(command, "")


class ActuatorPanel(QWidget):
    command_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        arm_box = QGroupBox("作業機構 / アクチュエータ")
        arm_layout = QHBoxLayout(arm_box)
        for text, command in [
            ("アーム上げ", "ARM UP 50"),
            ("アーム下げ", "ARM DOWN 50"),
            ("アーム停止", "ARM STOP"),
            ("ツール開", "TOOL OPEN"),
            ("ツール閉", "TOOL CLOSE"),
            ("ポンプON", "TOOL PUMP_ON"),
            ("ポンプOFF", "TOOL PUMP_OFF"),
        ]:
            button = QPushButton(text)
            button.setEnabled(False)
            button.setToolTip(f"将来の指令 {command} 用です。現在は準備中です。")
            arm_layout.addWidget(button)

        layout.addWidget(arm_box)
        layout.addStretch(1)
