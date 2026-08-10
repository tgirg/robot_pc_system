from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from hardware_profile import format_wiring_report_text, generate_wiring_report, load_hardware_profile, save_wiring_report

from .hardware_profile_editor_widget import create_hardware_profile_editor_panel
from .ui_helpers import boxed, make_button, make_notice


def create_settings_tab(host) -> QWidget:
    tab = QWidget()
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)

    info = QLabel(
        f"アプリ配置: {host._project_root()}\n"
        f"現在モード: {host.mode_name}\n"
        f"前回COMポート: {host.local_settings.get('last_com_port', '-')}\n"
        f"書き込み用COMポート: {host.local_settings.get('last_upload_port', '-')}\n"
        f"設定COMポート: {host.serial.port}\n"
        f"通信速度: {host.serial.baudrate}"
    )
    info.setObjectName("diagnosticLabel")
    layout.addWidget(boxed("現在の設定", info))

    quick_buttons = QWidget()
    quick_layout = QHBoxLayout(quick_buttons)
    quick_layout.addWidget(make_button("ESP32書き込み画面を開く", lambda: host.switch_to_tab("診断")))
    quick_layout.addWidget(make_button("実機接続画面を開く", lambda: host.switch_to_tab("実機接続")))
    quick_layout.addWidget(make_button("ハードウェア構成をコピー", lambda: _copy_hardware_profile(host)))
    quick_layout.addStretch(1)
    layout.addWidget(boxed("画面移動", quick_buttons))

    hardware_box = QWidget()
    hardware_layout = QVBoxLayout(hardware_box)
    hardware_layout.addWidget(make_notice("この画面は配線計画メモです。保存しても実出力を有効化するものではありません。"))
    host.hardware_profile_label.setText(host.hardware_profile.to_summary_text())
    hardware_layout.addWidget(host.hardware_profile_label)

    wiring_label = QLabel("配線表: 未作成")
    wiring_label.setObjectName("diagnosticLabel")
    host.wiring_report_label = wiring_label
    hardware_layout.addWidget(wiring_label)

    buttons = QWidget()
    button_layout = QHBoxLayout(buttons)
    for text, slot in [
        ("配線表を作成", lambda: _create_wiring_report(host)),
        ("配線表をコピー", lambda: _copy_wiring_report(host)),
        ("配線表を開く", lambda: _open_wiring_report(host)),
        ("YAMLを開く", lambda: host.open_project_file("config/hardware_profile.yaml")),
        ("結果フォルダを開く", lambda: host.open_project_file("logs/hardware_checks")),
        ("編集方法を開く", lambda: host.open_project_file("docs/hardware_profile_editor.md")),
    ]:
        button_layout.addWidget(make_button(text, slot))
    button_layout.addStretch(1)
    hardware_layout.addWidget(buttons)
    layout.addWidget(boxed("ハードウェア構成メモ", hardware_box))
    layout.addWidget(create_hardware_profile_editor_panel(host), 1)
    scroll.setWidget(content)
    outer.addWidget(scroll)
    return tab


def _copy_hardware_profile(host) -> None:
    QApplication.clipboard().setText(host.hardware_profile.to_summary_text())
    host._log("ハードウェア構成をクリップボードへコピーしました")
    if hasattr(host, "notify_operation"):
        host.notify_operation("ハードウェア構成をコピーしました", "success")


def _create_wiring_report(host) -> None:
    if hasattr(host, "notify_operation"):
        host.notify_operation("配線表を作成中...", "busy")
    host.hardware_profile = load_hardware_profile()
    txt_path, json_path, _report = save_wiring_report(host._project_root(), host.hardware_profile)
    host.latest_wiring_report_txt_path = str(txt_path)
    host.latest_wiring_report_json_path = str(json_path)
    if hasattr(host, "wiring_report_label"):
        host.wiring_report_label.setText(f"配線表: 作成済み\nTXT: {txt_path}\nJSON: {json_path}")
    host._log(f"配線表を作成しました: {txt_path}")
    if hasattr(host, "notify_operation"):
        host.notify_operation(f"配線表を作成しました: {txt_path.name}", "success")


def _copy_wiring_report(host) -> None:
    path = _latest_wiring_text_path(host)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        report = generate_wiring_report(load_hardware_profile())
        text = format_wiring_report_text(report)
    QApplication.clipboard().setText(text)
    host._log("配線表をクリップボードへコピーしました")
    if hasattr(host, "notify_operation"):
        host.notify_operation("配線表をコピーしました", "success")


def _open_wiring_report(host) -> None:
    path = _latest_wiring_text_path(host)
    if not path.exists():
        _create_wiring_report(host)
        path = _latest_wiring_text_path(host)
    try:
        import os

        os.startfile(str(path))
        host._log(f"配線表を開きました: {path}")
        if hasattr(host, "notify_operation"):
            host.notify_operation("配線表を開きました", "success")
    except Exception as exc:
        host._log(f"配線表を開けませんでした: {exc}")
        if hasattr(host, "notify_operation"):
            host.notify_operation(f"配線表を開けませんでした: {exc}", "error")


def _latest_wiring_text_path(host) -> Path:
    if getattr(host, "latest_wiring_report_txt_path", ""):
        path = Path(host.latest_wiring_report_txt_path)
        if path.exists():
            return path
    return host._project_root() / "logs" / "wiring_reports" / "latest_wiring_report.txt"
