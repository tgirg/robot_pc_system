from __future__ import annotations

import json
from pathlib import Path

from .hardware_check_result import HardwareCheckResult


class HardwareCheckLogger:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.output_dir = self.project_root / "logs" / "hardware_checks"

    def save(self, result: HardwareCheckResult) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_stamp = result.timestamp.replace("-", "").replace(":", "").replace(" ", "_")
        json_path = self.output_dir / f"hardware_check_{safe_stamp}.json"
        txt_path = self.output_dir / f"hardware_check_{safe_stamp}.txt"

        with json_path.open("w", encoding="utf-8") as file:
            json.dump(result.to_dict(), file, ensure_ascii=False, indent=2)
        with txt_path.open("w", encoding="utf-8") as file:
            file.write(result.to_text())
        return json_path, txt_path

    def latest_text_file(self) -> Path | None:
        if not self.output_dir.exists():
            return None
        files = sorted(self.output_dir.glob("hardware_check_*.txt"), key=lambda p: p.stat().st_mtime)
        return files[-1] if files else None
