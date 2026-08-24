from __future__ import annotations

import importlib.util
import platform
import sys
from typing import Any


REQUIRED_MODULES = ["PySide6", "cv2", "serial", "numpy", "yaml"]


def check_environment() -> dict[str, Any]:
    return {
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "platform": platform.platform(),
            "ok": sys.version_info >= (3, 11),
        },
        "imports": {name: check_import(name) for name in REQUIRED_MODULES},
    }


def check_import(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    return {
        "module": module_name,
        "available": spec is not None,
        "origin": spec.origin if spec and spec.origin else "",
    }
