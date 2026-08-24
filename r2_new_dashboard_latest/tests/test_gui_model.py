from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from pc_controller.app import ControllerApp
from pc_controller.autonomy import AutonomyStateMachine, MissionPlan, MissionStep, RobotId
from pc_controller.competition import CompetitionState
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_model import (
    BackendKind,
    ConnectionState,
    DisplaySeverity,
    NodeDisplayState,
    build_fleet_dashboard_snapshot,
    build_robot_dashboard_snapshot,
)
from pc_controller.node_inventory import NodeRequirement, evaluate_node_inventory
from pc_controller.protocol import arm_message, encode_message, hello_message
from pc_controller.serial_discovery import SerialProbe
from pc_controller.safety import SafetyState


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _seed_armable_config(config_dir: Path) -> None:
    ensure_config_files(config_dir)
    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(json.dumps(vehicle, indent=2) + "\n", encoding="utf-8")


def _args(config_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        config_dir=str(config_dir),
        simulate=False,
        fake_esp32=True,
        fake_trace=False,
        port=None,
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


def _ready_fake_app(tmp_path: Path) -> tuple[ControllerApp, ManualClock]:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    app = ControllerApp(_args(tmp_path), now_ms=clock)
    assert app.serial is not None
    app.safety.apply_config()
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    assert app.safety.config_accepted is True
    return app, clock


def _arm(app: ControllerApp, clock: ManualClock) -> None:
    assert app.serial is not None
    clock.ms += 10
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()
    assert app.safety.state == SafetyState.NORMAL


def test_fake_controller_builds_ready_disarmed_shared_snapshot(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    requirements = (NodeRequirement("mcb44_drive_main", "drive", True),)

    snapshot = build_robot_dashboard_snapshot(
        app,
        RobotId.R2,
        now_ms=clock.ms,
        node_requirements=requirements,
    )

    assert snapshot.backend == BackendKind.FAKE_ESP32
    assert snapshot.connection == ConnectionState.ONLINE
    assert snapshot.safe is True
    assert snapshot.ready is True
    assert snapshot.armed is False
    assert snapshot.safety_state == "SAFE"
    assert snapshot.drive_type == "4WIS"
    assert (
        snapshot.controller_mapping.axis_vx,
        snapshot.controller_mapping.axis_vy,
        snapshot.controller_mapping.axis_omega,
    ) == (1, 0, 2)
    assert (
        snapshot.controller_mapping.invert_vx,
        snapshot.controller_mapping.invert_vy,
        snapshot.controller_mapping.invert_omega,
    ) == (True, True, True)
    assert snapshot.machine_coordinate.x_positive == "FORWARD"
    assert snapshot.machine_coordinate.y_positive == "LEFT"
    assert snapshot.machine_coordinate.omega_positive == "CCW"
    assert snapshot.machine_coordinate.pivot_direction_inverted is False
    assert [(node.node_id, node.state) for node in snapshot.nodes] == [
        ("mcb44_drive_main", NodeDisplayState.PRESENT)
    ]


def test_backend_kinds_remain_visibly_distinct_without_hardware(tmp_path: Path) -> None:
    _seed_armable_config(tmp_path)
    clock = ManualClock()
    simulation_args = _args(tmp_path)
    simulation_args.fake_esp32 = False
    simulation_args.simulate = True
    simulation = ControllerApp(simulation_args, now_ms=clock)
    real_args = _args(tmp_path)
    real_args.fake_esp32 = False
    real = ControllerApp(real_args, now_ms=clock)

    simulation_snapshot = build_robot_dashboard_snapshot(simulation, RobotId.R1, now_ms=0)
    real_snapshot = build_robot_dashboard_snapshot(real, RobotId.R1, now_ms=0)

    assert simulation_snapshot.backend == BackendKind.LEGACY_SIMULATION
    assert simulation_snapshot.connection == ConnectionState.ONLINE
    assert real_snapshot.backend == BackendKind.REAL_SERIAL
    assert real_snapshot.connection == ConnectionState.OFFLINE


def test_motion_vector_and_wheels_come_from_controller_command_and_telemetry(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    _arm(app, clock)
    clock.ms += 20
    app.tick(0.3, 0.4, -0.2)

    snapshot = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)

    assert snapshot.motion.vx == pytest.approx(0.3)
    assert snapshot.motion.vy == pytest.approx(0.4)
    assert snapshot.motion.magnitude == pytest.approx(0.5)
    assert snapshot.motion.heading_deg == pytest.approx(53.130102)
    assert snapshot.motion.rotation_direction == "CW"
    assert snapshot.motion.accepted_by_safety is True
    assert snapshot.armed is True
    assert len(snapshot.wheels) == 4
    assert all(wheel.command_control == "pwm" for wheel in snapshot.wheels)
    assert all(wheel.command_target is not None for wheel in snapshot.wheels)
    assert all(wheel.observed_rpm is not None for wheel in snapshot.wheels)
    assert all(wheel.observed_steering_deg is not None for wheel in snapshot.wheels)


def test_fake_fault_is_prominent_and_disarms_without_gui_side_channel(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    _arm(app, clock)
    assert app.fake_device is not None
    app.fake_device.faults.explicit_fault = "GUI-visible injected fault"
    clock.ms += 20
    app.tick(0.1, 0.0, 0.0)

    snapshot = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)

    assert snapshot.safety_state == "SAFE"
    assert snapshot.safe is True
    assert snapshot.armed is False
    assert snapshot.ready is False
    assert snapshot.severity == DisplaySeverity.ERROR
    assert snapshot.fault == "ESP32 reported SAFE"
    assert snapshot.fault_event is not None
    assert snapshot.fault_event.source == "ESP32"
    assert snapshot.fault_event.reason == "GUI-visible injected fault"
    assert snapshot.fault_event.node_id == "mcb44_drive_main"
    assert snapshot.fault_event.timestamp_ms == clock.ms
    assert snapshot.fault_event.safety_response == "SAFE/DISARMED"
    assert app.fake_device.armed is False
    assert app.fake_device.motor_pwm == [0, 0, 0, 0]

    # Consume the acknowledgement to the fail-safe DISARM before beginning a
    # new config diagnostic epoch, matching the normal reconnect handshake.
    app._read_serial_messages()
    app.safety.apply_config()
    assert app.serial is not None
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    recovered = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)
    assert recovered.fault is None
    assert recovered.fault_event is None


def test_reconnect_and_node_inventory_fail_closed_in_snapshot(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    requirements = (NodeRequirement("mcb44_drive_main", "drive", True),)
    assert app.fake_device is not None
    app.fake_device.disconnect()
    clock.ms += 20
    app.tick(0.0, 0.0, 0.0)

    snapshot = build_robot_dashboard_snapshot(
        app,
        RobotId.R2,
        now_ms=clock.ms,
        node_requirements=requirements,
    )

    assert snapshot.connection == ConnectionState.RECONNECTING
    assert snapshot.ready is False
    assert snapshot.armed is False
    assert snapshot.nodes[0].state == NodeDisplayState.MISSING
    assert snapshot.severity == DisplaySeverity.ERROR


def test_duplicate_inventory_is_not_collapsed_to_one_gui_node(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    identity = app.fake_device.node_identity() if app.fake_device is not None else {}
    requirements = (NodeRequirement("mcb44_drive_main", "drive", True),)
    report = evaluate_node_inventory(
        requirements,
        (
            SerialProbe("SIM://one", identity=dict(identity)),
            SerialProbe("SIM://two", identity=dict(identity)),
        ),
    )

    snapshot = build_robot_dashboard_snapshot(
        app,
        RobotId.R2,
        now_ms=clock.ms,
        node_inventory=report,
    )

    assert snapshot.ready is False
    assert snapshot.nodes[0].state == NodeDisplayState.DUPLICATE
    assert snapshot.nodes[0].ports == ("SIM://one", "SIM://two")
    assert any("multiple ports" in warning for warning in snapshot.warnings)


def test_autonomy_and_competition_state_are_read_only_context(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    machine = AutonomyStateMachine(
        MissionPlan("field_mission", RobotId.R1, (MissionStep("collect_block"),))
    )
    machine.prepare(clock.ms, required_nodes_ready=True, safety_ready=True)

    snapshot = build_robot_dashboard_snapshot(
        app,
        RobotId.R1,
        now_ms=clock.ms,
        autonomy=machine,
        competition_state=CompetitionState.READY_DISARMED,
    )

    assert snapshot.autonomy.state == "READY_DISARMED"
    assert snapshot.autonomy.configured is True
    assert snapshot.autonomy.mission_id == "field_mission"
    assert snapshot.autonomy.step_index == 0
    assert snapshot.autonomy.step_count == 1
    assert snapshot.autonomy.current_step == "collect_block"
    assert snapshot.autonomy.next_step is None
    assert snapshot.autonomy.failure_action == "STOP"
    assert snapshot.autonomy.configured_fallback_id is None
    assert snapshot.autonomy.recent_events[-1].event == "ready_disarmed"
    assert snapshot.competition_state == "READY_DISARMED"
    with pytest.raises(ValueError, match="does not match"):
        build_robot_dashboard_snapshot(app, RobotId.R2, autonomy=machine)


def test_fleet_snapshot_keeps_unbound_robot_unknown(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    r2 = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)

    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=clock.ms)

    assert fleet.selected_robot == RobotId.R1
    assert fleet.selected.configured is False
    assert fleet.selected.connection == ConnectionState.OFFLINE
    assert fleet.robot(RobotId.R2).backend == BackendKind.FAKE_ESP32
    assert fleet.robot(RobotId.R1).nodes == ()
    assert fleet.robot(RobotId.R1).controller_mapping.axis_vx is None
    assert fleet.robot(RobotId.R1).machine_coordinate.max_linear_speed_mps is None
    with pytest.raises(ValueError, match="robot_id"):
        build_fleet_dashboard_snapshot("R1", (r2,), now_ms=clock.ms)  # type: ignore[arg-type]


def test_invalid_optional_telemetry_is_rendered_unknown_not_crashed(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    app.last_telemetry = {
        "type": "telemetry",
        "wheel_rpm": [1.0, float("nan"), 3.0, 4.0],
        "motor_pwm": [10**10000, 2, 3, 4],
        "servo_deg": [0.0, 1.0],
        "battery_v": 10**10000,
    }

    snapshot = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)

    assert all(wheel.observed_rpm is None for wheel in snapshot.wheels)
    assert all(wheel.observed_pwm is None for wheel in snapshot.wheels)
    assert snapshot.wheels[0].observed_steering_deg == 0.0
    assert snapshot.wheels[2].observed_steering_deg is None
    assert snapshot.battery_voltage_v is None
