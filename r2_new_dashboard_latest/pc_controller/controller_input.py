"""pygame controller input mapping."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from math import copysign
from typing import Mapping

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
except ImportError:  # pragma: no cover - optional runtime package
    pygame = None


@dataclass(frozen=True)
class ControllerState:
    connected: bool
    name: str
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0
    arm_pressed: bool = False
    safe_pressed: bool = False


def correct_controller_axis(value: float, invert: bool, deadzone: float) -> float:
    """Apply the runtime controller inversion/deadzone curve to one raw axis."""
    value = max(-1.0, min(1.0, -value if invert else value))
    deadzone = max(0.0, min(0.95, deadzone))
    abs_value = abs(value)
    if abs_value <= deadzone:
        return 0.0
    normalized = (abs_value - deadzone) / (1.0 - deadzone)
    normalized = 0.55 * normalized + 0.45 * normalized * normalized * normalized
    return copysign(normalized, value)


def transform_for_logical_front(vx: float, vy: float, logical_front: object) -> tuple[float, float]:
    """Rotate a logical translation command into the machine body frame.

    A front/rear change reverses both translation axes while the caller keeps
    omega unchanged. Missing legacy configuration is FRONT; an explicit
    invalid value is rejected so the control path can fail SAFE.
    """
    front = "FRONT" if logical_front is None else str(logical_front).strip().upper()
    if front == "FRONT":
        return float(vx), float(vy)
    if front == "RIGHT":
        return float(vy), -float(vx)
    if front == "REAR":
        return -float(vx), -float(vy)
    if front == "LEFT":
        return -float(vy), float(vx)
    raise ValueError(f"unsupported logical front: {logical_front}")


# Backward-compatible private alias for any existing diagnostic callers.
_axis = correct_controller_axis


class PygameController:
    """Read a joystick through pygame using JSON-configurable axes/buttons."""

    def __init__(self, mapping: Mapping[str, object]) -> None:
        if pygame is None:
            raise RuntimeError("pygame is required for controller input")
        self.mapping = mapping
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self._connect_first_joystick()

    def _connect_first_joystick(self) -> None:
        pygame.joystick.quit()
        pygame.joystick.init()
        self.joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() else None
        if self.joystick is not None:
            self.joystick.init()

    def read(self) -> ControllerState:
        """Read the current joystick state."""
        pygame.event.pump()
        if self.joystick is None:
            self._connect_first_joystick()
        if self.joystick is None:
            return ControllerState(False, "")
        deadzone = float(self.mapping.get("deadzone", 0.1))

        def axis(index_key: str, invert_key: str) -> float:
            index = int(self.mapping.get(index_key, 0))
            if index >= self.joystick.get_numaxes():
                return 0.0
            return correct_controller_axis(
                float(self.joystick.get_axis(index)),
                bool(self.mapping.get(invert_key, False)),
                deadzone,
            )

        arm_buttons = [int(value) for value in self.mapping.get("arm_buttons", [])]
        arm_pressed = bool(arm_buttons) and all(
            button < self.joystick.get_numbuttons() and self.joystick.get_button(button)
            for button in arm_buttons
        )
        safe_button = int(self.mapping.get("safe_button", -1))
        safe_pressed = safe_button >= 0 and safe_button < self.joystick.get_numbuttons() and bool(
            self.joystick.get_button(safe_button)
        )
        return ControllerState(
            connected=True,
            name=self.joystick.get_name(),
            vx=axis("axis_vx", "invert_vx"),
            vy=axis("axis_vy", "invert_vy"),
            omega=axis("axis_omega", "invert_omega"),
            arm_pressed=arm_pressed,
            safe_pressed=safe_pressed,
        )


def list_controllers() -> list[dict[str, object]]:
    """Return visible pygame joystick devices."""
    if pygame is None:
        raise RuntimeError("pygame is required for controller input")
    pygame.init()
    pygame.joystick.init()
    devices: list[dict[str, object]] = []
    for index in range(pygame.joystick.get_count()):
        joystick = pygame.joystick.Joystick(index)
        joystick.init()
        devices.append(
            {
                "index": index,
                "name": joystick.get_name(),
                "axes": joystick.get_numaxes(),
                "buttons": joystick.get_numbuttons(),
                "hats": joystick.get_numhats(),
            }
        )
    return devices


def print_controller_debug(seconds: float = 15.0) -> None:
    """Print raw pygame axes and buttons for a short controller debug session."""
    if pygame is None:
        raise RuntimeError("pygame is required for controller input")
    pygame.init()
    pygame.joystick.init()
    if not pygame.joystick.get_count():
        print("controllers: 0", flush=True)
        return

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(
        f"controller debug: {joystick.get_name()} "
        f"axes={joystick.get_numaxes()} buttons={joystick.get_numbuttons()} hats={joystick.get_numhats()}",
        flush=True,
    )
    print("move sticks and press buttons now", flush=True)

    deadline = time.monotonic() + max(0.1, seconds)
    last_axes: list[float] | None = None
    last_buttons: list[int] | None = None
    last_hats: list[tuple[int, int]] | None = None
    while time.monotonic() < deadline:
        pygame.event.pump()
        axes = [round(float(joystick.get_axis(index)), 3) for index in range(joystick.get_numaxes())]
        buttons = [int(joystick.get_button(index)) for index in range(joystick.get_numbuttons())]
        hats = [joystick.get_hat(index) for index in range(joystick.get_numhats())]
        axes_changed = last_axes is None or any(abs(axes[index] - last_axes[index]) >= 0.05 for index in range(len(axes)))
        buttons_changed = buttons != last_buttons
        hats_changed = hats != last_hats
        if axes_changed or buttons_changed or hats_changed:
            pressed = [index for index, value in enumerate(buttons) if value]
            print(f"axes={axes} pressed={pressed} hats={hats}", flush=True)
            last_axes = axes
            last_buttons = buttons
            last_hats = hats
        time.sleep(0.05)
