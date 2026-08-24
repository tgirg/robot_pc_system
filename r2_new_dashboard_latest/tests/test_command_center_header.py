from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from pc_controller.autonomy import RobotId
from pc_controller.gui_model import BackendKind, ConnectionState, DisplaySeverity

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

import main_ui  # noqa: E402
from sound_manager import SoundEvent  # noqa: E402


class RecordingBackend:
    available = True
    error = ""

    def __init__(self) -> None:
        self.events: list[str] = []

    def play(self, path: Path, volume: float) -> bool:
        del volume
        self.events.append(path.stem)
        return True


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _competition_ready(timestamp_ms: int):
    return SimpleNamespace(
        robot_id=RobotId.R2,
        connection=ConnectionState.ONLINE,
        backend=BackendKind.FAKE_ESP32,
        safety_state="SAFE",
        ready=True,
        armed=False,
        communication_age_ms=0,
        telemetry_age_ms=0,
        competition_state="READY_DISARMED",
        severity=DisplaySeverity.INFO,
        timestamp_ms=timestamp_ms,
    )


def test_start_ready_display_counts_down_and_cues_once(qt_app: QApplication) -> None:
    del qt_app
    window = main_ui.MainWindow(shared_runtime_only=True)
    backend = RecordingBackend()
    window.sound_manager.backend = backend

    window._update_command_center_header(SimpleNamespace(selected=_competition_ready(1_000)))
    assert "残り 60.0 s" in window.command_center_header.readiness_text
    window._update_command_center_header(SimpleNamespace(selected=_competition_ready(51_000)))
    assert "残り 10.0 s" in window.command_center_header.readiness_text
    assert backend.events.count(SoundEvent.START_READY_10S.value) == 1
    window._update_command_center_header(SimpleNamespace(selected=_competition_ready(52_000)))
    assert backend.events.count(SoundEvent.START_READY_10S.value) == 1
    window._update_command_center_header(SimpleNamespace(selected=_competition_ready(61_000)))
    assert "00.0 s / DISPLAY ONLY" in window.command_center_header.readiness_text
    assert backend.events.count(SoundEvent.WARNING.value) == 1
    window.close()
