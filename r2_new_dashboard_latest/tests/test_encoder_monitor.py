from __future__ import annotations

import argparse

import pytest

from pc_controller.encoder_monitor import extract_encoder_sample, format_sample, parse_wheel


def test_parse_wheel_accepts_names_and_indices() -> None:
    assert parse_wheel("FL") == 0
    assert parse_wheel("fr") == 1
    assert parse_wheel("RL") == 2
    assert parse_wheel("3") == 3


def test_parse_wheel_rejects_unknown_value() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_wheel("rear")


def test_extract_encoder_sample_filters_one_wheel() -> None:
    sample = extract_encoder_sample(
        {
            "v": 1,
            "type": "telemetry",
            "state": "NORMAL",
            "armed": True,
            "encoder_count": [10, 20, 30, 40],
            "wheel_rpm": [1.0, 2.0, 3.0, 4.0],
            "motor_pwm": [11, 22, 33, 44],
            "servo_deg": [5.0, 6.0, 7.0, 8.0],
            "fault_flags": 0,
        },
        wheel=2,
        timestamp_s=1.25,
        previous_count=25,
    )

    assert sample is not None
    assert sample.count == 30
    assert sample.delta_count == 5
    assert sample.rpm == pytest.approx(3.0)
    assert sample.pwm == 33
    assert sample.servo_deg == pytest.approx(7.0)


def test_format_sample_contains_selected_fields() -> None:
    sample = extract_encoder_sample(
        {
            "v": 1,
            "type": "telemetry",
            "state": "SAFE",
            "armed": False,
            "encoder_count": [100, 200, 300, 400],
            "wheel_rpm": [0.0, 0.0, 12.5, 0.0],
            "motor_pwm": [0, 0, 80, 0],
            "servo_deg": [0.0, 0.0, -4.5, 0.0],
            "fault_flags": 32,
        },
        wheel=2,
        timestamp_s=0.5,
        previous_count=None,
    )

    assert sample is not None
    text = format_sample(sample, "RL")
    assert "RL" in text
    assert "count=       +300" in text
    assert "rpm=  +12.50" in text
    assert "pwm=  +80" in text
    assert "fault=32" in text
