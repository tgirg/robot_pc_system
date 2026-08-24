from __future__ import annotations

import pytest

from pc_controller.kinematics import calculate_wheel_vectors


def cfg(max_speed: float = 10.0) -> dict[str, object]:
    return {
        "motion": {
            "wheelbase_m": 0.4,
            "track_width_m": 0.4,
            "wheel_diameter_m": 0.1,
            "max_wheel_rpm": 10000.0,
            "max_linear_speed_mps": max_speed,
        }
    }


def angles(vectors):
    return [round(vector.angle_deg, 3) for vector in vectors]


def speeds(vectors):
    return [round(vector.speed_mps, 3) for vector in vectors]


def test_forward_all_wheels_forward_same_speed() -> None:
    vectors = calculate_wheel_vectors(1.0, 0.0, 0.0, cfg())
    assert angles(vectors) == [0.0, 0.0, 0.0, 0.0]
    assert speeds(vectors) == [1.0, 1.0, 1.0, 1.0]


def test_sideways_left_all_wheels_left() -> None:
    vectors = calculate_wheel_vectors(0.0, 1.0, 0.0, cfg())
    assert angles(vectors) == [90.0, 90.0, 90.0, 90.0]


def test_pure_rotation_is_tangent_to_center() -> None:
    vectors = calculate_wheel_vectors(0.0, 0.0, 1.0, cfg())
    assert angles(vectors) == [135.0, 45.0, -135.0, -45.0]
    assert len(set(speeds(vectors))) == 1


def test_combined_motion_normalizes_ratio() -> None:
    vectors = calculate_wheel_vectors(2.0, 0.0, 1.0, cfg(max_speed=1.0))
    assert max(vector.speed_mps for vector in vectors) == pytest.approx(1.0)
    assert vectors[1].speed_mps > vectors[0].speed_mps


def test_zero_input_keeps_last_angles() -> None:
    vectors = calculate_wheel_vectors(0.0, 0.0, 0.0, cfg(), last_angles_deg=[10.0, 20.0, 30.0, 40.0])
    assert angles(vectors) == [10.0, 20.0, 30.0, 40.0]
