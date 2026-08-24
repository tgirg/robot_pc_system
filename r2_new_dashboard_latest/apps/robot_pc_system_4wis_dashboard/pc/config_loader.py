from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PC_DIR.parent
DEFAULT_CONFIG_PATH = PC_DIR / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def cfg_section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    return value if isinstance(value, dict) else {}


def save_config(config: dict[str, Any], path: str | Path | None = None) -> None:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)
