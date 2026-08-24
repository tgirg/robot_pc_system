from __future__ import annotations

import json
from pathlib import Path

import pytest

from pc_controller.config_manager import ensure_config_files
from pc_controller.fake_autonomy_scenarios import run_fake_autonomy_scenarios


def _seed_armable_config(config_dir: Path) -> None:
    ensure_config_files(config_dir)
    path = config_dir / "vehicle_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for servo in config["servos"]:
        servo["calibrated"] = True
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_fake_autonomy_e2e_scenarios_are_safe_and_deterministic(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)

    first = run_fake_autonomy_scenarios(config_dir=str(tmp_path))
    second = run_fake_autonomy_scenarios(config_dir=str(tmp_path))

    assert first == second
    assert [result.name for result in first] == [
        "stop_on_failure",
        "retry_skip_fallback",
        "missing_node_blocks_start",
    ]
    assert all(result.passed for result in first)
    by_name = {result.name: result for result in first}
    assert by_name["stop_on_failure"].robot_id == "R2"
    assert by_name["stop_on_failure"].autonomy_state == "STOPPED"
    assert by_name["stop_on_failure"].safety_state == "SAFE"
    assert by_name["stop_on_failure"].armed is False
    assert by_name["retry_skip_fallback"].robot_id == "R1"
    assert by_name["retry_skip_fallback"].autonomy_state == "COMPLETED"
    assert by_name["retry_skip_fallback"].safety_state == "SAFE"
    assert by_name["retry_skip_fallback"].armed is False
    assert by_name["missing_node_blocks_start"].autonomy_state == "BLOCKED"
    assert by_name["missing_node_blocks_start"].armed is False


def test_fake_autonomy_unknown_scenario_is_rejected(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)

    with pytest.raises(ValueError, match="unknown Fake autonomy scenarios"):
        run_fake_autonomy_scenarios(("unknown",), config_dir=str(tmp_path))
