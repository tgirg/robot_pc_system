from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from pc_controller.app import ControllerApp, build_arg_parser
from pc_controller.controller_input import ControllerState
from pc_controller.protocol import arm_message, encode_message
from pc_controller.safety import SafetyState
from pc_controller.serial_discovery import AmbiguousSerialNodeError, SerialProbe
from pc_controller.simulator import SimulatedEsp32
from pc_controller.virtual_serial import VirtualSerialLink


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _seed_armable_config(config_dir: Path) -> None:
    from pc_controller.config_manager import ensure_config_files

    ensure_config_files(config_dir)
    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(
        json.dumps(vehicle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _args(config_dir: Path, *, fake_esp32: bool = True, port: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir),
        simulate=False,
        fake_esp32=fake_esp32,
        fake_trace=False,
        port=port,
        node_role="drive",
        node_id=None,
        discovery_timeout=0.1,
        reconnect_interval=1.0,
        reconnect_handshake_timeout=0.5,
        auto_reconnect=True,
        once=False,
        duration=None,
        joystick=False,
        list_controllers=False,
        debug_controller=None,
        rpm_monitor=False,
        rpm_monitor_hz=5.0,
    )


def _arm_fake_app(app: ControllerApp, clock: ManualClock) -> None:
    assert app.serial is not None
    app.safety.apply_config()
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()
    assert app.safety.armed is True


def test_reconnect_cli_defaults_on_and_can_be_disabled() -> None:
    parser = build_arg_parser()
    defaults = parser.parse_args([])
    disabled = parser.parse_args(["--no-auto-reconnect"])

    assert defaults.auto_reconnect is True
    assert defaults.reconnect_interval == 1.0
    assert defaults.reconnect_handshake_timeout == 2.0
    assert disabled.auto_reconnect is False


def test_initial_discovery_failure_retries_residently_and_remains_disarmed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    args = _args(tmp_path, fake_esp32=False)
    app = ControllerApp(args, now_ms=clock)
    device = SimulatedEsp32(clock_ms=clock)
    link = VirtualSerialLink(device, now_ms=clock)
    attempts: list[int] = []

    def open_after_initial_failure(**kwargs: Any) -> SerialProbe:
        attempts.append(clock.ms)
        if len(attempts) == 1:
            raise RuntimeError("no serial node matched role=drive")
        return SerialProbe(port=link.port, identity=device.node_identity(), link=link)  # type: ignore[arg-type]

    monkeypatch.setattr("pc_controller.app.open_discovered_serial_link", open_after_initial_failure)
    monkeypatch.setattr("pc_controller.app.PID_FILE", tmp_path / "controller.pid")

    def run_retry_ticks() -> None:
        assert app.serial is None
        assert app.reconnect_phase == "waiting"
        assert app.reconnect_next_attempt_ms == 1000
        assert app.safety.state == SafetyState.SAFE
        assert app.safety.armed is False
        assert app.safety.fault == "serial unavailable at startup"

        clock.ms = 999
        app.tick(0.0, 0.0, 0.0)
        assert attempts == [0]

        clock.ms = 1000
        app.tick(0.0, 0.0, 0.0)
        assert attempts == [0, 1000]
        assert app.reconnect_phase == "config_pending"

        clock.ms = 1001
        app.tick(0.0, 0.0, 0.0)
        assert app.reconnect_phase == "ready_disarmed"
        assert app.safety.state == SafetyState.SAFE
        assert app.safety.armed is False
        assert app.safety.config_accepted is True
        assert [message["type"] for message in link.writes] == ["disarm", "hello", "config"]

    app._run_loop = run_retry_ticks  # type: ignore[method-assign]
    app.start()

    assert link.closed is True
    assert [message["type"] for message in link.writes] == ["disarm", "hello", "config", "disarm"]
    assert not (tmp_path / "controller.pid").exists()


def test_initial_explicit_port_open_failure_uses_same_resident_retry(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    args = _args(tmp_path, fake_esp32=False, port="COM7")
    app = ControllerApp(args, now_ms=clock)
    device = SimulatedEsp32(clock_ms=clock)
    link = VirtualSerialLink(device, now_ms=clock)
    attempts: list[int] = []

    def open_after_initial_failure(port: str) -> VirtualSerialLink:
        assert port == "COM7"
        attempts.append(clock.ms)
        if len(attempts) == 1:
            raise RuntimeError("could not open serial port COM7")
        return link

    monkeypatch.setattr("pc_controller.app.SerialLink", open_after_initial_failure)
    monkeypatch.setattr("pc_controller.app.PID_FILE", tmp_path / "controller.pid")

    def run_retry_ticks() -> None:
        assert app.reconnect_phase == "waiting"
        clock.ms = 1000
        app.tick(0.0, 0.0, 0.0)
        assert attempts == [0, 1000]
        assert app.reconnect_phase == "config_pending"
        clock.ms = 1001
        app.tick(0.0, 0.0, 0.0)
        assert app.reconnect_phase == "ready_disarmed"
        assert app.safety.state == SafetyState.SAFE
        assert app.safety.armed is False
        assert all(message["type"] != "arm" for message in link.writes)

    app._run_loop = run_retry_ticks  # type: ignore[method-assign]
    app.start()


@pytest.mark.parametrize(
    ("once", "duration", "auto_reconnect"),
    [
        (True, None, True),
        (False, 0.5, True),
        (False, None, False),
    ],
)
def test_bounded_or_opted_out_mode_does_not_hide_initial_connection_failure(
    tmp_path: Path,
    monkeypatch: Any,
    once: bool,
    duration: float | None,
    auto_reconnect: bool,
) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    args = _args(tmp_path, fake_esp32=False)
    args.once = once
    args.duration = duration
    args.auto_reconnect = auto_reconnect
    app = ControllerApp(args, now_ms=clock)
    monkeypatch.setattr(
        "pc_controller.app.open_discovered_serial_link",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("no serial node matched role=drive")),
    )
    monkeypatch.setattr("pc_controller.app.PID_FILE", tmp_path / "controller.pid")
    app._run_loop = lambda: pytest.fail("bounded/opted-out mode must fail before entering the loop")  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="no serial node matched"):
        app.start()

    assert app.reconnect_phase == "idle"
    assert not (tmp_path / "controller.pid").exists()


def test_ambiguous_initial_discovery_is_not_automatically_retried(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _seed_armable_config(tmp_path)
    args = _args(tmp_path, fake_esp32=False)
    app = ControllerApp(args)
    monkeypatch.setattr(
        "pc_controller.app.open_discovered_serial_link",
        lambda **kwargs: (_ for _ in ()).throw(
            AmbiguousSerialNodeError("multiple serial nodes matched role=drive")
        ),
    )
    monkeypatch.setattr("pc_controller.app.PID_FILE", tmp_path / "controller.pid")

    with pytest.raises(AmbiguousSerialNodeError, match="multiple serial nodes"):
        app.start()

    assert app.reconnect_phase == "idle"
    assert app.reconnect_next_attempt_ms is None
    assert not (tmp_path / "controller.pid").exists()


def test_ambiguous_rediscovery_blocks_retry_without_selecting_a_device(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    app._close_serial()
    app.reconnect_active = True
    app.reconnect_phase = "waiting"
    app.reconnect_next_attempt_ms = 0
    app._open_reconnect_transport = (  # type: ignore[method-assign]
        lambda: (_ for _ in ()).throw(AmbiguousSerialNodeError("duplicate drive nodes"))
    )

    app._service_serial_connection(0)

    assert app.serial is None
    assert app.reconnect_phase == "blocked"
    assert app.reconnect_next_attempt_ms is None
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.reconnect_last_error == "duplicate drive nodes"


def test_arm_is_rejected_while_serial_is_unavailable_during_retry(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    app._close_serial()
    app.safety.apply_config()
    app.reconnect_active = True
    app.reconnect_phase = "waiting"
    app.reconnect_next_attempt_ms = 100_000
    app.reconnect_require_arm_release = False
    arm_state = ControllerState(True, "test", arm_pressed=True)

    app.tick_controller(arm_state)
    clock.ms = int(float(app.mapping.get("arm_hold_seconds", 1.0)) * 1000)
    app.tick_controller(arm_state)

    assert app.serial is None
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.safety.fault == "serial unavailable"


def test_fake_disconnect_reconnects_rehandshakes_and_remains_safe(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.fake_device is not None
    _arm_fake_app(app, clock)

    app.fake_device.disconnect()
    clock.ms = 20
    app.tick(0.1, 0.0, 0.0)

    assert app.serial is None
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.fault == "serial write failed"
    assert app.reconnect_phase == "waiting"

    clock.ms = 1019
    app.tick(0.0, 0.0, 0.0)
    assert app.serial is None

    clock.ms = 1020
    app.tick(0.0, 0.0, 0.0)
    assert isinstance(app.serial, VirtualSerialLink)
    replacement_link = app.serial
    assert app.reconnect_phase == "config_pending"
    assert [message["type"] for message in replacement_link.writes] == ["disarm", "hello", "config"]

    clock.ms = 1021
    app.tick(0.0, 0.0, 0.0)

    assert app.reconnect_phase == "ready_disarmed"
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.safety.config_accepted is True
    assert app.safety.fault == "serial write failed"
    assert app.fake_device.state == "SAFE"
    assert app.fake_device.armed is False
    assert all(message["type"] != "arm" for message in replacement_link.writes)
    assert replacement_link.event_log
    assert all(event["reconnect"] is True for event in replacement_link.event_log)

    # Holding the old ARM gesture through a disconnect must not re-arm. The
    # operator has to release it before a fresh hold can start.
    clock.ms = 3000
    held_arm = ControllerState(True, "test", arm_pressed=True)
    app.tick_controller(held_arm)
    clock.ms = 5000
    app.tick_controller(held_arm)
    assert app.safety.state == SafetyState.SAFE
    assert all(message["type"] != "arm" for message in replacement_link.writes)

    clock.ms = 5001
    app.tick_controller(ControllerState(True, "test"))
    clock.ms = 5002
    app.tick_controller(held_arm)
    hold_ms = int(float(app.mapping.get("arm_hold_seconds", 1.0)) * 1000)
    clock.ms = 5002 + hold_ms
    app.tick_controller(held_arm)
    assert app.safety.state == SafetyState.NORMAL
    assert app.safety.armed is True


def test_reconnect_failure_uses_bounded_backoff_without_busy_loop(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    args = _args(tmp_path)
    args.reconnect_interval = 0.1
    app = ControllerApp(args, now_ms=clock)
    app._close_serial()
    app.reconnect_phase = "waiting"
    app.reconnect_next_attempt_ms = 0
    attempts: list[int] = []

    def fail_open() -> tuple[VirtualSerialLink, dict[str, Any] | None]:
        attempts.append(clock.ms)
        raise RuntimeError("port unavailable")

    app._open_reconnect_transport = fail_open  # type: ignore[method-assign]

    for now_ms in (0, 99, 100, 299, 300, 699, 700, 1499, 1500, 3099, 3100, 4699):
        clock.ms = now_ms
        app._service_serial_connection(now_ms)

    assert attempts == [0, 100, 300, 700, 1500, 3100]
    assert app.reconnect_next_attempt_ms == 4700
    assert app.reconnect_attempts == 6


def test_missing_hello_ack_times_out_and_retries_later(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.fake_device is not None
    app.fake_device.faults.hello_ack = False
    app._handle_transport_failure("serial read failed", "test disconnect")

    clock.ms = 1000
    app._service_serial_connection(clock.ms)
    assert app.reconnect_phase == "hello_pending"
    app._read_serial_messages()
    assert app.reconnect_phase == "hello_pending"

    clock.ms = 1500
    app._service_serial_connection(clock.ms)

    assert app.serial is None
    assert app.reconnect_phase == "waiting"
    assert app.reconnect_last_error == "reconnect handshake timeout"
    assert app.reconnect_next_attempt_ms == 2500


def test_auto_reconnect_can_be_disabled(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    args = _args(tmp_path)
    args.auto_reconnect = False
    app = ControllerApp(args, now_ms=clock)

    app._handle_transport_failure("serial read failed", "test disconnect")
    clock.ms = 5000
    app._service_serial_connection(clock.ms)

    assert app.serial is None
    assert app.reconnect_phase == "idle"
    assert app.reconnect_next_attempt_ms is None
    assert app.safety.state == SafetyState.SAFE


def test_telemetry_timeout_closes_silent_link_and_schedules_reconnect(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.fake_device is not None
    _arm_fake_app(app, clock)
    app.fake_device.stop_command_reception()

    clock.ms = 550
    app.tick(0.1, 0.0, 0.0)

    assert app.serial is None
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.fault == "telemetry timeout"
    assert app.reconnect_phase == "waiting"
    assert app.reconnect_next_attempt_ms == 1550


def test_rediscovery_is_pinned_to_original_node_id(tmp_path: Path, monkeypatch: Any) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path, fake_esp32=False), now_ms=clock)
    initial_device = SimulatedEsp32(clock_ms=clock)
    initial_link = VirtualSerialLink(initial_device, now_ms=clock)
    app.serial = initial_link
    app.reconnect_active = True
    app.reconnect_phase = "ready"
    initial_link.write(encode_message({"v": 1, "type": "hello"}))
    app._read_serial_messages()
    assert app.reconnect_expected_node_id == "mcb44_drive_main"
    app._handle_transport_failure("serial read failed", "test disconnect")
    device = SimulatedEsp32(clock_ms=clock)
    link = VirtualSerialLink(device, now_ms=clock)
    captured: dict[str, Any] = {}

    def open_pinned(**kwargs: Any) -> SerialProbe:
        captured.update(kwargs)
        return SerialProbe(port=link.port, identity=device.node_identity(), link=link)  # type: ignore[arg-type]

    monkeypatch.setattr("pc_controller.app.open_discovered_serial_link", open_pinned)

    clock.ms = 1000
    app._service_serial_connection(clock.ms)
    app._read_serial_messages()
    app._read_serial_messages()

    assert captured["node_id"] == "mcb44_drive_main"
    assert captured["role"] == "drive"
    assert app.reconnect_phase == "ready_disarmed"
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.config_accepted is True
    assert all(message["type"] != "arm" for message in link.writes)


def test_identity_mismatch_blocks_reconnect(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path, fake_esp32=False, port="COM7"), now_ms=clock)
    app.reconnect_expected_node_id = "mcb44_drive_main"
    app.reconnect_active = True
    app.reconnect_phase = "waiting"
    app.reconnect_next_attempt_ms = 0
    wrong_device = SimulatedEsp32(node_id="mcb44_drive_spare", clock_ms=clock)
    wrong_link = VirtualSerialLink(wrong_device, now_ms=clock)
    app._open_reconnect_transport = (  # type: ignore[method-assign]
        lambda: (wrong_link, wrong_device.node_identity())
    )

    app._service_serial_connection(0)

    assert app.reconnect_phase == "blocked"
    assert app.serial is None
    assert wrong_link.closed is True
    assert app.safety.state == SafetyState.SAFE
    assert "node mismatch" in str(app.safety.fault)


def test_role_mismatch_blocks_reconnect(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path, fake_esp32=False, port="COM7"), now_ms=clock)
    app.reconnect_expected_node_id = "robot_node_main"
    app.reconnect_active = True
    app.reconnect_phase = "waiting"
    app.reconnect_next_attempt_ms = 0
    wrong_device = SimulatedEsp32(node_id="robot_node_main", role="sensor", clock_ms=clock)
    wrong_link = VirtualSerialLink(wrong_device, now_ms=clock)
    app._open_reconnect_transport = (  # type: ignore[method-assign]
        lambda: (wrong_link, wrong_device.node_identity())
    )

    app._service_serial_connection(0)

    assert app.reconnect_phase == "blocked"
    assert app.serial is None
    assert wrong_link.closed is True
    assert app.safety.state == SafetyState.SAFE
    assert "role mismatch" in str(app.safety.fault)


def test_rejected_config_blocks_reconnect_without_arm(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.fake_device is not None
    app.fake_device.faults.config_ack_ok = False
    app._handle_transport_failure("serial read failed", "test disconnect")

    clock.ms = 1000
    app._service_serial_connection(clock.ms)
    assert isinstance(app.serial, VirtualSerialLink)
    replacement_link = app.serial
    app._read_serial_messages()
    app._read_serial_messages()

    assert app.reconnect_phase == "blocked"
    assert app.serial is None
    assert replacement_link.closed is True
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.safety.config_accepted is False
    assert app.reconnect_last_error == "config rejected by fake injector"
    assert all(message["type"] != "arm" for message in replacement_link.writes)


def test_pca9685_not_ready_blocks_reconnect(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.fake_device is not None
    app.fake_device.pca9685_ok = False
    app._handle_transport_failure("serial read failed", "test disconnect")

    clock.ms = 1000
    app._service_serial_connection(clock.ms)
    app._read_serial_messages()

    assert app.reconnect_phase == "blocked"
    assert app.serial is None
    assert app.safety.state == SafetyState.SAFE
    assert app.safety.armed is False
    assert app.reconnect_last_error == "ESP32 reports PCA9685 not ready"
