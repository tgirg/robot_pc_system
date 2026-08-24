# Integration Notes

Source: https://github.com/tgirg/robot_pc_system
Imported revision: `783cfb5 Initial robot PC dashboard`
Imported date: 2026-08-12

This app is included as an optional PySide6 dashboard for the robot project.
It is intentionally kept separate from the existing `pc_controller` package.
This copied variant adds a `4WIS` tab for four independent steering angles, live v29 telemetry display, controller/keyboard-driven simulation without requiring ESP32 connection, and guarded one-shot v29 real-drive messages.

Important protocol note:

- Existing real-drive path: `run-pc-controller.cmd` sends v29 JSON Lines messages to `esp32_firmware/esp32_firmware.ino`.
- This dashboard's original drive path sends text commands such as `DRIVE VEL 100 100`.
- The `4WIS` tab now has a v29 adapter for explicit `ARM`, one-shot `drive`, zero-drive, and `DISARM`.
- Do not treat slider movement as live control. The dashboard sends v29 real-drive only from the explicit `4WIS` real-send buttons, and only after ESP32 real connection plus `arm_ack`.

Local defaults changed for this workspace:

- `pc/config.yaml` title changed to `F3RC2026 4WIS統合ロボットPCダッシュボード`.
- USB/serial defaults changed from `COM6` to `COM7`.
- Mock/simulation remain enabled so the dashboard starts without driving real hardware.
- Simulation keyboard input is enabled by default: `W/S` forward/back, `A/D` strafe, and `Q/E` or left/right arrow rotate. It does not send ESP32 commands.
- 4WIS real-send defaults to v29 normal ARM and `max_pwm: 120` in `pc/config.yaml`.
- `config/hardware_profile.yaml` records the current v29 4WIS mapping limitation.

Root launchers:

- `setup-robot-dashboard.cmd` creates `C:/robot_venvs/robot_pc_dashboard` and installs dashboard dependencies.
- `run-robot-dashboard.cmd` starts the dashboard from the project root.
- `run-robot-dashboard-4wis.cmd` starts this copied 4WIS dashboard from the project root.
- `setup-robot-dashboard-4wis.cmd` points setup at this copied app; `run-robot-dashboard-4wis.cmd` calls it automatically when the dashboard venv is missing or broken.
- `run-fake-robot-dashboard.cmd --robot R1|R2` is the explicit read-only shared runtime path. It owns one protocol-faithful Fake `ControllerApp`, requires an explicit robot binding, and starts `MainWindow` without any legacy Serial, COM enumeration, camera, or command tabs. It never ARM-s automatically.
