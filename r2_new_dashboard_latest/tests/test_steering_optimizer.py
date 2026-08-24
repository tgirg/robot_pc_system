from __future__ import annotations

import pytest

from pc_controller.steering_optimizer import (
    OptimizerSettings,
    ServoLimit,
    SteeringTransitionController,
    TransitionState,
    coordinated_4ws_speed_factors,
    apply_open_loop_static_compensation,
    optimize_coordinated_four_ws,
    optimize_pure_translation,
    optimize_pivot_rotation,
    optimize_wheel,
    speed_scale_for_error,
    translation_angle_and_magnitude,
)


def test_open_loop_static_compensation_preserves_zero_full_scale_and_order() -> None:
    motors = [
        {"ff_static_pwm_pos": 40, "ff_static_pwm_neg": 40},
        {"ff_static_pwm_pos": 25, "ff_static_pwm_neg": 25},
        {"ff_static_pwm_pos": 30, "ff_static_pwm_neg": 30},
        {"ff_static_pwm_pos": 40, "ff_static_pwm_neg": 40},
    ]

    assert apply_open_loop_static_compensation([0, -29, -29, -60], 60, motors) == [0, -42, -44, -60]
    compensated = apply_open_loop_static_compensation([-29, -60, -29, -60], 60, motors)
    assert compensated == [-50, -60, -44, -60]
    assert abs(compensated[0]) < abs(compensated[1])
    assert abs(compensated[2]) < abs(compensated[3])


def test_over_135_uses_reversed_motor_candidate() -> None:
    command = optimize_wheel(150.0, 1.0, 0.0, ServoLimit(-135.0, 135.0))
    assert command.angle_deg == pytest.approx(-30.0)
    assert command.speed == pytest.approx(-1.0)
    assert command.drive_direction_reversed is True


def test_can_disable_reversed_motor_candidate_for_pure_rotation() -> None:
    command = optimize_wheel(135.0, 1.0, 0.0, ServoLimit(-135.0, 135.0), allow_reversed_drive=False)
    assert command.angle_deg == pytest.approx(135.0)
    assert command.speed == pytest.approx(1.0)
    assert command.drive_direction_reversed is False


def test_below_minus_135_uses_reversed_motor_candidate() -> None:
    command = optimize_wheel(-150.0, 1.0, 0.0, ServoLimit(-135.0, 135.0))
    assert command.angle_deg == pytest.approx(30.0)
    assert command.speed == pytest.approx(-1.0)


def test_uncalibrated_servo_faults_without_motion() -> None:
    command = optimize_wheel(45.0, 1.0, 0.0, ServoLimit(-135.0, 135.0, calibrated=False))
    assert command.speed == 0.0
    assert command.fault == "servo_not_calibrated"


def test_pure_translation_prefers_common_four_wheel_angle() -> None:
    commands = optimize_pure_translation(45.0, 1.0, [0.0, 0.0, 0.0, 0.0], [ServoLimit(-135.0, 135.0)] * 4)
    assert [command.angle_deg for command in commands] == [45.0, 45.0, 45.0, 45.0]
    assert [command.speed for command in commands] == [1.0, 1.0, 1.0, 1.0]


def test_coordinated_four_ws_matches_v29_forward_turn_posture() -> None:
    commands = optimize_coordinated_four_ws(
        0.0,
        1.0,
        1.0,
        [0.0, 0.0, 0.0, 0.0],
        [ServoLimit(-135.0, 135.0)] * 4,
    )
    assert [command.angle_deg for command in commands] == [45.0, 45.0, -45.0, -45.0]
    assert [command.speed for command in commands] == [1.0, 1.0, 1.0, 1.0]
    assert [command.representation for command in commands] == ["A", "A", "A", "A"]


def test_coordinated_four_ws_reverses_all_wheels_as_a_group() -> None:
    commands = optimize_coordinated_four_ws(
        0.0,
        1.0,
        1.0,
        [-130.0, -130.0, 130.0, 130.0],
        [ServoLimit(-135.0, 135.0)] * 4,
    )
    assert [command.angle_deg for command in commands] == [-135.0, -135.0, 135.0, 135.0]
    assert [command.speed for command in commands] == [-1.0, -1.0, -1.0, -1.0]
    assert [command.representation for command in commands] == ["B", "B", "B", "B"]


def test_coordinated_four_ws_inner_outer_speed_difference() -> None:
    commands = optimize_coordinated_four_ws(
        0.0,
        1.0,
        1.0,
        [0.0, 0.0, 0.0, 0.0],
        [ServoLimit(-135.0, 135.0)] * 4,
        wheelbase_m=0.327,
        track_width_m=0.327,
        inner_outer_speed=True,
        positive_steer_turns_right=True,
    )
    speeds = [command.speed for command in commands]
    assert speeds[0] == pytest.approx(speeds[2])
    assert speeds[1] == pytest.approx(speeds[3])
    assert speeds[0] == pytest.approx(1.0)
    assert 0.0 < speeds[1] < speeds[0]


def test_coordinated_four_ws_speed_factors_flip_by_turn_direction() -> None:
    right_turn = coordinated_4ws_speed_factors(1.0, 0.327, 0.327)
    left_turn = coordinated_4ws_speed_factors(-1.0, 0.327, 0.327)
    assert right_turn[0] == pytest.approx(right_turn[2])
    assert right_turn[1] == pytest.approx(right_turn[3])
    assert right_turn[0] > right_turn[1]
    assert left_turn[1] > left_turn[0]


def test_pivot_rotation_uses_v29_shortest_posture_from_straight() -> None:
    steer, speeds = optimize_pivot_rotation(1.0, 1.0, [0.0, 0.0, 0.0, 0.0], [ServoLimit(-135.0, 135.0)] * 4)
    assert steer == [-45.0, 45.0, 45.0, -45.0]
    assert speeds == pytest.approx([-1.0, 1.0, -1.0, 1.0])


def test_pivot_rotation_reverses_motor_signs_without_moving_servos() -> None:
    current = [-45.0, 45.0, 45.0, -45.0]
    positive_steer, positive_speeds = optimize_pivot_rotation(1.0, 1.0, current, [ServoLimit(-135.0, 135.0)] * 4)
    negative_steer, negative_speeds = optimize_pivot_rotation(1.0, -1.0, current, [ServoLimit(-135.0, 135.0)] * 4)
    assert positive_steer == current
    assert negative_steer == current
    assert negative_speeds == pytest.approx([-speed for speed in positive_speeds])


def test_candidate_hysteresis_prevents_small_flip() -> None:
    settings = OptimizerSettings(hysteresis_deg=20.0)
    command = optimize_wheel(
        100.0,
        1.0,
        -80.0,
        ServoLimit(-135.0, 135.0),
        previous_representation="B",
        settings=settings,
    )
    assert command.representation == "B"


def test_speed_scale_rules() -> None:
    assert speed_scale_for_error(0.0) == pytest.approx(1.0)
    assert speed_scale_for_error(30.0) == pytest.approx(0.0)
    assert 0.2 < speed_scale_for_error(20.0) < 1.0


def test_deadzone_holds_last_translation_angle() -> None:
    angle, magnitude = translation_angle_and_magnitude(0.01, 0.01, 0.1)
    assert angle is None
    assert magnitude == 0.0


def test_transition_stops_before_large_realign_and_waits_for_alignment() -> None:
    controller = SteeringTransitionController(decel_time_ms=100, settle_time_ms=100, accel_time_ms=100)
    out = controller.update(0, [90.0] * 4, [0.0] * 4)
    assert out.state == TransitionState.DECELERATE
    assert out.allow_drive is False
    out = controller.update(150, [90.0] * 4, [0.0] * 4)
    assert out.state == TransitionState.ALIGN
    out = controller.update(180, [90.0] * 4, [90.0] * 4)
    assert out.state == TransitionState.SETTLE
    out = controller.update(300, [90.0] * 4, [90.0] * 4)
    assert out.state == TransitionState.ACCELERATE


def test_transition_times_out_to_blocked() -> None:
    controller = SteeringTransitionController(decel_time_ms=0, alignment_timeout_ms=100)
    controller.update(0, [90.0] * 4, [0.0] * 4)
    controller.update(1, [90.0] * 4, [0.0] * 4)
    out = controller.update(200, [90.0] * 4, [0.0] * 4)
    assert out.state == TransitionState.BLOCKED
