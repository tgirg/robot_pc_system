from __future__ import annotations

import json

from pc_controller.config_manager import ensure_config_files
from pc_controller.fake_robot_scenarios import run_scenarios


def _seed_armable_config(config_dir) -> None:
    ensure_config_files(config_dir)
    path = config_dir / "vehicle_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for servo in config["servos"]:
        servo["calibrated"] = True
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_fake_robot_scenarios_core_set(tmp_path) -> None:
    _seed_armable_config(tmp_path)
    results = run_scenarios(
        [
            "normal",
            "telemetry_timeout",
            "disconnect",
            "automatic_reconnect",
            "reboot",
            "malformed",
            "explicit_fault",
            "controller_disconnect",
            "config_rejection",
            "arm_rejection",
            "sequence_regression",
            "command_receive_stop",
        ],
        config_dir=str(tmp_path),
        trace=False,
        seed=13,
    )

    for result in results:
        assert result.passed, f"{result.name} failed: {result.fault}"
    assert all(result.final_state in {"SAFE", "NORMAL"} for result in results)
    by_name = {result.name: result for result in results}
    assert by_name["telemetry_timeout"].fault == "telemetry timeout"
    assert by_name["automatic_reconnect"].fault == "serial write failed"
    assert by_name["explicit_fault"].fault == "explicit scenario fault"
    assert by_name["sequence_regression"].fault == "telemetry sequence regression"
    assert by_name["config_rejection"].fault == "config rejected by fake injector"
    assert by_name["arm_rejection"].fault == "arm rejected by fake injector"
    assert by_name["controller_disconnect"].fault == "controller disconnected"
    assert by_name["command_receive_stop"].fault == "ESP32 command timeout"


def test_fake_robot_scenario_stale_telemetry_is_treated_as_non_fatal(tmp_path) -> None:
    _seed_armable_config(tmp_path)
    results = run_scenarios(["stale_telemetry"], config_dir=str(tmp_path), trace=False, seed=13)
    result = results[0]
    assert result.passed
    assert result.final_state == "NORMAL"
    assert result.final_armed is True
    assert result.fault is None
