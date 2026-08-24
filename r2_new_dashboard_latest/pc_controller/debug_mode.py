"""Debug command builders."""

from __future__ import annotations

from .protocol import debug_message


def motor_test_command(wheel: int, pwm: int, forward: bool = True) -> dict[str, object]:
    """Build a low-power momentary motor test command."""
    return debug_message("motor_test", wheel=wheel, pwm=abs(pwm), direction=forward)


def motor_stop_command() -> dict[str, object]:
    """Build a motor stop debug command."""
    return debug_message("motor_stop", wheel=0)


def servo_pulse_command(wheel: int, pulse_us: int) -> dict[str, object]:
    """Build a one-servo pulse command."""
    return debug_message("servo_us", wheel=wheel, pulse_us=pulse_us)


def encoder_zero_command(wheel: int) -> dict[str, object]:
    """Build an encoder zeroing command."""
    return debug_message("encoder_zero", wheel=wheel)

