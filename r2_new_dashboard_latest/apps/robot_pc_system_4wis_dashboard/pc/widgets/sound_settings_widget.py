from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from sound_manager import SOUND_SPECS, SoundEvent, SoundManager, SoundSettings


class SoundSettingsWidget(QWidget):
    """Immediate, persistent sound settings with individual event previews."""

    def __init__(self, manager: SoundManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("soundSettingsScreen")
        settings = manager.settings

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        title = QLabel("AUDIO CONTROL / 効果音管制")
        title.setObjectName("commandSectionTitle")
        root.addWidget(title)

        master = QGroupBox("MASTER / 即時反映")
        master_layout = QGridLayout(master)
        self.master_check = QCheckBox("マスター音声 ON")
        self.master_check.setChecked(settings.master_enabled)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(round(settings.master_volume * 100))
        self.volume_label = QLabel(f"{self.volume_slider.value()} %")
        self.operation_check = QCheckBox("操作音")
        self.connection_check = QCheckBox("接続音")
        self.warning_check = QCheckBox("警告音")
        self.operation_check.setChecked(settings.operation_enabled)
        self.connection_check.setChecked(settings.connection_enabled)
        self.warning_check.setChecked(settings.warning_enabled)
        master_layout.addWidget(self.master_check, 0, 0)
        master_layout.addWidget(QLabel("MASTER VOLUME"), 0, 1)
        master_layout.addWidget(self.volume_slider, 0, 2)
        master_layout.addWidget(self.volume_label, 0, 3)
        master_layout.addWidget(self.operation_check, 1, 0)
        master_layout.addWidget(self.connection_check, 1, 1)
        master_layout.addWidget(self.warning_check, 1, 2)
        root.addWidget(master)

        event_box = QGroupBox("EVENT MATRIX / 個別イベント試聴")
        event_grid = QGridLayout(event_box)
        event_grid.addWidget(QLabel("EVENT"), 0, 0)
        event_grid.addWidget(QLabel("CATEGORY"), 0, 1)
        event_grid.addWidget(QLabel("ENABLE"), 0, 2)
        event_grid.addWidget(QLabel("TEST"), 0, 3)
        self.event_checks: dict[SoundEvent, QCheckBox] = {}
        self.preview_buttons: dict[SoundEvent, QPushButton] = {}
        for row, (event, spec) in enumerate(SOUND_SPECS.items(), start=1):
            event_grid.addWidget(QLabel(f"{event.value.upper()} / {spec.label_ja}"), row, 0)
            event_grid.addWidget(QLabel(spec.category.value.upper()), row, 1)
            check = QCheckBox("ON")
            check.setChecked(settings.event_enabled.get(event.value, True))
            preview = QPushButton("▶ 試聴")
            preview.setProperty("commandRole", "preview")
            preview.clicked.connect(lambda _checked=False, value=event: self.preview(value))
            check.toggled.connect(self._save)
            self.event_checks[event] = check
            self.preview_buttons[event] = preview
            event_grid.addWidget(check, row, 2)
            event_grid.addWidget(preview, row, 3)
        event_grid.setColumnStretch(0, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(event_box)
        root.addWidget(scroll, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("soundStatusLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.master_check.toggled.connect(self._save)
        self.operation_check.toggled.connect(self._save)
        self.connection_check.toggled.connect(self._save)
        self.warning_check.toggled.connect(self._save)
        self.volume_slider.valueChanged.connect(self._volume_changed)
        self._refresh_status("設定を読み込みました")

    def preview(self, event: SoundEvent) -> None:
        self._save(play_feedback=False)
        played = self.manager.play(event, preview=True)
        if played:
            self._refresh_status(f"試聴: {SOUND_SPECS[event].label_ja}")
        else:
            reason = self.manager.last_error or "ミュート、カテゴリOFF、または音声デバイス未使用"
            self._refresh_status(f"試聴なし: {reason}", error=True)

    def _volume_changed(self, value: int) -> None:
        self.volume_label.setText(f"{value} %")
        self._save()

    def _save(self, _value=None, *, play_feedback: bool = True) -> None:
        settings = SoundSettings(
            master_enabled=self.master_check.isChecked(),
            master_volume=self.volume_slider.value() / 100.0,
            operation_enabled=self.operation_check.isChecked(),
            connection_enabled=self.connection_check.isChecked(),
            warning_enabled=self.warning_check.isChecked(),
            event_enabled={event.value: check.isChecked() for event, check in self.event_checks.items()},
        )
        if self.manager.update_settings(settings):
            self._refresh_status("保存済み / 即時反映")
            if play_feedback:
                self.manager.play(SoundEvent.SETTINGS_SAVED)
        else:
            self._refresh_status(f"保存失敗: {self.manager.last_error}", error=True)
            if play_feedback:
                self.manager.play(SoundEvent.SETTINGS_SAVE_FAILED)

    def _refresh_status(self, message: str, *, error: bool = False) -> None:
        audio = "AUDIO READY" if self.manager.audio_available else "AUDIO FAIL-SOFT / GUI継続"
        self.status_label.setText(f"{audio} | {message}")
        self.status_label.setProperty("status", "error" if error else "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


def create_sound_settings_tab(host) -> SoundSettingsWidget:
    widget = SoundSettingsWidget(host.sound_manager)
    host.sound_settings_widget = widget
    return widget

