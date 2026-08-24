"""Fail-soft, transition-driven command-center sound effects.

The sound layer is deliberately independent from robot control.  It consumes
immutable GUI snapshots, never writes to Serial, and treats playback failures
as a visual-only warning so audio can never stop the controller or GUI.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class SoundCategory(str, Enum):
    OPERATION = "operation"
    CONNECTION = "connection"
    WARNING = "warning"


class SoundEvent(str, Enum):
    STARTUP_COMPLETE = "startup_complete"
    DEVICE_CONNECTED = "device_connected"
    DEVICE_DISCONNECTED = "device_disconnected"
    CONTROLLER_CONNECTED = "controller_connected"
    CONTROLLER_DISCONNECTED = "controller_disconnected"
    COMMUNICATION_TEST_PASS = "communication_test_pass"
    START_READY = "start_ready"
    START_READY_10S = "start_ready_10s"
    START = "start"
    SAFE = "safe"
    ARM = "arm"
    FAIL = "fail"
    TIMEOUT_RELOCK = "timeout_relock"
    SETTINGS_SAVED = "settings_saved"
    SETTINGS_SAVE_FAILED = "settings_save_failed"
    WARNING = "warning"
    CRITICAL = "critical"
    LIMIT_SWITCH = "limit_switch"
    OPERATION_REJECTED = "operation_rejected"


@dataclass(frozen=True)
class SoundSpec:
    label_ja: str
    category: SoundCategory
    cooldown_ms: int


SOUND_SPECS: dict[SoundEvent, SoundSpec] = {
    SoundEvent.STARTUP_COMPLETE: SoundSpec("GUI起動完了", SoundCategory.OPERATION, 1500),
    SoundEvent.DEVICE_CONNECTED: SoundSpec("デバイス接続", SoundCategory.CONNECTION, 1200),
    SoundEvent.DEVICE_DISCONNECTED: SoundSpec("デバイス切断", SoundCategory.CONNECTION, 2500),
    SoundEvent.CONTROLLER_CONNECTED: SoundSpec("コントローラ接続", SoundCategory.CONNECTION, 1200),
    SoundEvent.CONTROLLER_DISCONNECTED: SoundSpec("コントローラ切断", SoundCategory.CONNECTION, 2500),
    SoundEvent.COMMUNICATION_TEST_PASS: SoundSpec("通信テストPASS", SoundCategory.OPERATION, 2500),
    SoundEvent.START_READY: SoundSpec("START READY成立", SoundCategory.OPERATION, 2500),
    SoundEvent.START_READY_10S: SoundSpec("START READY残り10秒", SoundCategory.WARNING, 10000),
    SoundEvent.START: SoundSpec("START成立", SoundCategory.OPERATION, 2500),
    SoundEvent.SAFE: SoundSpec("SAFE移行", SoundCategory.OPERATION, 1500),
    SoundEvent.ARM: SoundSpec("ARM成立", SoundCategory.OPERATION, 1800),
    SoundEvent.FAIL: SoundSpec("FAIL", SoundCategory.WARNING, 3000),
    SoundEvent.TIMEOUT_RELOCK: SoundSpec("タイムアウト／自動再ロック", SoundCategory.WARNING, 5000),
    SoundEvent.SETTINGS_SAVED: SoundSpec("設定保存成功", SoundCategory.OPERATION, 1000),
    SoundEvent.SETTINGS_SAVE_FAILED: SoundSpec("設定保存失敗", SoundCategory.WARNING, 2500),
    SoundEvent.WARNING: SoundSpec("警告発生", SoundCategory.WARNING, 3000),
    SoundEvent.CRITICAL: SoundSpec("重大異常", SoundCategory.WARNING, 5000),
    SoundEvent.LIMIT_SWITCH: SoundSpec("リミットスイッチ作動", SoundCategory.WARNING, 2000),
    SoundEvent.OPERATION_REJECTED: SoundSpec("操作拒否", SoundCategory.OPERATION, 1000),
}


@dataclass
class SoundSettings:
    master_enabled: bool = True
    master_volume: float = 0.55
    operation_enabled: bool = True
    connection_enabled: bool = True
    warning_enabled: bool = True
    event_enabled: dict[str, bool] = field(default_factory=dict)

    def normalized(self) -> "SoundSettings":
        event_enabled = self.event_enabled if isinstance(self.event_enabled, dict) else {}
        return SoundSettings(
            master_enabled=bool(self.master_enabled),
            master_volume=max(0.0, min(1.0, float(self.master_volume))),
            operation_enabled=bool(self.operation_enabled),
            connection_enabled=bool(self.connection_enabled),
            warning_enabled=bool(self.warning_enabled),
            event_enabled={
                event.value: bool(event_enabled.get(event.value, True))
                for event in SoundEvent
            },
        )


class AudioBackend(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def error(self) -> str: ...

    def play(self, path: Path, volume: float) -> bool: ...


class NullAudioBackend:
    def __init__(self, reason: str = "audio disabled") -> None:
        self._error = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def error(self) -> str:
        return self._error

    def play(self, path: Path, volume: float) -> bool:
        del path, volume
        return False


class QtSoundEffectBackend:
    """Small QSoundEffect cache; construction is optional and fail-soft."""

    def __init__(self) -> None:
        self._effects: dict[str, Any] = {}
        self._error = ""
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
        except Exception as exc:  # pragma: no cover - platform dependent
            self._qurl = None
            self._effect_type = None
            self._error = f"QtMultimedia unavailable: {exc}"
        else:
            self._qurl = QUrl
            self._effect_type = QSoundEffect

    @property
    def available(self) -> bool:
        return self._effect_type is not None

    @property
    def error(self) -> str:
        return self._error

    def play(self, path: Path, volume: float) -> bool:
        if not self.available:
            return False
        if not path.is_file():
            self._error = f"sound asset missing: {path.name}"
            return False
        try:
            key = str(path.resolve())
            effect = self._effects.get(key)
            if effect is None:
                effect = self._effect_type()
                effect.setSource(self._qurl.fromLocalFile(key))
                self._effects[key] = effect
            effect.setVolume(max(0.0, min(1.0, float(volume))))
            effect.play()
            self._error = ""
            return True
        except Exception as exc:  # pragma: no cover - platform dependent
            self._error = str(exc)
            return False


class SoundSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> SoundSettings:
        if not self.path.is_file():
            return SoundSettings().normalized()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("sound settings must be a JSON object")
            return SoundSettings(
                master_enabled=data.get("master_enabled", True),
                master_volume=data.get("master_volume", 0.55),
                operation_enabled=data.get("operation_enabled", True),
                connection_enabled=data.get("connection_enabled", True),
                warning_enabled=data.get("warning_enabled", True),
                event_enabled=data.get("event_enabled", {}),
            ).normalized()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return SoundSettings().normalized()

    def save(self, settings: SoundSettings) -> None:
        normalized = settings.normalized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


class SoundManager:
    """Play one sound per semantic transition with per-event cooldowns."""

    def __init__(
        self,
        *,
        assets_dir: str | Path,
        settings_path: str | Path,
        backend: AudioBackend | None = None,
        clock_ms=None,
    ) -> None:
        self.assets_dir = Path(assets_dir)
        self.store = SoundSettingsStore(settings_path)
        self.settings = self.store.load()
        self._clock_ms = clock_ms or (lambda: int(time.monotonic() * 1000))
        self._last_played_ms: dict[SoundEvent, int] = {}
        self._robot_state: dict[str, dict[str, Any]] = {}
        self.last_error = ""
        self.last_event: SoundEvent | None = None
        offscreen = os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
        under_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self.backend = backend or (
            NullAudioBackend("audio suppressed for offscreen/automated validation")
            if offscreen or under_test
            else QtSoundEffectBackend()
        )

    @property
    def audio_available(self) -> bool:
        return bool(self.backend.available)

    def update_settings(self, settings: SoundSettings) -> bool:
        self.settings = settings.normalized()
        try:
            self.store.save(self.settings)
        except OSError as exc:
            self.last_error = str(exc)
            return False
        self.last_error = ""
        return True

    def play(self, event: SoundEvent | str, *, preview: bool = False, now_ms: int | None = None) -> bool:
        try:
            sound_event = event if isinstance(event, SoundEvent) else SoundEvent(str(event))
        except ValueError:
            self.last_error = f"unknown sound event: {event}"
            return False
        settings = self.settings
        spec = SOUND_SPECS[sound_event]
        if not settings.master_enabled or settings.master_volume <= 0.0:
            return False
        if not preview:
            if not settings.event_enabled.get(sound_event.value, True):
                return False
            if not self._category_enabled(spec.category):
                return False
        current_ms = int(self._clock_ms() if now_ms is None else now_ms)
        previous_ms = self._last_played_ms.get(sound_event)
        if not preview and previous_ms is not None and current_ms - previous_ms < spec.cooldown_ms:
            return False
        path = self.assets_dir / f"{sound_event.value}.wav"
        try:
            played = bool(self.backend.play(path, settings.master_volume))
        except Exception as exc:  # audio must never stop control or GUI
            self.last_error = str(exc)
            return False
        if played:
            self._last_played_ms[sound_event] = current_ms
            self.last_event = sound_event
            self.last_error = ""
        elif self.backend.error:
            self.last_error = self.backend.error
        return played

    def observe_fleet_snapshot(self, fleet: Any) -> tuple[SoundEvent, ...]:
        """Detect state edges only; repeated telemetry produces no new sound."""
        emitted: list[SoundEvent] = []
        for robot in tuple(getattr(fleet, "robots", ())):
            robot_id = str(getattr(getattr(robot, "robot_id", ""), "value", getattr(robot, "robot_id", "")))
            if not robot_id:
                continue
            current = self._state_key(robot)
            previous = self._robot_state.get(robot_id)
            self._robot_state[robot_id] = current
            if previous is None:
                continue
            candidates: list[SoundEvent] = []
            if previous["online"] != current["online"]:
                candidates.append(SoundEvent.DEVICE_CONNECTED if current["online"] else SoundEvent.DEVICE_DISCONNECTED)
            if previous["controller"] != current["controller"]:
                candidates.append(
                    SoundEvent.CONTROLLER_CONNECTED if current["controller"] else SoundEvent.CONTROLLER_DISCONNECTED
                )
            if not previous["ready"] and current["ready"]:
                candidates.append(SoundEvent.COMMUNICATION_TEST_PASS)
            if not previous["armed"] and current["armed"]:
                candidates.append(SoundEvent.ARM)
            if (previous["armed"] or previous["arm_pending"]) and current["safe"]:
                candidates.append(SoundEvent.SAFE)
            if previous["competition"] != current["competition"]:
                if current["competition"] == "READY_DISARMED":
                    candidates.append(SoundEvent.START_READY)
                elif current["competition"] == "ACTIVE":
                    candidates.append(SoundEvent.START)
                elif current["competition"] == "BLOCKED":
                    candidates.append(SoundEvent.FAIL)
            if current["fault"] and current["fault"] != previous["fault"]:
                lowered = current["fault"].lower()
                candidates.append(SoundEvent.TIMEOUT_RELOCK if "timeout" in lowered else SoundEvent.CRITICAL)
            if current["warnings"] and current["warnings"] != previous["warnings"]:
                candidates.append(SoundEvent.WARNING)
            if current["limit"] and not previous["limit"]:
                candidates.append(SoundEvent.LIMIT_SWITCH)
            for candidate in candidates:
                if candidate not in emitted:
                    self.play(candidate)
                    emitted.append(candidate)
        return tuple(emitted)

    def _category_enabled(self, category: SoundCategory) -> bool:
        if category == SoundCategory.OPERATION:
            return self.settings.operation_enabled
        if category == SoundCategory.CONNECTION:
            return self.settings.connection_enabled
        return self.settings.warning_enabled

    @staticmethod
    def _state_key(robot: Any) -> dict[str, Any]:
        connection = str(getattr(getattr(robot, "connection", ""), "value", getattr(robot, "connection", "")))
        diagnostics = tuple(getattr(robot, "diagnostic_events", ()))
        reasons = " ".join(str(getattr(item, "reason", "")) for item in diagnostics).lower()
        warnings = tuple(str(value) for value in getattr(robot, "warnings", ()))
        return {
            "online": connection == "ONLINE",
            "controller": bool(getattr(robot, "controller_connected", False)),
            "ready": bool(getattr(robot, "ready", False)),
            "armed": bool(getattr(robot, "armed", False)),
            "arm_pending": bool(getattr(robot, "arm_pending", False)),
            "safe": bool(getattr(robot, "safe", False)),
            "competition": str(getattr(robot, "competition_state", "") or ""),
            "fault": str(getattr(robot, "fault", "") or ""),
            "warnings": warnings,
            "limit": "limit" in reasons or "リミット" in reasons,
        }
