from __future__ import annotations

import json
from pathlib import Path

from pc_controller.config_manager import ensure_config_files
from pc_controller.fake_competition_demo import run_fake_competition


def _seed_armable_config(config_dir: Path) -> None:
    ensure_config_files(config_dir)
    path = config_dir / "vehicle_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for servo in config["servos"]:
        servo["calibrated"] = True
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_fake_competition_e2e_finalizes_safe_log_and_outbox(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    _seed_armable_config(config_dir)

    result = run_fake_competition(
        config_dir=str(config_dir),
        output_dir=tmp_path / "run",
        session_id="test-session",
    )

    assert result.passed is True
    assert result.competition_state == "POST_COMPETITION"
    assert result.autonomy_state == "COMPLETED"
    assert result.safety_state == "SAFE"
    assert result.armed is False
    assert result.motor_pwm == (0, 0, 0, 0)
    assert result.log_path.is_file()
    assert result.bundle_dir.is_dir()
    assert result.event_count >= 7
    records = [json.loads(line) for line in result.log_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "session_finalized"
    manifest = json.loads((result.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sync_status"] == "AWAITING_REMOTE_CONFIGURATION"
    assert manifest["remote_transfer_performed"] is False


def test_fake_competition_session_id_cannot_escape_output_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "run"
    _seed_armable_config(config_dir)

    result = run_fake_competition(
        config_dir=str(config_dir),
        output_dir=output_dir,
        session_id="../escape-attempt",
    )

    assert result.passed is True
    assert result.log_path.parent == output_dir
    assert not (tmp_path / "escape-attempt.jsonl").exists()
