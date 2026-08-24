from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QWidget


class StatusPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.connection_labels: dict[str, QLabel] = {}
        self.source_labels: dict[str, QLabel] = {}

        layout = QGridLayout(self)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.addWidget(QLabel("項目"), 0, 0)
        layout.addWidget(QLabel("接続状態"), 0, 1)
        layout.addWidget(QLabel("データ種別"), 0, 2)

        self.labels = {
            "ESP32": "ESP32",
            "Camera": "カメラ",
            "LSB": "LSB基板",
            "LiDAR": "LiDAR",
            "IMU": "IMU",
            "Optical Odometry": "光学式オドメトリ",
            "Encoder": "エンコーダ",
        }
        for row, (key, text) in enumerate(self.labels.items(), start=1):
            title = QLabel(text)
            title.setToolTip(self._tooltip(key))
            connection = QLabel("未接続")
            source = QLabel("データなし")
            connection.setObjectName("statusValue")
            source.setObjectName("statusValue")
            layout.addWidget(title, row, 0)
            layout.addWidget(connection, row, 1)
            layout.addWidget(source, row, 2)
            self.connection_labels[key] = connection
            self.source_labels[key] = source

    def set_status(self, name: str, connected: bool, source: str) -> None:
        connection_label = self.connection_labels.get(name)
        source_label = self.source_labels.get(name)
        if connection_label is None or source_label is None:
            return

        connection_text = "接続中" if connected else "未接続"
        source_text = self._source_text(source)
        connection_color = "#22c55e" if connected else "#f97316"
        source_color = {
            "実データ": "#22c55e",
            "実カメラ": "#22c55e",
            "Mockデータ": "#fde68a",
            "Mock通信": "#fde68a",
            "Mock映像": "#fde68a",
            "シミュレーション": "#93c5fd",
        }.get(source_text, "#cbd5e1")

        connection_label.setText(connection_text)
        source_label.setText(source_text)
        connection_label.setStyleSheet(f"color:{connection_color}; font-weight:700;")
        source_label.setStyleSheet(f"color:{source_color}; font-weight:700;")

    def _source_text(self, source: str) -> str:
        if source == "Mock通信":
            return "Mock通信"
        if source == "Mock映像":
            return "Mock映像"
        if source == "RealCamera":
            return "実カメラ"
        if source == "Real":
            return "実データ"
        if source == "Simulation":
            return "シミュレーション"
        if source == "Mock":
            return "Mockデータ"
        return source or "データなし"

    def _tooltip(self, name: str) -> str:
        tooltips = {
            "ESP32": "ESP32との通信状態と、実通信かMock通信かを表示します。",
            "Camera": "USBカメラまたはMock映像の状態を表示します。",
            "LSB": "Localization Sensor Boardのシリアル受信状態を表示します。",
            "LiDAR": "LiDAR距離センサの接続状態とデータ種別を表示します。",
            "IMU": "IMU姿勢センサの接続状態とデータ種別を表示します。",
            "Optical Odometry": "光学式オドメトリの接続状態とデータ種別を表示します。",
            "Encoder": "左右エンコーダの接続状態とデータ種別を表示します。",
        }
        return tooltips.get(name, "")
