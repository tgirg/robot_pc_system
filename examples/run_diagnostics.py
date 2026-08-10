from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from diagnostics.diagnostics_report import build_report, print_japanese_summary  # noqa: E402


def main() -> None:
    print("robot_pc_system 診断を実行します。")
    report = build_report()
    print_japanese_summary(report)


if __name__ == "__main__":
    main()
