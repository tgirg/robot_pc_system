"""Minimal pygame dashboard."""

from __future__ import annotations

from typing import Mapping

try:
    import pygame
except ImportError:  # pragma: no cover - optional runtime package
    pygame = None


class Dashboard:
    """Draw status and telemetry pages."""

    def __init__(self) -> None:
        if pygame is None:
            raise RuntimeError("pygame is required for GUI mode")
        self.screen = pygame.display.set_mode((1100, 720))
        pygame.display.set_caption("MCB44 4WIS Controller")
        self.font = pygame.font.SysFont("consolas", 22)
        self.small = pygame.font.SysFont("consolas", 18)

    def draw(self, status: Mapping[str, object], telemetry: Mapping[str, object] | None) -> None:
        """Render one dashboard frame."""
        self.screen.fill((18, 20, 24))
        lines = [
            f"mode={status.get('mode')} armed={status.get('armed')} serial={status.get('serial')} controller={status.get('controller')}",
            f"vx={status.get('vx', 0): .2f} vy={status.get('vy', 0): .2f} omega={status.get('omega', 0): .2f}",
            f"fault={status.get('fault') or '-'}",
        ]
        y = 24
        for line in lines:
            self.screen.blit(self.font.render(line, True, (235, 238, 242)), (24, y))
            y += 34

        if telemetry:
            labels = ("FL", "FR", "RL", "RR")
            enc = telemetry.get("encoder_count", [0, 0, 0, 0])
            rpm = telemetry.get("wheel_rpm", [0.0, 0.0, 0.0, 0.0])
            pwm = telemetry.get("motor_pwm", [0, 0, 0, 0])
            servo = telemetry.get("servo_deg", [0.0, 0.0, 0.0, 0.0])
            y += 20
            for index, label in enumerate(labels):
                line = (
                    f"{label} servo={float(servo[index]):7.2f}deg "
                    f"rpm={float(rpm[index]):8.2f} pwm={int(pwm[index]):5d} enc={int(enc[index]):9d}"
                )
                self.screen.blit(self.small.render(line, True, (205, 215, 225)), (24, y))
                y += 28
        pygame.display.flip()

