from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from hardware_profile import load_hardware_profile, validate_hardware_profile  # noqa: E402


def main() -> int:
    profile = load_hardware_profile()
    result = validate_hardware_profile(profile)
    print("=== ハードウェア構成チェック ===")
    print(profile.to_summary_text())
    print("")
    if result["errors"]:
        print("[エラー]")
        for message in result["errors"]:
            print(f"- {message}")
    else:
        print("[エラー] なし")
    if result["warnings"]:
        print("[警告]")
        for message in result["warnings"]:
            print(f"- {message}")
    else:
        print("[警告] なし")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
