from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from .ui_helpers import boxed, set_section_title


def _detail_page(host, key: str, rows: list[str]) -> QWidget:
    page = QWidget()
    layout = QFormLayout(page)
    labels: dict[str, QLabel] = {}
    for row in rows:
        label = QLabel("-")
        label.setObjectName("cardValue")
        label.setWordWrap(True)
        layout.addRow(row, label)
        labels[row] = label
    host.sensor_detail_labels[key] = labels
    return page


def create_sensor_tab(host) -> QWidget:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(14, 14, 14, 14)

    title = QLabel("センサ")
    set_section_title(title)
    layout.addWidget(title)

    actions = QWidget()
    actions_layout = QHBoxLayout(actions)
    actions_layout.setContentsMargins(0, 0, 0, 0)
    refresh_button = QPushButton("更新")
    imu_field_button = QPushButton("IMU慣性推定を開始")
    refresh_button.clicked.connect(host.force_sensor_ok_refresh)
    imu_field_button.clicked.connect(host.enable_imu_only_field_mode)
    actions_layout.addWidget(refresh_button)
    actions_layout.addWidget(imu_field_button)
    actions_layout.addStretch(1)
    layout.addWidget(actions)

    tabs = QTabWidget()

    overview = QWidget()
    overview_layout = QVBoxLayout(overview)
    overview_layout.addWidget(boxed("接続状態", host.status_panel))
    overview_layout.addWidget(boxed("センサ概要", host.sensor_panel))
    overview_layout.addStretch(1)
    tabs.addTab(overview, "センサ概要")

    tabs.addTab(
        _detail_page(host, "imu", ["IMU状態", "yaw", "pitch", "roll", "gyro x", "gyro y", "gyro z", "accel x", "accel y", "accel z", "データ種別"]),
        "IMU",
    )
    tabs.addTab(
        _detail_page(host, "lidar", ["LiDAR状態", "前方", "左", "右", "後方", "データ種別"]),
        "LiDAR",
    )
    tabs.addTab(
        _detail_page(host, "encoder", ["左エンコーダ", "右エンコーダ", "状態", "データ種別"]),
        "エンコーダ",
    )

    camera = QWidget()
    camera_layout = QVBoxLayout(camera)
    host.sensor_detail_labels["camera"] = {
        "カメラ状態": QLabel("-"),
        "データ種別": QLabel("-"),
    }
    for label in host.sensor_detail_labels["camera"].values():
        label.setObjectName("cardValue")
    camera_layout.addWidget(boxed("カメラ状態", host.sensor_detail_labels["camera"]["カメラ状態"]))
    camera_layout.addWidget(boxed("カメラ映像", host.camera_widget), 1)
    tabs.addTab(camera, "カメラ")

    layout.addWidget(tabs, 1)
    return tab
