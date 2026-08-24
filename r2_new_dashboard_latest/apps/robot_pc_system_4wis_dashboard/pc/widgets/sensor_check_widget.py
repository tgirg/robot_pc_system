from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pc_controller.custom_board_sensor_inventory import R2_SENSOR_CHECK_ORDER

from .ui_helpers import boxed, make_notice, set_section_title


CONNECTED_COLOR = QColor("#1d4ed8")
DISCONNECTED_COLOR = QColor("#dc2626")


class SensorCheckWidget(QWidget):
    connect_requested = Signal(str)
    port_refresh_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sensorCheckWidget")
        self._readings: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self.update_readings({})

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("R2 センサチェック")
        set_section_title(title)
        header.addWidget(title)
        header.addStretch(1)
        self.summary_label = QLabel("更新: 未実行")
        self.summary_label.setObjectName("sensorCheckSummary")
        header.addWidget(self.summary_label)
        header.addWidget(QLabel("COM:"))
        self.port_combo = QComboBox()
        self.port_combo.setObjectName("sensorCheckPortCombo")
        self.port_combo.setMinimumWidth(130)
        header.addWidget(self.port_combo)
        self.port_refresh_button = QPushButton("COM更新")
        self.port_refresh_button.setObjectName("sensorCheckPortRefreshButton")
        self.port_refresh_button.setFixedHeight(32)
        self.port_refresh_button.clicked.connect(lambda _checked=False: self.port_refresh_requested.emit())
        header.addWidget(self.port_refresh_button)
        self.connect_button = QPushButton("ESP接続")
        self.connect_button.setObjectName("sensorCheckEspConnectButton")
        self.connect_button.setFixedHeight(32)
        self.connect_button.clicked.connect(lambda _checked=False: self.connect_requested.emit(self.selected_port()))
        header.addWidget(self.connect_button)
        self.refresh_button = QPushButton("更新")
        self.refresh_button.setObjectName("sensorCheckRefreshButton")
        self.refresh_button.setFixedHeight(32)
        self.refresh_button.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        layout.addWidget(
            make_notice(
                "青=接続データ受信あり / 赤=未接続。ESP接続でCOMを開き、更新で受信済みセンサ情報を再読み込みします。"
            )
        )

        self.esp_status_label = QLabel("ESP32: 未接続")
        self.esp_status_label.setObjectName("sensorCheckEspStatus")
        self.esp_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.esp_status_label.setMinimumHeight(34)
        layout.addWidget(self.esp_status_label)

        headers = ("センサ", "GPIO", "用途", "接続", "値", "単位", "注意")
        self.table = QTableWidget(len(R2_SENSOR_CHECK_ORDER), len(headers))
        self.table.setObjectName("sensorCheckTable")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        height = self.table.horizontalHeader().height() + len(R2_SENSOR_CHECK_ORDER) * 26 + 8
        self.table.setMinimumHeight(height)
        self.table.setMaximumHeight(height)
        layout.addWidget(boxed("接続確認一覧", self.table))
        layout.addStretch(1)

    def update_readings(
        self,
        readings: dict[str, dict[str, Any]],
        *,
        summary: str = "",
        esp_connected: bool = False,
        esp_detail: str = "",
    ) -> None:
        self._readings = {str(key).upper(): dict(value) for key, value in readings.items()}
        self._set_esp_status(esp_connected, esp_detail)
        connected_count = 0
        for row, sensor in enumerate(R2_SENSOR_CHECK_ORDER):
            reading = self._readings.get(sensor.name, {})
            connected = bool(reading.get("connected", False))
            if connected:
                connected_count += 1
            value = str(reading.get("value", "未受信"))
            unit = str(reading.get("unit", sensor.unit))
            note = str(reading.get("note", sensor.note))
            values = (
                sensor.name,
                sensor.gpio_label,
                sensor.purpose,
                "接続" if connected else "未接続",
                value,
                unit,
                note,
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 3:
                    item.setForeground(CONNECTED_COLOR if connected else DISCONNECTED_COLOR)
                self.table.setItem(row, column, item)
        self.summary_label.setText(summary or f"接続 {connected_count}/{len(R2_SENSOR_CHECK_ORDER)}")

    def selected_port(self) -> str:
        text = self.port_combo.currentText().strip()
        return text.split()[0].strip() if text else ""

    def set_ports(self, ports: list[str], *, selected: str = "") -> None:
        current = selected or self.selected_port()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        for port in ports:
            self.port_combo.addItem(port)
        if current:
            index = self.port_combo.findText(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            elif ports:
                self.port_combo.setCurrentIndex(0)
        self.port_combo.blockSignals(False)

    def _set_esp_status(self, connected: bool, detail: str) -> None:
        state = "接続" if connected else "未接続"
        color = "#1d4ed8" if connected else "#dc2626"
        background = "#eff6ff" if connected else "#fef2f2"
        border = "#93c5fd" if connected else "#fecaca"
        text = f"ESP32: {state}"
        if detail:
            text += f" / {detail}"
        self.esp_status_label.setText(text)
        self.esp_status_label.setStyleSheet(
            f"color:{color}; background:{background}; border:1px solid {border}; "
            "font-weight:800; padding:6px;"
        )


def create_sensor_check_tab(host: Any) -> SensorCheckWidget:
    widget = SensorCheckWidget()
    widget.connect_requested.connect(host.connect_sensor_check_esp)
    widget.port_refresh_requested.connect(host.refresh_sensor_check_ports)
    widget.refresh_requested.connect(host.refresh_sensor_check_info)
    host.sensor_check_widget = widget
    host.refresh_sensor_check_ports(notify=False)
    return widget
