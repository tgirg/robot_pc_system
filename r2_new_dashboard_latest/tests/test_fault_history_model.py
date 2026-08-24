from __future__ import annotations

import argparse
import json
from pathlib import Path

from pc_controller.app import ControllerApp
from pc_controller.autonomy import RobotId
from pc_controller.config_manager import ensure_config_files
from pc_controller.gui_fault_history_model import FaultHistoryStore
from pc_controller.gui_model import DisplaySeverity, build_fleet_dashboard_snapshot, build_robot_dashboard_snapshot
from pc_controller.node_inventory import NodeRequirement, evaluate_node_inventory
from pc_controller.protocol import arm_message, encode_message, hello_message
from pc_controller.serial_discovery import SerialProbe


class ManualClock:
    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms


def _ready_fake_app(config_dir: Path) -> tuple[ControllerApp, ManualClock]:
    ensure_config_files(config_dir)
    vehicle_path = config_dir / "vehicle_config.json"
    vehicle = json.loads(vehicle_path.read_text(encoding="utf-8"))
    for servo in vehicle["servos"]:
        servo["calibrated"] = True
    vehicle_path.write_text(json.dumps(vehicle, indent=2) + "\n", encoding="utf-8")
    args = argparse.Namespace(
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
    clock = ManualClock()
    app = ControllerApp(args, now_ms=clock)
    assert app.serial is not None
    app.safety.apply_config()
    app.serial.write(encode_message(hello_message()))
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    return app, clock


def _arm(app: ControllerApp, clock: ManualClock) -> None:
    assert app.serial is not None
    clock.ms += 10
    app.safety.request_arm(clock.ms)
    app.serial.write(encode_message(arm_message("normal")))
    app._read_serial_messages()


def _explicit_fault_snapshot(app: ControllerApp, clock: ManualClock):
    _arm(app, clock)
    assert app.fake_device is not None
    app.fake_device.faults.explicit_fault = "history-visible fault"
    clock.ms += 20
    app.tick(0.1, 0.0, 0.0)
    return build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)


def test_history_keeps_safety_root_cause_and_structured_esp32_event_separate(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    robot = _explicit_fault_snapshot(app, clock)

    active = robot.diagnostic_events
    assert [(event.source, event.reason) for event in active] == [
        ("PC_SAFETY", "ESP32 reported SAFE"),
        ("ESP32", "history-visible fault"),
    ]

    store = FaultHistoryStore()
    history = store.ingest(robot)
    by_source = {entry.source: entry for entry in history.entries}
    assert history.active_count == 2
    assert by_source["PC_SAFETY"].timestamp_basis == "FIRST_OBSERVED"
    assert by_source["PC_SAFETY"].timestamp_ms == robot.timestamp_ms
    assert by_source["ESP32"].timestamp_basis == "SOURCE"
    assert by_source["ESP32"].node_id == "mcb44_drive_main"
    assert by_source["ESP32"].fault_flags == 1
    assert by_source["ESP32"].safety_response == "SAFE/DISARMED"

    repeated = store.ingest(robot)
    assert len(repeated.entries) == 2
    acknowledged = store.acknowledge(RobotId.R2, by_source["PC_SAFETY"].event_id)
    assert acknowledged.unacknowledged_count == 1
    assert app.safety.fault == "ESP32 reported SAFE"


def test_history_closes_events_without_erasing_them_or_their_acknowledgement(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    robot = _explicit_fault_snapshot(app, clock)
    store = FaultHistoryStore()
    history = store.ingest(robot)
    event_id = history.entries[0].event_id
    store.acknowledge(RobotId.R2, event_id)

    assert app.serial is not None
    app._read_serial_messages()
    app.safety.apply_config()
    app.serial.write(encode_message(app.config))
    app._read_serial_messages()
    clock.ms += 20
    recovered = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms)
    history = store.ingest(recovered)

    assert history.active_count == 0
    assert len(history.entries) == 2
    assert next(entry for entry in history.entries if entry.event_id == event_id).acknowledged is True
    assert all(entry.active is False for entry in history.entries)


def test_warning_stop_and_inventory_events_keep_distinct_sources_and_responses(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    app.safety.arm(0)
    assert app.safety.update_timeout(250) == "warn"
    identity = dict(app.node_identity or {})
    report = evaluate_node_inventory(
        (
            NodeRequirement("mcb44_drive_main", "drive", True),
            NodeRequirement("optional_sensor", "sensor", False),
        ),
        (SerialProbe("SIM://fake-esp32", identity=identity),),
    )
    robot = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=250, node_inventory=report)

    events = {(event.source, event.reason): event for event in robot.diagnostic_events}
    warning = events[("PC_SAFETY", "communication timeout warning")]
    inventory = next(event for event in robot.diagnostic_events if event.source == "NODE_INVENTORY")
    assert warning.severity == DisplaySeverity.WARNING
    assert warning.safety_response == "WARNING_ONLY"
    assert inventory.severity == DisplaySeverity.WARNING
    assert inventory.safety_response == "NONE"

    store = FaultHistoryStore()
    store.ingest(robot)
    assert app.safety.update_timeout(350) == "stop"
    stopped = build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=350, node_inventory=report)
    history = store.ingest(stopped)
    stop_entry = next(entry for entry in history.entries if entry.reason == "drive stopped by communication timeout")
    assert stop_entry.safety_response == "STOP_OUTPUT"
    assert history.active_count == 3


def test_fleet_history_isolated_by_robot_and_acknowledgement_is_local(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    r2 = _explicit_fault_snapshot(app, clock)
    fleet = build_fleet_dashboard_snapshot(RobotId.R1, (r2,), now_ms=clock.ms)
    store = FaultHistoryStore()

    r1_history = store.ingest_fleet(fleet)
    assert [entry.source for entry in r1_history.entries] == ["GUI_BINDING"]
    r1_event = r1_history.entries[0]
    store.acknowledge(RobotId.R1, r1_event.event_id)

    r2_history = store.build(fleet.robot(RobotId.R2))
    assert len(r2_history.entries) == 2
    assert all(entry.acknowledged is False for entry in r2_history.entries)
    assert store.build(fleet.robot(RobotId.R1)).entries[0].acknowledged is True


def test_history_retention_is_bounded_per_robot(tmp_path: Path) -> None:
    app, clock = _ready_fake_app(tmp_path)
    store = FaultHistoryStore(max_entries_per_robot=2)

    for index in range(3):
        app.safety.disarm(f"fault-{index}")
        clock.ms += 10
        store.ingest(build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms))
        app.safety.apply_config()
        clock.ms += 10
        store.ingest(build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms))

    history = store.build(build_robot_dashboard_snapshot(app, RobotId.R2, now_ms=clock.ms))
    assert len(history.entries) == 2
    assert [entry.reason for entry in history.entries] == ["fault-2", "fault-1"]
