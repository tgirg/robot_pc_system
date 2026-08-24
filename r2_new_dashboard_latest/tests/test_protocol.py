from __future__ import annotations

import json

import pytest

from pc_controller.protocol import (
    ProtocolError,
    ProtocolValidator,
    decode_line,
    drive_message,
    encode_message,
    who_are_you_message,
)


def test_valid_ndjson_round_trip() -> None:
    raw = encode_message({"type": "hello"})
    assert decode_line(raw)["type"] == "hello"


def test_who_are_you_message() -> None:
    raw = encode_message(who_are_you_message())
    decoded = decode_line(raw)
    assert decoded["type"] == "who_are_you"
    assert decoded["client"] == "pc_controller"


def test_rejects_bad_json() -> None:
    with pytest.raises(ProtocolError):
        decode_line("{bad")


def test_rejects_invalid_utf8_line() -> None:
    with pytest.raises(ProtocolError):
        decode_line(b"\xff\xfe\n")


def test_rejects_bad_array_length() -> None:
    validator = ProtocolValidator()
    with pytest.raises(ProtocolError):
        validator.validate_drive({"v": 1, "type": "drive", "seq": 1, "control": "pwm", "steer_deg": [0], "drive_target": [0]})


def test_rejects_nan_drive_value() -> None:
    message = json.loads('{"v":1,"type":"drive","seq":1,"control":"pwm","steer_deg":[0,0,0,NaN],"drive_target":[0,0,0,0]}')
    with pytest.raises(ProtocolError):
        ProtocolValidator().validate_drive(message)


def test_rejects_stale_sequence() -> None:
    validator = ProtocolValidator()
    validator.validate_drive(drive_message(1, "pwm", [0.0] * 4, [0.0] * 4, True))
    with pytest.raises(ProtocolError):
        validator.validate_drive(drive_message(1, "pwm", [0.0] * 4, [0.0] * 4, True))
