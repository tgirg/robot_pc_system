from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pc_controller.app import ControllerApp, build_arg_parser
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.controller_input import ControllerState
from pc_controller.gui_model import BackendKind, ConnectionState
from pc_controller.gui_runtime import FakeFleetDashboardRuntime, RealFleetDashboardRuntime
from pc_controller.safety import SafetyState
from pc_controller.simulator import SimulatedEsp32
from pc_controller.virtual_serial import VirtualSerialLink


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


class MutableControllerInput:
    def __init__(self) -> None:
        self.state = ControllerState(connected=True, name="test controller")
        self.mapping: dict = {}

    def read(self) -> ControllerState:
        return self.state


def _config_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    ensure_config_files(config_dir)
    manifest = config_dir / "node_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "nodes": [
                    {
                        "node_id": "mcb44_drive_main",
                        "role": "drive",
                        "required": True,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return config_dir, manifest


def _command_types(runtime: FakeFleetDashboardRuntime) -> list[str]:
    serial = runtime.controller.serial
    assert serial is not None
    return [str(message["type"]) for message in serial.writes]


def _real_runtime_over_virtual_serial(
    tmp_path: Path,
    clock: ManualClock,
    *,
    motion_enabled: bool,
) -> tuple[RealFleetDashboardRuntime, MutableControllerInput]:
    config_dir, manifest = _config_and_manifest(tmp_path)
    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    vehicle["motion"].update(
        {
            "wheelbase_m": 0.327,
            "track_width_m": 0.327,
            "wheel_diameter_m": 0.055,
            "max_wheel_rpm": 520.0,
            "max_linear_speed_mps": 1.5,
            "max_angular_speed_radps": 4.0,
            "open_loop_max_pwm": 300,
            "pivot_max_pwm": 600,
        }
    )
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(json.dumps(vehicle) + "\n", encoding="utf-8")
    args = build_arg_parser().parse_args(
        ["--config-dir", str(config_dir), "--no-joystick"]
    )
    controller = ControllerApp(args, now_ms=clock)
    device = SimulatedEsp32(clock_ms=clock)
    controller.serial = VirtualSerialLink(device, now_ms=clock)
    controller.reconnect_active = True
    controller.reconnect_phase = "ready"
    source = MutableControllerInput()
    runtime = RealFleetDashboardRuntime(
        controller,
        robot_id=RobotId.R2,
        node_requirements=tuple(),
        controller_input=source,
        motion_enabled=motion_enabled,
        max_pwm=120,
    )
    assert manifest.exists()
    return runtime, source


def test_fake_runtime_owns_one_controller_and_starts_ready_disarmed(tmp_path: Path) -> None:
    config_dir, manifest = _config_and_manifest(tmp_path)
    clock = ManualClock()
    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R2,
        config_dir=config_dir,
        node_manifest=manifest,
        now_ms=clock,
    )

    fleet = runtime.start()

    assert fleet.selected_robot == RobotId.R2
    assert fleet.robot(RobotId.R1).configured is False
    r2 = fleet.robot(RobotId.R2)
    assert r2.backend == BackendKind.FAKE_ESP32
    assert r2.connection == ConnectionState.ONLINE
    assert r2.safety_state == "SAFE"
    assert r2.safe is True
    assert r2.ready is True
    assert r2.armed is False
    assert runtime.controller.safety.state == SafetyState.SAFE
    assert runtime.controller.fake_device is not None
    assert runtime.controller.fake_device.armed is False
    assert _command_types(runtime) == ["disarm", "hello", "config"]
    assert "arm" not in _command_types(runtime)


def test_runtime_ticks_zero_input_and_selection_never_sends_arm(tmp_path: Path) -> None:
    config_dir, manifest = _config_and_manifest(tmp_path)
    clock = ManualClock()
    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R1,
        config_dir=config_dir,
        node_manifest=manifest,
        now_ms=clock,
    )
    runtime.start()

    clock.ms = 100
    fleet = runtime.tick()
    assert fleet.selected_robot == RobotId.R1
    assert fleet.robot(RobotId.R1).motion.magnitude == 0.0
    assert runtime.controller.last_motion_request == (0.0, 0.0, 0.0)

    selected = runtime.select_robot(RobotId.R2)
    assert selected.selected_robot == RobotId.R2
    assert selected.selected.configured is False
    assert selected.robot(RobotId.R1).backend == BackendKind.FAKE_ESP32
    assert _command_types(runtime) == ["disarm", "hello", "config"]

    with pytest.raises(ValueError, match="RobotId"):
        runtime.select_robot("R1")  # type: ignore[arg-type]


def test_fake_runtime_reconnects_to_ready_disarmed_without_arm(tmp_path: Path) -> None:
    config_dir, manifest = _config_and_manifest(tmp_path)
    clock = ManualClock()
    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R2,
        config_dir=config_dir,
        node_manifest=manifest,
        now_ms=clock,
    )
    runtime.start()
    original_link = runtime.controller.serial
    assert original_link is not None
    assert runtime.controller.fake_device is not None
    runtime.controller.fake_device.disconnect()

    clock.ms = 20
    disconnected = runtime.tick().robot(RobotId.R2)
    assert disconnected.connection == ConnectionState.RECONNECTING
    assert disconnected.safe is True
    assert disconnected.armed is False

    clock.ms = 1020
    runtime.tick()
    replacement_link = runtime.controller.serial
    assert replacement_link is not None
    assert replacement_link is not original_link
    clock.ms = 1021
    recovered = runtime.tick().robot(RobotId.R2)

    assert recovered.connection == ConnectionState.ONLINE
    assert recovered.safety_state == "SAFE"
    # Reconnect is transport/config ready, while the first disconnect cause
    # remains latched for operator diagnostics and therefore keeps GUI READY
    # false until a later explicit diagnostic epoch clears it.
    assert recovered.ready is False
    assert recovered.fault == "serial read failed"
    assert recovered.armed is False
    assert runtime.controller.reconnect_phase == "ready_disarmed"
    assert all(message["type"] != "arm" for message in original_link.writes)
    assert all(message["type"] != "arm" for message in replacement_link.writes)


def test_runtime_close_is_idempotent_and_finishes_disarmed(tmp_path: Path) -> None:
    config_dir, manifest = _config_and_manifest(tmp_path)
    runtime = FakeFleetDashboardRuntime.create(
        robot_id=RobotId.R2,
        config_dir=config_dir,
        node_manifest=manifest,
    )
    runtime.start()
    link = runtime.controller.serial
    assert link is not None

    runtime.close()
    runtime.close()

    assert link.closed is True
    assert [message["type"] for message in link.writes].count("disarm") == 2
    assert all(message["type"] != "arm" for message in link.writes)
    assert runtime.controller.safety.state == SafetyState.SAFE
    assert runtime.controller.safety.armed is False
    assert runtime.controller.fake_device is not None
    assert runtime.controller.fake_device.motor_pwm == [0, 0, 0, 0]
    with pytest.raises(RuntimeError, match="closed"):
        runtime.tick()


def test_real_r2_runtime_defaults_to_output_disabled_and_locks_robot_view(tmp_path: Path) -> None:
    clock = ManualClock()
    runtime, source = _real_runtime_over_virtual_serial(
        tmp_path,
        clock,
        motion_enabled=False,
    )

    fleet = runtime.start()
    serial = runtime.controller.serial
    assert serial is not None
    assert fleet.selected_robot == RobotId.R2
    assert fleet.robot(RobotId.R2).backend == BackendKind.REAL_SERIAL
    assert fleet.robot(RobotId.R2).connection == ConnectionState.ONLINE
    assert runtime.controller.config["motion"]["open_loop_max_pwm"] == 120
    assert runtime.controller.config["motion"]["pivot_max_pwm"] == 120
    assert [message["type"] for message in serial.writes] == ["disarm", "hello", "config"]

    source.state = ControllerState(
        connected=True,
        name="test controller",
        vx=1.0,
        arm_pressed=True,
    )
    clock.ms = 2000
    runtime.tick()
    controller_status = runtime.controller_input_snapshot()
    assert controller_status.connected is True
    assert controller_status.name == "test controller"
    assert controller_status.vx == 1.0
    assert controller_status.arm_pressed is True
    assert all(message["type"] not in {"arm", "drive"} for message in serial.writes)
    assert runtime.select_robot(RobotId.R1).selected_robot == RobotId.R2
    runtime.close()


def test_real_r2_runtime_explicit_motion_uses_normal_arm_and_120_pwm_clamp(tmp_path: Path) -> None:
    clock = ManualClock()
    runtime, source = _real_runtime_over_virtual_serial(
        tmp_path,
        clock,
        motion_enabled=True,
    )
    runtime.start()
    serial = runtime.controller.serial
    assert serial is not None

    # Startup requires one release before the normal one-second ARM hold.
    source.state = ControllerState(connected=True, name="test controller")
    clock.ms = 20
    runtime.tick()
    source.state = ControllerState(
        connected=True,
        name="test controller",
        arm_pressed=True,
    )
    clock.ms = 100
    runtime.tick()
    clock.ms = 1100
    runtime.tick()
    assert runtime.controller.safety.armed is True
    assert [message["type"] for message in serial.writes].count("arm") == 1

    source.state = ControllerState(
        connected=True,
        name="test controller",
        vx=1.0,
    )
    clock.ms = 1150
    fleet = runtime.tick()
    drive = runtime.controller.last_drive_command
    assert drive is not None
    assert drive["type"] == "drive"
    assert max(abs(float(value)) for value in drive["drive_target"]) <= 120
    assert fleet.robot(RobotId.R2).armed is True

    runtime.close()
    assert runtime.controller.safety.armed is False
    assert [message["type"] for message in serial.writes][-1] == "disarm"


def test_real_r2_runtime_live_applies_settings_and_stays_safe(tmp_path: Path) -> None:
    clock = ManualClock()
    runtime, source = _real_runtime_over_virtual_serial(
        tmp_path,
        clock,
        motion_enabled=False,
    )
    runtime.start()
    serial = runtime.controller.serial
    assert serial is not None
    vehicle = copy.deepcopy(runtime.controller.config)
    mapping = copy.deepcopy(runtime.controller.mapping)
    vehicle["config_revision"] += 1
    vehicle["motion"]["open_loop_max_pwm"] = 75
    vehicle["motion"]["pivot_max_pwm"] = 70
    mapping["deadzone"] = 0.2

    fleet = runtime.apply_settings(vehicle, mapping)

    assert runtime.controller.config["motion"]["open_loop_max_pwm"] == 75
    assert runtime.controller.config["motion"]["pivot_max_pwm"] == 70
    assert runtime.controller.mapping["deadzone"] == pytest.approx(0.2)
    assert source.mapping["deadzone"] == pytest.approx(0.2)
    assert runtime.controller.reconnect_phase == "ready_disarmed"
    assert runtime.controller.safety.state == SafetyState.SAFE
    assert runtime.controller.safety.config_accepted is True
    assert runtime.controller.safety.armed is False
    assert fleet.robot(RobotId.R2).armed is False
    assert [message["type"] for message in serial.writes][-2:] == ["disarm", "config"]
    assert all(message["type"] not in {"arm", "drive"} for message in serial.writes)
    runtime.close()


def test_real_r2_runtime_rejects_live_apply_while_armed(tmp_path: Path) -> None:
    clock = ManualClock()
    runtime, _ = _real_runtime_over_virtual_serial(
        tmp_path,
        clock,
        motion_enabled=True,
    )
    runtime.start()
    vehicle = copy.deepcopy(runtime.controller.config)
    mapping = copy.deepcopy(runtime.controller.mapping)
    runtime.controller.safety.arm(clock.ms)

    with pytest.raises(RuntimeError, match="SAFE and disarmed"):
        runtime.apply_settings(vehicle, mapping)

    runtime.close()
