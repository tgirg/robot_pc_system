from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .ui_helpers import boxed, make_button, make_notice


def create_esp32_connection_panel(host) -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(host.esp32_connection_label)
    layout.addWidget(host.esp32_connection_detail_label)
    layout.addWidget(host.connection_test_label)

    port_row = QWidget()
    port_layout = QHBoxLayout(port_row)
    port_layout.addWidget(QLabel("COM選択"))
    host.com_port_combo.setMinimumWidth(300)
    port_layout.addWidget(host.com_port_combo)
    port_layout.addStretch(1)
    layout.addWidget(port_row)

    row1 = QWidget()
    row1_layout = QHBoxLayout(row1)
    for text, slot in [
        ("COMポート更新", host.refresh_com_ports),
        ("ESP32候補を自動選択", host.auto_select_esp32_port),
        ("ESP32接続", host.connect_esp32_from_ui),
        ("ESP32切断", host.disconnect_esp32_from_ui),
    ]:
        row1_layout.addWidget(make_button(text, slot))
    row1_layout.addStretch(1)
    layout.addWidget(row1)

    row2 = QWidget()
    row2_layout = QHBoxLayout(row2)
    for text, slot in [
        ("接続テスト", host.test_esp32_connection),
        ("受信確認", host.start_esp32_receive_check),
        ("テスト送信", host.send_esp32_test_command),
        ("停止送信", host.send_esp32_stop_command),
        ("設定に保存", host.save_selected_com_port),
    ]:
        row2_layout.addWidget(make_button(text, slot))
    row2_layout.addStretch(1)
    layout.addWidget(row2)
    layout.addWidget(make_notice("注意：テスト送信は接続中のESP32へ DRIVE VEL 50 50 を送信し、最後に DRIVE STOP を送信します。"))
    return boxed("ESP32通信テスト", panel)
