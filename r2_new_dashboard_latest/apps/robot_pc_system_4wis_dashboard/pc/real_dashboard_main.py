"""Explicit R2 real-hardware entrypoint for the new shared dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc_controller.autonomy import RobotId  # noqa: E402
from pc_controller.gui_runtime import RealFleetDashboardRuntime  # noqa: E402

from main_ui import MainWindow  # noqa: E402
from shared_runtime_binding import QtFleetDashboardBinding  # noqa: E402
from widgets.ui_helpers import (  # noqa: E402
    install_input_wheel_guard,
    install_qt_font_warning_filter,
    make_font,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R2 real robot through the new shared dashboard"
    )
    parser.add_argument(
        "--robot",
        choices=[RobotId.R2.value],
        default=RobotId.R2.value,
        help="physical binding; first-motion real output is currently R2 only",
    )
    parser.add_argument("--port", default=None, help="serial port such as COM7; omit to auto-discover")
    parser.add_argument("--node-role", default="drive", help="auto-discovery role")
    parser.add_argument("--node-id", default=None, help="optional exact serial node_id")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=PROJECT_ROOT / "config",
        help="R2 ControllerApp configuration directory",
    )
    parser.add_argument(
        "--node-manifest",
        type=Path,
        default=PROJECT_ROOT / "config" / "node_manifest.json",
        help="required/optional R2 node manifest",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=50,
        help="controller/snapshot interval (20-100 ms for real motion)",
    )
    parser.add_argument(
        "--enable-motion",
        action="store_true",
        help="explicitly allow controller ARM and drive output; default is real-serial read-only",
    )
    parser.add_argument(
        "--max-pwm",
        type=int,
        default=RealFleetDashboardRuntime.FIRST_MOTION_MAX_PWM,
        help="first-motion PWM clamp (1-120)",
    )
    parser.add_argument("--discovery-timeout", type=float, default=1.2)
    parser.add_argument("--reconnect-interval", type=float, default=1.0)
    parser.add_argument("--reconnect-handshake-timeout", type=float, default=2.0)
    parser.add_argument(
        "--competition-log",
        type=Path,
        default=None,
        help="explicit local Competition .jsonl/.ndjson to display read-only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if int(args.interval_ms) < 20 or int(args.interval_ms) > 100:
        print("R2 dashboard startup failed: --interval-ms must be between 20 and 100", file=sys.stderr)
        return 2

    install_qt_font_warning_filter()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("F3RC R2 実機ダッシュボード")
    app.setApplicationDisplayName("F3RC R2 実機ダッシュボード")
    app.setFont(make_font("Yu Gothic UI", 10))
    install_input_wheel_guard(app)
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        runtime = RealFleetDashboardRuntime.create(
            robot_id=RobotId(args.robot),
            config_dir=args.config_dir,
            node_manifest=args.node_manifest,
            port=args.port,
            node_role=args.node_role,
            node_id=args.node_id,
            discovery_timeout=float(args.discovery_timeout),
            reconnect_interval=float(args.reconnect_interval),
            reconnect_handshake_timeout=float(args.reconnect_handshake_timeout),
            motion_enabled=bool(args.enable_motion),
            max_pwm=int(args.max_pwm),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"R2 dashboard configuration failed: {exc}", file=sys.stderr, flush=True)
        return 2

    window = MainWindow(
        shared_runtime_only=True,
        shared_runtime_mode="real",
        shared_runtime_max_pwm=runtime.max_pwm,
        shared_runtime_config_dir=args.config_dir,
    )
    window.lock_shared_runtime_robot(RobotId.R2.value)
    if args.competition_log is not None:
        window.logs_widget.set_competition_log_path(args.competition_log)
    binding = QtFleetDashboardBinding(window, runtime, interval_ms=int(args.interval_ms))
    window.shared_runtime_binding = binding

    def fail(message: str) -> None:
        print(f"R2 dashboard runtime failed: {message}", file=sys.stderr, flush=True)
        app.exit(1)

    binding.failed.connect(fail)
    try:
        binding.start()
    except Exception as exc:
        runtime.close()
        print(f"R2 dashboard startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
    window.show()
    exit_code = int(app.exec())
    binding.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
