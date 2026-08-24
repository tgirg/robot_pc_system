from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from noise_eval import (  # noqa: E402
    build_motor_test_line,
    build_servo_deg_line,
    classify_motor_noise,
    classify_servo_noise,
    format_result_text,
    summarize_records,
)


def _telemetry(counts, rpm, pwm, servo=None, fault_flags=0):
    return {
        "v": 1,
        "type": "telemetry",
        "encoder_count": counts,
        "wheel_rpm": rpm,
        "motor_pwm": pwm,
        "servo_deg": servo or [0.0, 0.0, 0.0, 0.0],
        "fault_flags": fault_flags,
    }


def _rx(message, phase="test"):
    return {"phase": phase, "dir": "rx", "line": json.dumps(message), "message": message}


def test_noise_eval_builds_v29_debug_lines() -> None:
    motor = json.loads(build_motor_test_line(1, 40))
    servo = json.loads(build_servo_deg_line(1, 180))

    assert motor == {"v": 1, "type": "debug", "action": "motor_test", "wheel": 1, "pwm": 40, "direction": True}
    assert servo == {"v": 1, "type": "debug", "action": "servo_deg", "wheel": 1, "value": 135.0}


def test_noise_eval_passes_when_only_active_wheel_moves() -> None:
    records = [
        _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 0, 40, 0])),
        _rx(_telemetry([0, 0, 53405, 0], [0.0, 0.0, 48.34, 0.0], [0, 0, 40, 0])),
    ]

    summary = summarize_records(records)
    classification = classify_motor_noise(summary, active_wheel=2, requested_pwm=40)

    assert summary["count_delta"] == [0, 0, 53405, 0]
    assert classification["status"] == "pass"
    assert classification["rotation_confirmed"] is True
    assert classification["stationary_count_noise"] == 0


def test_noise_eval_flags_pwm_without_rotation_as_unconfirmed() -> None:
    records = [
        _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 40, 0, 0])),
        _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 40, 0, 0])),
    ]

    summary = summarize_records(records)
    classification = classify_motor_noise(summary, active_wheel=1, requested_pwm=40)

    assert classification["status"] == "rotation_unconfirmed"
    assert classification["pwm_reported"] is True
    assert classification["rotation_confirmed"] is False
    assert "PWM" in classification["reason"]


def test_noise_eval_flags_stationary_encoder_delta_as_noise() -> None:
    records = [
        _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 40, 0, 0])),
        _rx(_telemetry([0, 1400, 5, 0], [0.0, 8.0, 0.0, 0.0], [0, 40, 0, 0])),
    ]

    summary = summarize_records(records)
    classification = classify_motor_noise(summary, active_wheel=1, requested_pwm=40)

    assert classification["status"] == "noise_observed"
    assert classification["stationary_count_noise"] == 5


def test_noise_eval_servo_only_detects_encoder_noise() -> None:
    records = [
        _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 0, 0, 0])),
        _rx(_telemetry([0, 2, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 0, 0, 0])),
    ]

    summary = summarize_records(records)
    classification = classify_servo_noise(summary)

    assert classification["status"] == "noise_observed"
    assert classification["max_count_noise"] == 2


def test_noise_eval_formats_rotation_unconfirmed_result() -> None:
    summary = summarize_records(
        [
            _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 40, 0, 0])),
            _rx(_telemetry([0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], [0, 40, 0, 0])),
        ]
    )
    classification = classify_motor_noise(summary, active_wheel=1, requested_pwm=40)

    text = format_result_text(
        {
            "mode": "combined",
            "port": "COM7",
            "wheel": 1,
            "pwm": 40,
            "log_path": "logs/example.jsonl",
            "summary": summary,
            "classification": classification,
        }
    )

    assert "FR" in text
    assert "回転未確認" in text
    assert "rotation_confirmed=False" in text
