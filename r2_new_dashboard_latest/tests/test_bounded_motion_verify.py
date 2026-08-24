from __future__ import annotations

from pc_controller.bounded_motion_verify import summarize_pattern


def test_pivot_summary_checks_all_four_reversed_signs() -> None:
    result = summarize_pattern(
        "right_pivot",
        {"steer_deg": [-45, 45, 45, -45], "drive_target": [-60, 60, 60, -60]},
        [0, 0, 0, 0],
        [-100, 200, 150, -250],
    )

    assert result["pivot_target_signs_ok"] is True
    assert result["encoder_sign_matches_command"] is True


def test_rear_front_right_arc_assigns_old_right_as_inner_pair() -> None:
    result = summarize_pattern(
        "forward_right_arc",
        {"steer_deg": [-16.2, -34.7, 16.2, 34.7], "drive_target": [-60, -29, -60, -29]},
        [0, 0, 0, 0],
        [-500, -50, -600, -80],
    )

    assert result["physical_inner_old_logical"] == ["FR", "RR"]
    assert result["inner_outer_command_ok"] is True
    assert result["encoder_sign_matches_command"] is True
