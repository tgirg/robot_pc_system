from __future__ import annotations

import json
from pathlib import Path

from pc_controller.protocol import arm_message, decode_line, disarm_message, drive_message, encode_message, hello_message, who_are_you_message
from pc_controller.controller_input import ControllerState
from pc_controller.simulator import SimulatedEsp32, SimulatedFaultProfile
from pc_controller.virtual_serial import VirtualSerialLink


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _seed_armable_test_config(config_dir: Path) -> None:
    """Create an isolated config and explicitly mark test servos calibrated."""
    from pc_controller.config_manager import ensure_config_files

    ensure_config_files(config_dir)

    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))

    servos = vehicle.get("servos", [])
    if len(servos) != 4:
        raise AssertionError(f"expected 4 servos in test config, got {len(servos)}")

    for servo in servos:
        servo["calibrated"] = True

    vehicle_path.write_text(
        json.dumps(vehicle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read(link: VirtualSerialLink) -> list[dict[str, object]]:
    return [decode_line(line) for line in link.read_lines()]


def test_virtual_serial_handshake_config_arm_drive_disarm() -> None:
    device = SimulatedEsp32()
    link = VirtualSerialLink(device)

    link.write(encode_message(who_are_you_message()))
    identity = _read(link)[0]
    assert identity["type"] == "node_identity"
    assert identity["role"] == "drive"

    link.write(encode_message(hello_message()))
    assert _read(link)[0]["type"] == "hello_ack"

    link.write(encode_message({"v": 1, "type": "config", "config_revision": 41, "pca9685_address": 64}))
    config_ack = _read(link)[0]
    assert config_ack["type"] == "config_ack"
    assert config_ack["ok"] is True
    assert device.state == "SAFE"

    link.write(encode_message(arm_message("normal")))
    arm_ack = _read(link)[0]
    assert arm_ack["type"] == "arm_ack"
    assert arm_ack["armed"] is True
    assert device.state == "NORMAL"

    command = drive_message(1, "pwm", [0.0, 0.0, 0.0, 0.0], [100.0, 100.0, 100.0, 100.0], True)
    link.write(encode_message(command))
    telemetry = _read(link)[0]
    assert telemetry["type"] == "telemetry"
    assert telemetry["motor_pwm"] == [100, 100, 100, 100]
    assert telemetry["armed"] is True

    link.write(encode_message(disarm_message()))
    disarm_ack = _read(link)[0]
    assert disarm_ack["type"] == "arm_ack"
    assert disarm_ack["armed"] is False
    assert device.motor_pwm == [0, 0, 0, 0]


def test_virtual_serial_rejects_stale_drive_seq() -> None:
    link = VirtualSerialLink()
    link.write(encode_message(arm_message("normal")))
    _read(link)

    command = drive_message(10, "pwm", [0.0] * 4, [10.0] * 4, True)
    link.write(encode_message(command))
    _read(link)
    link.write(encode_message(command))

    fault = _read(link)[0]
    assert fault["type"] == "fault"
    assert fault["reason"] == "stale drive seq"


def test_controller_app_can_drive_through_fake_esp32(tmp_path) -> None:
    import argparse

    from pc_controller.app import ControllerApp
    from pc_controller.protocol import arm_message

    _seed_armable_test_config(tmp_path)

    args = argparse.Namespace(
        config_dir=str(tmp_path),
        simulate=False,
        fake_esp32=True,
        fake_trace=False,
        port=None,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )
    clock = ManualClock()
    app = ControllerApp(args, now_ms=clock)
    assert isinstance(app.serial, VirtualSerialLink)
    assert app.fake_device is not None

    app.safety.apply_config()
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()

    max_linear = float(app.config["motion"]["max_linear_speed_mps"])
    for step in range(12):
        clock.ms = step * 20
        app.tick(max_linear * 0.12, 0.0, 0.0)

    assert app.last_telemetry is not None
    assert app.last_telemetry["type"] == "telemetry"
    assert app.last_telemetry["state"] == "NORMAL"
    assert app.last_telemetry["armed"] is True
    pwm = app.last_telemetry["motor_pwm"]
    assert all(int(value) > 0 for value in pwm)
    assert pwm == app.fake_device.motor_pwm
    assert max(abs(int(value)) for value in pwm) <= int(app.config["motion"]["open_loop_max_pwm"])


def test_controller_disconnect_cancels_pending_arm_and_late_ack(tmp_path) -> None:
    import argparse

    from pc_controller.app import ControllerApp
    from pc_controller.safety import SafetyState

    _seed_armable_test_config(tmp_path)
    args = argparse.Namespace(
        config_dir=str(tmp_path),
        simulate=False,
        fake_esp32=True,
        fake_trace=False,
        port=None,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )
    clock = ManualClock()
    app = ControllerApp(args, now_ms=clock)
    assert isinstance(app.serial, VirtualSerialLink)
    assert app.fake_device is not None
    app.safety.apply_config()
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()

    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    assert app.fake_device.armed is True
    app.tick_controller(ControllerState(False, ""))

    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.safety.fault == "controller disconnected"
    assert app.fake_device.state == "SAFE"
    assert app.fake_device.armed is False


def test_fake_robot_demo_smoke(tmp_path) -> None:
    from pc_controller.fake_robot_demo import run_demo

    _seed_armable_test_config(tmp_path)

    results = dict(run_demo(str(tmp_path), trace=False))
    assert any(abs(int(value)) > 0 for value in results["forward"]["motor_pwm"])
    assert any(abs(int(value)) > 0 for value in results["pivot"]["motor_pwm"])
    assert results["final_stop"]["motor_pwm"] == [0, 0, 0, 0]


def test_virtual_serial_returns_fault_for_bad_drive_shape() -> None:
    link = VirtualSerialLink()
    link.write(encode_message(arm_message("normal")))
    _read(link)
    link.write(encode_message({"v": 1, "type": "drive", "seq": 1, "armed": True, "control": "pwm", "steer_deg": [0], "drive_target": [1]}))
    fault = _read(link)[0]
    assert fault["type"] == "fault"
    assert fault["reason"] == "drive arrays must have 4 entries"


def test_response_delay_uses_same_clock_and_exact_due_boundary() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(clock_ms=clock)
    device.faults.response_delay_ms = 100
    link = VirtualSerialLink(device, now_ms=clock)

    link.write(encode_message(hello_message()))
    clock.ms = 99
    assert link.read_lines() == []
    clock.ms = 100
    assert decode_line(link.read_lines()[0])["type"] == "hello_ack"


def test_packet_drop_is_inactive_during_handshake_then_seeded_runtime() -> None:
    clock = ManualClock()
    faults = SimulatedFaultProfile(seed=5, packet_drop_probability=1.0)
    device = SimulatedEsp32(faults=faults, clock_ms=clock)
    link = VirtualSerialLink(device, now_ms=clock)

    link.write(encode_message(hello_message()))
    assert decode_line(link.read_lines()[0])["type"] == "hello_ack"
    link.write(encode_message(arm_message("normal")))
    assert decode_line(link.read_lines()[0])["type"] == "arm_ack"

    device.activate_packet_drop()
    link.write(encode_message(drive_message(1, "pwm", [0.0] * 4, [10.0] * 4, True)))
    assert link.read_lines() == []
    assert any(event["event"] == "drop" for event in link.event_log)


def test_disconnect_fails_read_and_write_and_stops_pending_telemetry() -> None:
    clock = ManualClock()
    device = SimulatedEsp32(clock_ms=clock)
    link = VirtualSerialLink(device, now_ms=clock)
    device.disconnect()

    try:
        link.read_lines()
    except RuntimeError as exc:
        assert "disconnect" in str(exc)
    else:
        raise AssertionError("read did not fail while disconnected")

    try:
        link.write(encode_message(hello_message()))
    except RuntimeError as exc:
        assert "disconnect" in str(exc)
    else:
        raise AssertionError("write did not fail while disconnected")

    assert any(event["event"] == "disconnect" for event in link.event_log)


def test_event_log_is_retained_when_trace_is_disabled() -> None:
    clock = ManualClock()
    link = VirtualSerialLink(SimulatedEsp32(clock_ms=clock), trace=False, now_ms=clock)
    link.write(encode_message(hello_message()))
    assert link.read_lines()

    assert [event["event"] for event in link.event_log] == ["tx", "schedule", "rx"]
    assert all(event["timestamp"] == 0 for event in link.event_log)
