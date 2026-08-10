from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_doc_button, make_notice, make_scroll_area, set_section_title


def create_document_links_tab(host) -> QWidget:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(14, 14, 14, 14)
    title = QLabel("ドキュメント")
    set_section_title(title)
    layout.addWidget(title)
    layout.addWidget(make_notice("資料ボタンはWindowsの既定アプリでファイルを開きます。ファイルが無い場合は操作ログに表示します。"))
    groups = [
        ("使い方", [("使い方", "docs/how_to_use.md"), ("初心者向けガイド", "docs/usability_guide.md"), ("全画面UI", "docs/fullscreen_ui.md")]),
        ("実機接続", [("ESP32接続", "docs/esp32_connection.md"), ("実機確認ログ", "docs/hardware_check_logs.md"), ("ハードウェア構成エディタ", "docs/hardware_profile_editor.md")]),
        ("センサ", [("LiDAR接続テンプレート", "docs/real_lidar_templates.md"), ("IMU接続テンプレート", "docs/real_imu_templates.md"), ("エンコーダ接続", "docs/encoder_connection.md")]),
        ("駆動", [("モータ安全手順", "docs/motor_driver_safety.md"), ("モータドライバ", "docs/motor_driver.md")]),
        ("ミニPC/共有", [("ミニPC移行手順", "docs/mini_pc_migration.md"), ("班員引き継ぎ", "docs/team_handoff.md"), ("現在の状態まとめ", "docs/current_status_summary.md")]),
        ("ログ/レポート", [("報告方法", "docs/reporting.md"), ("進捗メモ", "docs/progress_report_notes.md"), ("画面構成", "docs/ui_layout.md")]),
    ]
    grid = QGridLayout()
    grid.setSpacing(12)
    for index, (group_title, docs) in enumerate(groups):
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        for doc_title, path in docs:
            panel_layout.addWidget(make_doc_button(host, doc_title, path))
        panel_layout.addStretch(1)
        grid.addWidget(boxed(group_title, panel), index // 2, index % 2)
    layout.addLayout(grid)
    layout.addStretch(1)
    return make_scroll_area(content)
