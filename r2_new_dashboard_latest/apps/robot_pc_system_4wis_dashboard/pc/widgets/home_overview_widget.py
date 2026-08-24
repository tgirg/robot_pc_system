from __future__ import annotations

from PySide6.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .ui_helpers import add_nav_button, boxed, make_notice, make_scroll_area, set_section_title


def create_home_tab(host) -> QWidget:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    title = QLabel("ホーム")
    set_section_title(title)
    layout.addWidget(title)

    host.next_action_label = QLabel("次にやること: ESP32をUSB接続して、診断タブでボード一覧更新を押してください。")
    host.next_action_label.setObjectName("largeValue")
    host.next_action_label.setWordWrap(True)
    layout.addWidget(boxed("次の操作", host.next_action_label))
    layout.addWidget(make_notice("安全設定: 実モータ出力は無効です。ESP32への自動アップロードは行いません。"))

    host.home_status_label = QLabel(
        "システム状態\n"
        "ESP32: 未接続\n"
        "IMU: 未接続 / LiDAR: 未接続 / 光学式オドメトリ: 未接続\n"
        "R2位置推定: 準備中\n"
        "現在ファームウェア: 未確認"
    )
    host.home_status_label.setObjectName("largeValue")
    host.home_status_label.setWordWrap(True)
    layout.addWidget(boxed("システム状態", host.home_status_label))

    workflow = QWidget()
    workflow_layout = QGridLayout(workflow)
    workflow_layout.setSpacing(10)
    host.workflow_step_labels = {}
    steps = [
        ("usb", "1. ESP32 USB接続"),
        ("board", "2. ボード一覧更新"),
        ("compile", "3. コンパイル確認"),
        ("upload", "4. ESP32へ書き込み"),
        ("reconnect", "5. ESP32再接続"),
        ("quick", "6. 実機クイック確認"),
        ("save", "7. 結果保存"),
    ]
    for index, (key, step_title) in enumerate(steps):
        card = QWidget()
        card_layout = QVBoxLayout(card)
        step_label = QLabel(step_title)
        step_label.setObjectName("cardLabel")
        status_label = QLabel("未実行")
        status_label.setObjectName("cardValue")
        status_label.setWordWrap(True)
        card_layout.addWidget(step_label)
        card_layout.addWidget(status_label)
        host.workflow_step_labels[key] = status_label
        workflow_layout.addWidget(boxed(step_title, card), index // 4, index % 4)
    layout.addWidget(boxed("作業ナビ", workflow))

    grid = QGridLayout()
    grid.setSpacing(10)
    cards = [
        ("esp32", "ESP32接続", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("firmware", "ファームウェア", [("状態", "未確認"), ("値", "-"), ("データ種別", "受信情報")]),
        ("imu", "IMU", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("lidar", "LiDAR", [("状態", "未確認"), ("値", "-"), ("データ種別", "データなし")]),
        ("motor", "モータ出力", [("状態", "停止中"), ("値", "-"), ("データ種別", "無効（安全ダミー）")]),
        ("quick", "最新実機確認", [("状態", "未実行"), ("値", "-"), ("データ種別", "結果保存")]),
        ("wiring", "最新配線表", [("状態", "未作成"), ("値", "-"), ("データ種別", "配線表")]),
        ("log", "最新ログ", [("状態", "表示中"), ("値", "-"), ("データ種別", "操作ログ")]),
    ]
    for index, (key, card_title, rows) in enumerate(cards):
        grid.addWidget(host._machine_card(key, card_title, rows), index // 4, index % 4)
    layout.addLayout(grid)

    nav = QWidget()
    nav_layout = QHBoxLayout(nav)
    add_nav_button(nav_layout, host, "Main Dashboardを開く", "Main Dashboard")
    add_nav_button(nav_layout, host, "診断を開く", "診断")
    add_nav_button(nav_layout, host, "実機接続を開く", "実機接続")
    add_nav_button(nav_layout, host, "書き込みを開く", "書き込み")
    add_nav_button(nav_layout, host, "シリアルを開く", "シリアル")
    add_nav_button(nav_layout, host, "テストフィールドを開く", "テストフィールド")
    add_nav_button(nav_layout, host, "ログを開く", "ログ")
    add_nav_button(nav_layout, host, "設定を開く", "設定")
    copy_button = QPushButton("現在状態をコピー")
    copy_button.clicked.connect(lambda: _copy_current_status(host))
    nav_layout.addWidget(copy_button)
    nav_layout.addStretch(1)
    layout.addWidget(boxed("移動", nav))
    layout.addStretch(1)
    return make_scroll_area(content)


def _copy_current_status(host) -> None:
    board = host.hardware_profile.get_board_summary()
    imu = host.hardware_profile.get_imu_summary()
    lidar = host.hardware_profile.get_lidar_summary()
    motor = host.hardware_profile.get_motor_summary()
    encoder = host.hardware_profile.get_encoder_summary()
    display_mode = "全画面" if host.isFullScreen() else "通常"
    text = "\n".join(
        [
            "現在状態",
            f"表示モード: {display_mode}",
            f"モード: {host.mode_name}",
            f"安全状態: {host.safety_label.text()}",
            f"ESP32接続: {host.header_esp32_label.text()}",
            f"ファームウェア: {host.firmware_name or '未確認'} {host.firmware_version or ''}".strip(),
            f"IMU: {host._card_value_text('imu')}",
            f"LiDAR: {host._card_value_text('lidar')}",
            f"モータ: {host._card_value_text('motor')}",
            f"実機クイック確認: {host.quick_check_result_label.text()}",
            f"最新実機確認: {host.latest_hardware_check_txt_path or 'なし'}",
            f"最新配線表: {getattr(host, 'latest_wiring_report_txt_path', '') or 'なし'}",
            getattr(getattr(host, "test_field_widget", None), "summary_text", lambda: "テストフィールド: データなし")(),
            "",
            "ハードウェア構成",
            f"ボード: {board.get('type', '-')}",
            f"IMU型番: {imu.get('type', '-')}",
            f"LiDAR型番: {lidar.get('type', '-')}",
            f"モータドライバ: {motor.get('type', '-')}",
            f"エンコーダ: {'有効' if encoder.get('enabled') else '無効'}",
            "",
            "安全設定",
            "MOTOR_OUTPUT_ENABLED 0",
            "USE_REAL_IMU 0",
            "USE_REAL_LIDAR 0",
            "",
            "ハードウェア構成サマリー",
            host.hardware_profile.to_summary_text(),
        ]
    )
    QApplication.clipboard().setText(text)
    host._log("現在状態をクリップボードへコピーしました")
