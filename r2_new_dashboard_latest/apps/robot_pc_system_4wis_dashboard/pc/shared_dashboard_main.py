"""Explicit Fake-only entrypoint for the shared read-only dashboard."""

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
from pc_controller.gui_runtime import FakeFleetDashboardRuntime  # noqa: E402

from main_ui import MainWindow  # noqa: E402
from shared_runtime_binding import QtFleetDashboardBinding  # noqa: E402
from widgets.ui_helpers import (  # noqa: E402
    install_input_wheel_guard,
    install_qt_font_warning_filter,
    make_font,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fake ESP32 shared dashboard (read-only, no legacy Serial owner)"
    )
    parser.add_argument(
        "--robot",
        required=True,
        choices=[robot.value for robot in RobotId],
        help="explicit robot binding; the other robot remains UNBOUND/OFFLINE",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=PROJECT_ROOT / "config",
        help="pc_controller configuration directory",
    )
    parser.add_argument(
        "--node-manifest",
        type=Path,
        default=PROJECT_ROOT / "config" / "node_manifest.json",
        help="required/optional node manifest",
    )
    parser.add_argument("--interval-ms", type=int, default=100, help="snapshot interval (20-5000 ms)")
    parser.add_argument("--fake-trace", action="store_true", help="print protocol-faithful VirtualSerial trace")
    parser.add_argument(
        "--competition-log",
        type=Path,
        default=None,
        help="explicit local Competition .jsonl/.ndjson to validate and display read-only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    install_qt_font_warning_filter()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("F3RC Fake共有ダッシュボード")
    app.setApplicationDisplayName("F3RC Fake共有ダッシュボード")
    app.setFont(make_font("Yu Gothic UI", 10))
    install_input_wheel_guard(app)
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId(args.robot),
        config_dir=args.config_dir,
        node_manifest=args.node_manifest,
        fake_trace=bool(args.fake_trace),
    )
    window = MainWindow(shared_runtime_only=True)
    if args.competition_log is not None:
        window.logs_widget.set_competition_log_path(args.competition_log)
    binding = QtFleetDashboardBinding(window, runtime, interval_ms=int(args.interval_ms))
    window.shared_runtime_binding = binding

    def fail(message: str) -> None:
        print(f"Fake dashboard runtime failed: {message}", file=sys.stderr, flush=True)
        app.exit(1)

    binding.failed.connect(fail)
    try:
        binding.start()
    except Exception as exc:
        runtime.close()
        print(f"Fake dashboard startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
    window.show()
    exit_code = int(app.exec())
    binding.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
