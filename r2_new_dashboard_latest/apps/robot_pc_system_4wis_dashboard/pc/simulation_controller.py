from __future__ import annotations

import json
import os
from dataclasses import dataclass
from math import copysign
from pathlib import Path
from typing import Any, Iterable, Mapping

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

try:
    import pygame
except ImportError:  # pragma: no cover - optional runtime package
    pygame = None


@dataclass(frozen=True)
class SimulationControllerState:
    connected: bool
    name: str = ""
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0
    safe_pressed: bool = False
    message: str = ""


def load_controller_mapping() -> dict[str, Any]:
    path = _project_root_from_here() / "config" / "controller_mapping.json"
    default = {
        "axis_vx": 1,
        "axis_vy": 0,
        "axis_omega": 2,
        "invert_vx": True,
        "invert_vy": True,
        "invert_omega": True,
        "deadzone": 0.12,
        "safe_button": 6,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(data, dict):
        return default
    merged = default.copy()
    merged.update(data)
    return merged


def _project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "controller_mapping.json").exists() and (parent / "pc_controller").exists():
            return parent
    return here.parents[2] if len(here.parents) > 2 else here.parents[-1]


def normalize_axis(value: float, invert: bool, deadzone: float) -> float:
    value = max(-1.0, min(1.0, -value if invert else value))
    deadzone = max(0.0, min(0.95, deadzone))
    abs_value = abs(value)
    if abs_value <= deadzone:
        return 0.0
    normalized = (abs_value - deadzone) / (1.0 - deadzone)
    normalized = 0.55 * normalized + 0.45 * normalized * normalized * normalized
    return copysign(normalized, value)


def keyboard_state_from_keys(active_keys: Iterable[str], speed: float = 0.65, turn: float = 0.65) -> SimulationControllerState:
    keys = {str(key).lower() for key in active_keys}
    speed = max(0.0, min(1.0, float(speed)))
    turn = max(0.0, min(1.0, float(turn)))

    vx = 0.0
    if keys & {"w", "up"}:
        vx += speed
    if keys & {"s", "down"}:
        vx -= speed

    vy = 0.0
    if keys & {"a"}:
        vy += speed
    if keys & {"d"}:
        vy -= speed

    omega = 0.0
    if keys & {"q", "left", "arrow_left"}:
        omega += turn
    if keys & {"e", "right", "arrow_right"}:
        omega -= turn

    return SimulationControllerState(
        connected=True,
        name="Keyboard",
        vx=vx,
        vy=vy,
        omega=omega,
        message="keyboard",
    )


class SimulationControllerInput:
    def __init__(self, mapping: Mapping[str, Any] | None = None, enabled: bool = True) -> None:
        self.mapping = dict(mapping or load_controller_mapping())
        self.enabled = bool(enabled)
        self.joystick = None
        self.last_error = ""
        if pygame is None:
            self.last_error = "pygame未導入"
            return
        try:
            pygame.init()
            pygame.joystick.init()
            self._connect_first_joystick()
        except Exception as exc:  # pragma: no cover - hardware/runtime dependent
            self.last_error = str(exc)
            self.joystick = None

    def read(self) -> SimulationControllerState:
        if not self.enabled:
            return SimulationControllerState(False, message="コントローラ入力OFF")
        if pygame is None:
            return SimulationControllerState(False, message="pygame未導入")
        try:
            pygame.event.pump()
            if self.joystick is None:
                self._connect_first_joystick()
            if self.joystick is None:
                return SimulationControllerState(False, message="未接続")
            deadzone = float(self.mapping.get("deadzone", 0.12))
            safe_button = int(self.mapping.get("safe_button", -1))
            safe_pressed = safe_button >= 0 and safe_button < self.joystick.get_numbuttons() and bool(
                self.joystick.get_button(safe_button)
            )
            return SimulationControllerState(
                connected=True,
                name=self.joystick.get_name(),
                vx=self._axis("axis_vx", "invert_vx", deadzone),
                vy=self._axis("axis_vy", "invert_vy", deadzone),
                omega=self._axis("axis_omega", "invert_omega", deadzone),
                safe_pressed=safe_pressed,
                message="接続中",
            )
        except Exception as exc:  # pragma: no cover - hardware/runtime dependent
            self.last_error = str(exc)
            self.joystick = None
            return SimulationControllerState(False, message=f"読取エラー: {exc}")

    def reconnect(self) -> SimulationControllerState:
        if pygame is None:
            return SimulationControllerState(False, message="pygame未導入")
        try:
            self._connect_first_joystick()
        except Exception as exc:  # pragma: no cover - hardware/runtime dependent
            self.last_error = str(exc)
            self.joystick = None
        return self.read()

    def _connect_first_joystick(self) -> None:
        if pygame is None:
            return
        pygame.joystick.quit()
        pygame.joystick.init()
        self.joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None
        if self.joystick is not None:
            self.joystick.init()

    def _axis(self, index_key: str, invert_key: str, deadzone: float) -> float:
        if self.joystick is None:
            return 0.0
        index = int(self.mapping.get(index_key, 0))
        if index < 0 or index >= self.joystick.get_numaxes():
            return 0.0
        return normalize_axis(float(self.joystick.get_axis(index)), bool(self.mapping.get(invert_key, False)), deadzone)
