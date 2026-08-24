from __future__ import annotations

from pc_controller.wheel_pairing_check import analyze_pairing_observation, propose_encoder_mapping


def _config() -> dict[str, object]:
    return {
        "motors": [
            {"physical": 1},
            {"physical": 2},
            {"physical": 3},
            {"physical": 0},
        ],
        "encoders": [
            {"physical": 1, "inverted": False},
            {"physical": 0, "inverted": False},
            {"physical": 3, "inverted": False},
            {"physical": 2, "inverted": False},
        ],
    }


def test_analyze_pairing_identifies_dominant_physical_encoder() -> None:
    observation = analyze_pairing_observation(
        commanded_logical=0,
        direction="forward",
        count_before=[100, 200, 300, 400],
        count_after=[101, -800, 301, 399],
        vehicle_config=_config(),
    )

    assert observation.pairing_confirmed is True
    assert observation.commanded_motor_physical == 1
    assert observation.dominant_encoder_logical == 1
    assert observation.dominant_encoder_physical == 0
    assert observation.dominant_delta == -1000


def test_analyze_pairing_rejects_ambiguous_encoder_noise() -> None:
    observation = analyze_pairing_observation(
        commanded_logical=2,
        direction="forward",
        count_before=[0, 0, 0, 0],
        count_after=[0, 100, 40, 0],
        vehicle_config=_config(),
    )

    assert observation.pairing_confirmed is False
    assert observation.dominant_encoder_logical is None


def test_propose_encoder_mapping_reorders_physical_pairings_and_polarity() -> None:
    deltas = (
        [0, -1000, 0, 0],
        [900, 0, 0, 0],
        [0, 0, 0, 1200],
        [0, 0, -1100, 0],
    )
    observations = []
    for wheel, delta in enumerate(deltas):
        observations.append(
            analyze_pairing_observation(
                commanded_logical=wheel,
                direction="forward",
                count_before=[0, 0, 0, 0],
                count_after=delta,
                vehicle_config=_config(),
            )
        )

    proposal = propose_encoder_mapping(observations, _config())

    assert proposal == [
        {"logical": 0, "name": "FL", "physical": 0, "inverted": True},
        {"logical": 1, "name": "FR", "physical": 1, "inverted": False},
        {"logical": 2, "name": "RL", "physical": 2, "inverted": False},
        {"logical": 3, "name": "RR", "physical": 3, "inverted": True},
    ]
