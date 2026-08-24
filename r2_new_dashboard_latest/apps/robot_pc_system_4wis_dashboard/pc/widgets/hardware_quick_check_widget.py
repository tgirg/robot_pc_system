from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_button, make_notice


def create_hardware_quick_check_panel(host) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(make_notice(
        "ESP32接続、STATUS、IMU、LiDAR、エンコーダ、モータダミー、テスト送信、STOP送信をまとめて確認します。"
    ))
    summary = QGridLayout()
    summary.addWidget(host.quick_check_com_label, 0, 0)
    summary.addWidget(host.quick_check_connection_label, 0, 1)
    summary.addWidget(host.quick_check_result_label, 1, 0)
    summary.addWidget(host.quick_check_time_label, 1, 1)
    layout.addLayout(summary)

    checklist = QGridLayout()
    checklist.setSpacing(8)
    items = [
        ("esp32", "ESP32接続"),
        ("status", "STATUS受信"),
        ("imu", "IMU受信"),
        ("lidar", "LiDAR受信"),
        ("encoder", "エンコーダ受信"),
        ("motor", "モータダミー受信"),
        ("test_send", "テスト送信"),
        ("stop_send", "STOP送信"),
    ]
    for index, (key, title) in enumerate(items):
        label = QLabel(f"{title}: 未確認")
        label.setObjectName("quickCheckItem")
        host.quick_check_item_labels[key] = label
        checklist.addWidget(label, index // 4, index % 4)
    layout.addLayout(checklist)

    buttons = QWidget()
    button_layout = QHBoxLayout(buttons)
    run_button = make_button("実機クイック確認を実行", host.start_quick_hardware_check, 56)
    run_button.setMinimumWidth(240)
    host.quick_check_run_button = run_button
    button_layout.addWidget(run_button)
    for text, slot in [
        ("STOP送信", host.send_esp32_stop_command),
        ("最新結果を開く", host.open_latest_hardware_check_result),
        ("最新結果をコピー", host.copy_latest_hardware_check_result),
        ("結果フォルダを開く", host.open_hardware_check_folder),
    ]:
        button_layout.addWidget(make_button(text, slot, 44))
    button_layout.addStretch(1)
    layout.addWidget(buttons)
    layout.addWidget(make_notice("成功すると結果は logs\\hardware_checks に保存されます。失敗時はCOMポート、再接続、書き込み、ログを確認してください。"))
    layout.addWidget(host.latest_hardware_result_label)
    host._reset_quick_check_items()
    return boxed("実機クイック確認", box)
