from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


ARDUINO_CLI_CANDIDATES = [
    Path(r"C:\Program Files\Arduino CLI\arduino-cli.exe"),
    Path(r"C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
    Path(r"C:\Program Files (x86)\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
]


@dataclass
class ArduinoCliResult:
    success: bool
    command: list[str]
    stdout: str
    stderr: str
    return_code: int
    started_at: str
    finished_at: str
    elapsed_seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def find_arduino_cli() -> str | None:
    from_path = shutil.which("arduino-cli")
    if from_path:
        return from_path
    for candidate in ARDUINO_CLI_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def _run_command(command: list[str], timeout: int = 180) -> ArduinoCliResult:
    started = time.time()
    started_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started))
    try:
        completed = subprocess.run(
            command,
            cwd=project_root(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        return_code = 127
        stdout = ""
        stderr = str(exc)
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nタイムアウトしました。"
    finished = time.time()
    return ArduinoCliResult(
        success=return_code == 0,
        command=command,
        stdout=stdout,
        stderr=stderr,
        return_code=return_code,
        started_at=started_text,
        finished_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished)),
        elapsed_seconds=round(finished - started, 2),
    )


def _cli_or_error() -> str:
    cli = find_arduino_cli()
    if not cli:
        raise FileNotFoundError(
            "arduino-cli が見つかりません。PATH、C:\\Program Files\\Arduino CLI\\arduino-cli.exe、"
            "または Arduino IDE 付属の arduino-cli.exe を確認してください。"
        )
    return cli


def run_arduino_version() -> ArduinoCliResult:
    return _run_command([_cli_or_error(), "version"], timeout=30)


def run_board_list() -> ArduinoCliResult:
    return _run_command([_cli_or_error(), "board", "list"], timeout=60)


def run_core_list() -> ArduinoCliResult:
    return _run_command([_cli_or_error(), "core", "list"], timeout=60)


def compile_drive_controller(fqbn: str) -> ArduinoCliResult:
    return compile_sketch("drive_controller", fqbn)


def upload_drive_controller(port: str, fqbn: str) -> ArduinoCliResult:
    return upload_sketch("drive_controller", port, fqbn)


def sketch_path(sketch_name: str) -> str:
    safe_name = str(sketch_name).strip().replace("/", "").replace("\\", "")
    if not safe_name:
        safe_name = "drive_controller"
    app_sketch = project_root() / "esp32" / safe_name
    if app_sketch.exists():
        return str(app_sketch)
    workspace_sketch = workspace_root() / safe_name
    if workspace_sketch.exists():
        return str(workspace_sketch)
    return str(app_sketch)


def _safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip() or "default")


def build_cache_path(sketch_name: str, fqbn: str) -> Path:
    safe_sketch = _safe_cache_name(Path(sketch_path(sketch_name)).name)
    safe_fqbn = _safe_cache_name(fqbn)
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local_app_data / "robot_pc_system" / "arduino_cache" / f"{safe_sketch}_{safe_fqbn}"


def has_cached_build(sketch_name: str, fqbn: str) -> bool:
    cache = build_cache_path(sketch_name, fqbn)
    return cache.exists() and any(cache.glob("*.bin"))


def compile_sketch(sketch_name: str, fqbn: str) -> ArduinoCliResult:
    cache = build_cache_path(sketch_name, fqbn)
    cache.mkdir(parents=True, exist_ok=True)
    return _run_command(
        [_cli_or_error(), "compile", "--fqbn", fqbn, "--build-path", str(cache), sketch_path(sketch_name)],
        timeout=240,
    )


def upload_sketch(sketch_name: str, port: str, fqbn: str) -> ArduinoCliResult:
    return _run_command([_cli_or_error(), "upload", "-p", port, "--fqbn", fqbn, sketch_path(sketch_name)], timeout=240)


def upload_cached_sketch(sketch_name: str, port: str, fqbn: str, upload_speed: str = "1500000") -> ArduinoCliResult:
    cache = build_cache_path(sketch_name, fqbn)
    command = [_cli_or_error(), "upload", "-p", port, "--fqbn", fqbn, "--input-dir", str(cache)]
    if upload_speed:
        command.extend(["--upload-property", f"upload.speed={upload_speed}"])
    command.append(sketch_path(sketch_name))
    return _run_command(command, timeout=180)
