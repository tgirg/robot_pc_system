from __future__ import annotations

from pc_controller.protocol import ProtocolError, decode_line
from pc_controller.simulator import SimulatedEsp32, SimulatedFaultProfile


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _drive(seq: int, target: float = 0.0, *, control: str = "pwm", steer: float = 0.0) -> dict[str, object]:
    return {
        "v": 1,
        "type": "drive",
        "seq": seq,
        "armed": True,
        "control": control,
        "steer_deg": [steer] * 4,
        "drive_target": [target] * 4,
    }


def test_packet_drop_decisions_are_deterministic_with_seed() -> None:
    seed = 42
    faults = SimulatedFaultProfile(seed=seed, packet_drop_probability=0.5)
    device_a = SimulatedEsp32(faults=faults)

    faults_repeat = SimulatedFaultProfile(seed=seed, packet_drop_probability=0.5)
    device_b = SimulatedEsp32(faults=faults_repeat)
    device_a.activate_packet_drop()
    device_b.activate_packet_drop()

    assert [device_a.should_drop_response() for _ in range(12)] == [device_b.should_drop_response() for _ in range(12)]


def test_malformed_json_injection_returns_non_json_bytes() -> None:
    device = SimulatedEsp32(faults=SimulatedFaultProfile(seed=1, malformed_json_count=1))
    responses = device.handle_message({"v": 1, "type": "hello"})
    assert len(responses) == 1
    assert isinstance(responses[0], (bytes, bytearray))
    assert not responses[0].strip().endswith(b"}")
    try:
        decode_line(responses[0])
    except ProtocolError as exc:
        assert str(exc) == "invalid json"
    else:
        raise AssertionError("malformed injector output was accepted by the protocol decoder")


def test_explicit_runtime_fault_is_not_consumed_by_setup_messages() -> None:
    device = SimulatedEsp32(
        faults=SimulatedFaultProfile(explicit_fault="runtime failure", explicit_fault_once=True)
    )

    assert device.handle_message({"v": 1, "type": "hello"})[0]["type"] == "hello_ack"
    assert device.handle_message({"v": 1, "type": "config", "config_revision": 1})[0]["type"] == "config_ack"
    assert device.handle_message({"v": 1, "type": "arm", "mode": "normal"})[0]["type"] == "arm_ack"
    assert device.faults.explicit_fault == "runtime failure"

    responses = device.handle_message(_drive(1, 10.0))
    assert [response["type"] for response in responses if isinstance(response, dict)] == ["telemetry", "fault"]
    assert device.state == "SAFE"
    assert device.armed is False
    assert device.faults.explicit_fault is None


def test_stale_telemetry_sequence_injection_repeats_previous_seq() -> None:
    device = SimulatedEsp32(faults=SimulatedFaultProfile(seed=1))
    config = {"v": 1, "type": "config", "config_revision": 10}
    device.handle_message(config)

    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    telemetry_first = device.handle_message(_drive(1))
    device.faults.telemetry_seq_stale = True
    telemetry_second = device.handle_message(_drive(2))
    assert len(telemetry_first) == 1
    assert len(telemetry_second) == 1
    first = telemetry_first[0]
    second = telemetry_second[0]
    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["type"] == "telemetry"
    assert second["type"] == "telemetry"
    assert int(first["seq"]) == int(second["seq"])


def test_sequence_regression_requires_a_baseline_then_emits_past_seq() -> None:
    device = SimulatedEsp32(faults=SimulatedFaultProfile(seed=1, telemetry_seq_regression_count=1))
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})

    baseline = device.handle_message(_drive(1))[0]
    regression = device.handle_message(_drive(2))[0]

    assert isinstance(baseline, dict) and isinstance(regression, dict)
    assert int(baseline["seq"]) == 1
    assert int(regression["seq"]) < int(baseline["seq"])


def test_disconnect_and_reboot_timing_use_injected_clock_at_exact_boundary() -> None:
    disconnect_clock = ManualClock()
    disconnected = SimulatedEsp32(
        faults=SimulatedFaultProfile(disconnect_after_ms=100),
        clock_ms=disconnect_clock,
    )
    disconnect_clock.ms = 99
    assert disconnected.handle_message({"v": 1, "type": "ping", "seq": 1})[0]["type"] == "pong"
    disconnect_clock.ms = 100
    try:
        disconnected.handle_message({"v": 1, "type": "ping", "seq": 2})
    except RuntimeError as exc:
        assert "disconnect" in str(exc)
    else:
        raise AssertionError("disconnect did not occur at the configured boundary")

    reboot_clock = ManualClock()
    rebooted = SimulatedEsp32(
        faults=SimulatedFaultProfile(reboot_after_ms=100),
        clock_ms=reboot_clock,
    )
    rebooted.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    reboot_clock.ms = 99
    assert rebooted.poll() is None
    reboot_clock.ms = 100
    assert rebooted.poll() == "reboot"
    assert rebooted.state == "SAFE"
    assert rebooted.armed is False
    assert rebooted.reboot_count == 1
    reboot_clock.ms = 200
    assert rebooted.poll() is None


def test_reboot_resets_volatile_runtime_state_without_automatic_arm() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(clock_ms=clock)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    device.handle_message(_drive(1, 80.0, steer=25.0))
    assert device.armed and device.motor_pwm == [80] * 4

    device.request_reboot()
    assert device.poll() == "reboot"

    assert device.state == "SAFE"
    assert device.armed is False
    assert device.motor_pwm == [0] * 4
    assert device.wheel_rpm == [0.0] * 4
    assert device.servo_deg == [0.0] * 4
    assert device.last_drive_seq == 0
    assert device.last_emitted_telemetry_seq is None


def test_rpm_stuck_keeps_observed_rpm_fixed_while_command_changes() -> None:
    faults = SimulatedFaultProfile(rpm_stuck=True, rpm_stuck_value=12.5)
    device = SimulatedEsp32(faults=faults)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})

    first = device.handle_message(_drive(1, 20.0, control="rpm"))[0]
    second = device.handle_message(_drive(2, 60.0, control="rpm"))[0]

    assert isinstance(first, dict) and isinstance(second, dict)
    assert device.commanded_drive_target == [60.0] * 4
    assert first["wheel_rpm"] == [12.5] * 4
    assert second["wheel_rpm"] == [12.5] * 4
    assert first["motor_pwm"] != second["motor_pwm"]


def test_rpm_stuck_has_the_same_observed_semantics_for_pwm_control() -> None:
    faults = SimulatedFaultProfile(rpm_stuck=True, rpm_stuck_value=8.0)
    device = SimulatedEsp32(faults=faults)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})

    first = device.handle_message(_drive(1, 20.0, control="pwm"))[0]
    second = device.handle_message(_drive(2, 90.0, control="pwm"))[0]

    assert isinstance(first, dict) and isinstance(second, dict)
    assert device.commanded_drive_target == [90.0] * 4
    assert first["wheel_rpm"] == [8.0] * 4
    assert second["wheel_rpm"] == [8.0] * 4
    assert first["motor_pwm"] == [20] * 4
    assert second["motor_pwm"] == [90] * 4


def test_servo_stuck_keeps_observed_position_fixed_while_command_changes() -> None:
    faults = SimulatedFaultProfile(servo_stuck=True, servo_stuck_value=-7.0)
    device = SimulatedEsp32(faults=faults)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})

    first = device.handle_message(_drive(1, 10.0, steer=20.0))[0]
    second = device.handle_message(_drive(2, 10.0, steer=45.0))[0]

    assert isinstance(first, dict) and isinstance(second, dict)
    assert device.commanded_servo_deg == [45.0] * 4
    assert first["servo_deg"] == [-7.0] * 4
    assert second["servo_deg"] == [-7.0] * 4


def test_command_receive_stop_distinguishes_ignored_commands_from_pc_send() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(clock_ms=clock)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    before = device.processed_command_count
    device.stop_command_reception()

    response = device.handle_message(_drive(1, 30.0))
    assert len(response) == 1 and isinstance(response[0], dict)
    assert response[0]["type"] == "telemetry"
    assert response[0]["command_age_ms"] == 0
    assert device.processed_command_count == before
    assert device.commanded_drive_target == [0.0] * 4
    assert device.event_log[-1]["event"] == "command_ignored"


def test_scheduled_command_receive_stop_starts_at_exact_boundary() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(
        faults=SimulatedFaultProfile(command_receive_stop_after_ms=100),
        clock_ms=clock,
    )
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    before = device.processed_command_count

    clock.ms = 99
    assert device.handle_message(_drive(1, 10.0))
    assert device.processed_command_count == before + 1
    clock.ms = 100
    response = device.handle_message(_drive(2, 20.0))
    assert len(response) == 1 and isinstance(response[0], dict)
    assert response[0]["type"] == "telemetry"
    assert device.processed_command_count == before + 1


def test_command_receive_stop_keeps_telemetry_and_applies_firmware_watchdog() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(clock_ms=clock)
    device.handle_message({"v": 1, "type": "arm", "mode": "normal"})
    clock.ms = 20
    device.handle_message(_drive(1, 80.0))
    device.stop_command_reception()

    clock.ms = 319
    before_stop = device.handle_message(_drive(2, 90.0))[0]
    assert isinstance(before_stop, dict)
    assert before_stop["command_age_ms"] == 299
    assert before_stop["motor_pwm"] == [80] * 4
    clock.ms = 320
    stopped = device.handle_message(_drive(3, 90.0))[0]
    assert isinstance(stopped, dict)
    assert stopped["command_age_ms"] == 300
    assert stopped["motor_pwm"] == [0] * 4
    assert stopped["armed"] is True
    clock.ms = 520
    safe = device.handle_message(_drive(4, 90.0))[0]
    assert isinstance(safe, dict)
    assert safe["command_age_ms"] == 500
    assert safe["state"] == "SAFE"
    assert safe["armed"] is False
    assert safe["fault_flags"] == 1 << 5
