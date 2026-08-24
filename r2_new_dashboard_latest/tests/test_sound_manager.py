from __future__ import annotations

import json
import wave
from pathlib import Path
from types import SimpleNamespace

from pc_controller.autonomy import RobotId
from pc_controller.gui_model import ConnectionState, DisplaySeverity

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"

import sys

sys.path.insert(0, str(DASHBOARD_PC))

from sound_manager import SoundEvent, SoundManager, SoundSettings  # noqa: E402
from sound_manager import SOUND_SPECS  # noqa: E402


class RecordingBackend:
    available = True
    error = ""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def play(self, path: Path, volume: float) -> bool:
        self.calls.append((path.name, volume))
        return True


def _robot(**overrides):
    values = {
        "robot_id": RobotId.R2,
        "connection": ConnectionState.OFFLINE,
        "controller_connected": False,
        "ready": False,
        "armed": False,
        "arm_pending": False,
        "safe": True,
        "competition_state": None,
        "fault": None,
        "warnings": (),
        "diagnostic_events": (),
        "severity": DisplaySeverity.INFO,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _fleet(robot):
    return SimpleNamespace(robots=(robot,))


def test_sound_settings_persist_immediately_and_keep_backward_defaults(tmp_path: Path) -> None:
    backend = RecordingBackend()
    manager = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=backend,
    )
    settings = SoundSettings(master_volume=0.34, warning_enabled=False)
    assert manager.update_settings(settings) is True

    saved = json.loads((tmp_path / "sound_settings.json").read_text(encoding="utf-8"))
    assert saved["master_volume"] == 0.34
    assert saved["warning_enabled"] is False
    assert set(saved["event_enabled"]) == {event.value for event in SoundEvent}

    reloaded = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=backend,
    )
    assert reloaded.settings.master_volume == 0.34
    assert reloaded.settings.operation_enabled is True


def test_transition_observer_never_sounds_on_repeated_telemetry(tmp_path: Path) -> None:
    now = 10_000
    backend = RecordingBackend()
    manager = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=backend,
        clock_ms=lambda: now,
    )
    offline = _robot()
    manager.observe_fleet_snapshot(_fleet(offline))
    assert backend.calls == []

    online = _robot(connection=ConnectionState.ONLINE, ready=True, controller_connected=True)
    emitted = manager.observe_fleet_snapshot(_fleet(online))
    assert emitted == (
        SoundEvent.DEVICE_CONNECTED,
        SoundEvent.CONTROLLER_CONNECTED,
        SoundEvent.COMMUNICATION_TEST_PASS,
    )
    call_count = len(backend.calls)
    manager.observe_fleet_snapshot(_fleet(online))
    manager.observe_fleet_snapshot(_fleet(online))
    assert len(backend.calls) == call_count


def test_fault_timeout_and_competition_edges_are_distinct(tmp_path: Path) -> None:
    backend = RecordingBackend()
    manager = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=backend,
        clock_ms=lambda: 20_000,
    )
    manager.observe_fleet_snapshot(_fleet(_robot(connection=ConnectionState.ONLINE, ready=True)))
    ready = _robot(connection=ConnectionState.ONLINE, ready=True, competition_state="READY_DISARMED")
    assert SoundEvent.START_READY in manager.observe_fleet_snapshot(_fleet(ready))
    active = _robot(connection=ConnectionState.ONLINE, ready=True, competition_state="ACTIVE", armed=True, safe=False)
    emitted = manager.observe_fleet_snapshot(_fleet(active))
    assert SoundEvent.START in emitted
    timeout = _robot(
        connection=ConnectionState.ONLINE,
        ready=False,
        fault="telemetry timeout",
        competition_state="BLOCKED",
    )
    emitted = manager.observe_fleet_snapshot(_fleet(timeout))
    assert SoundEvent.FAIL in emitted
    assert SoundEvent.TIMEOUT_RELOCK in emitted


def test_audio_failure_is_fail_soft(tmp_path: Path) -> None:
    class BrokenBackend(RecordingBackend):
        def play(self, path: Path, volume: float) -> bool:
            del path, volume
            raise RuntimeError("device unavailable")

    manager = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=BrokenBackend(),
    )
    assert manager.play(SoundEvent.WARNING) is False
    assert manager.last_error == "device unavailable"


def test_every_event_has_one_valid_original_pcm_asset() -> None:
    sounds = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "assets" / "sounds"
    files = {path.stem: path for path in sounds.glob("*.wav")}
    assert set(files) == {event.value for event in SOUND_SPECS}
    for path in files.values():
        with wave.open(str(path), "rb") as wav:
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getframerate() == 22050
            assert wav.getnframes() > 1000


def test_same_event_is_cooled_down_but_preview_is_immediate(tmp_path: Path) -> None:
    now = 42_000
    backend = RecordingBackend()
    manager = SoundManager(
        assets_dir=tmp_path,
        settings_path=tmp_path / "sound_settings.json",
        backend=backend,
        clock_ms=lambda: now,
    )
    assert manager.play(SoundEvent.WARNING) is True
    assert manager.play(SoundEvent.WARNING) is False
    assert manager.play(SoundEvent.WARNING, preview=True) is True
    assert len(backend.calls) == 2
