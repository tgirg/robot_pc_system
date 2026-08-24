from __future__ import annotations

from PySide6.QtWidgets import QLabel, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from .hardware_quick_check_widget import create_hardware_quick_check_panel
from .safety_checklist_widget import create_safety_checklist_panel
from .ui_helpers import boxed, make_button, make_notice, make_scroll_area, set_section_title


def create_real_machine_overview(host) -> QWidget:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    title = QLabel("実機接続")
    set_section_title(title)
    layout.addWidget(title)
    layout.addWidget(make_notice("接続できない時は、Arduino IDEのシリアルモニタを閉じる、USBを挿し直す、COMポート更新、ボード一覧更新を順に試してください。"))

    cards = QGridLayout()
    cards.setSpacing(10)
    card_defs = [
        (
            "pre_operation_check",
            "実機操作前チェック",
            [
                ("MOTOR_OUTPUT_ENABLED", "確認中"),
                ("USE_REAL_IMU", "確認中"),
                ("USE_REAL_LIDAR", "確認中"),
                ("ESP32接続状態", "未確認"),
                ("緊急停止状態", "未作動"),
            ],
        ),
        ("esp32", "ESP32接続", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("firmware", "ESP32ファームウェア", [("状態", "未確認"), ("値", "-"), ("データ種別", "受信情報")]),
        ("imu", "IMU", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("lidar", "LiDAR", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("encoder", "エンコーダ", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("motor", "モータ出力", [("状態", "停止中"), ("値", "-"), ("データ種別", "無効（安全ダミー）")]),
        ("command", "現在指令", [("状態", "待機中"), ("値", host.current_command), ("データ種別", "PC指令")]),
    ]
    for index, (key, card_title, rows) in enumerate(card_defs):
        cards.addWidget(host._machine_card(key, card_title, rows), index // 4, index % 4)
    layout.addLayout(cards)

    columns = QHBoxLayout()
    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.addWidget(boxed("ESP32接続状態", host.real_esp32_connection_label))
    left_layout.addWidget(boxed("ESP32通信詳細", host.real_esp32_connection_detail_label))
    nav = QWidget()
    nav_layout = QVBoxLayout(nav)
    nav_layout.addWidget(make_button("ESP32接続操作を開く", lambda: host.switch_to_tab("診断")))
    nav_layout.addWidget(make_button("ログを見る", lambda: host.switch_to_tab("ログ")))
    left_layout.addWidget(boxed("操作への移動", nav))
    left_layout.addStretch(1)
    center = QWidget()
    center_layout = QVBoxLayout(center)
    center_layout.setContentsMargins(0, 0, 0, 0)
    center_layout.addWidget(create_hardware_quick_check_panel(host))
    center_layout.addStretch(1)
    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.addWidget(create_safety_checklist_panel(host))
    help_text = QLabel(
        "接続できない時に確認すること:\n"
        "- Arduino IDEのシリアルモニタを閉じる\n"
        "- アプリを複数起動していないか確認\n"
        "- ESP32を挿し直す\n"
        "- USBケーブルを変える\n"
        "- COMポート更新を押す\n"
        "- ボード一覧更新を押す\n"
        "- COM番号が変わっていないか確認\n"
        "- それでもだめなら examples\\quick_hardware_check.py COM10 を実行"
    )
    help_text.setObjectName("diagnosticLabel")
    right_layout.addWidget(boxed("接続トラブル時の確認", help_text))
    right_layout.addStretch(1)
    columns.addWidget(left, 1)
    columns.addWidget(center, 2)
    columns.addWidget(right, 1)
    layout.addLayout(columns, 1)
    return make_scroll_area(content)
