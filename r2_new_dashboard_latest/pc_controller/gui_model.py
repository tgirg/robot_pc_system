"""Read-only GUI state derived from the real controller state path.

This module intentionally owns no transport and exposes no ARM, drive, or
calibration command API.  Renderers consume immutable snapshots built from a
``ControllerApp`` so real serial, VirtualSerial/Fake ESP32, and legacy direct
simulation remain visibly distinct while sharing the same state mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import degrees, hypot, isfinite, atan2
from typing import Any, Iterable, Mapping

from .autonomy import AutonomyStateMachine, RobotId
from .competition import CompetitionState
from .node_inventory import NodeInventoryReport, NodeRequirement, evaluate_node_inventory
from .safety import SafetyState
from .serial_discovery import SerialProbe


class BackendKind(str, Enum):
    UNBOUND = "UNBOUND"
    REAL_SERIAL = "REAL_SERIAL"
    FAKE_ESP32 = "FAKE_ESP32"
    LEGACY_SIMULATION = "LEGACY_SIMULATION"


class ConnectionState(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    RECONNECTING = "RECONNECTING"
    BLOCKED = "BLOCKED"


class NodeDisplayState(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    OPTIONAL_MISSING = "OPTIONAL_MISSING"
    DUPLICATE = "DUPLICATE"
    WRONG_ROLE = "WRONG_ROLE"
    UNEXPECTED = "UNEXPECTED"


class DisplaySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MotionVectorSnapshot:
    vx: float
    vy: float
    omega: float
    magnitude: float
    heading_deg: float | None
    rotation_direction: str
    accepted_by_safety: bool


@dataclass(frozen=True)
class ControllerInputMappingSnapshot:
    axis_vx: int | None
    axis_vy: int | None
    axis_omega: int | None
    invert_vx: bool | None
    invert_vy: bool | None
    invert_omega: bool | None
    deadzone: float | None
    linear_scale: float | None
    angular_scale: float | None
    logical_front: str | None


@dataclass(frozen=True)
class MachineCoordinateSnapshot:
    x_positive: str
    y_positive: str
    omega_positive: str
    max_linear_speed_mps: float | None
    max_angular_speed_radps: float | None
    pivot_direction_inverted: bool | None


@dataclass(frozen=True)
class MotionParameterSourceSnapshot:
    """Controller-loaded PC motion limits used by local GUI parameter drafts."""

    open_loop_max_pwm: float | None
    pivot_max_pwm: float | None


@dataclass(frozen=True)
class WheelSnapshot:
    logical_index: int
    name: str
    configured: bool
    motor_inverted: bool | None
    servo_inverted: bool | None
    servo_channel: int | None
    servo_center_us: int | None
    servo_min_us: int | None
    servo_max_us: int | None
    servo_trim_deg: float | None
    servo_min_angle_deg: float | None
    servo_max_angle_deg: float | None
    servo_calibrated: bool | None
    command_control: str | None
    command_target: float | None
    command_direction: str
    commanded_steering_deg: float | None
    observed_rpm: float | None
    observed_pwm: float | None
    observed_steering_deg: float | None
    encoder_count: int | None
    fault: str | None


@dataclass(frozen=True)
class NodeSnapshot:
    node_id: str
    role: str
    required: bool
    state: NodeDisplayState
    ports: tuple[str, ...]


@dataclass(frozen=True)
class AutonomyEventSnapshot:
    timestamp_ms: int
    state: str
    event: str
    step_id: str | None
    attempt: int | None
    reason: str | None


@dataclass(frozen=True)
class AutonomySnapshot:
    configured: bool
    state: str | None
    mission_id: str | None
    step_index: int | None
    step_count: int | None
    current_step: str | None
    next_step: str | None
    attempt: int | None
    max_retries: int | None
    retry_delay_ms: int | None
    retry_deadline_ms: int | None
    failure_action: str | None
    fallback_id: str | None
    configured_fallback_id: str | None
    reason: str | None
    skipped_steps: tuple[str, ...]
    recent_events: tuple[AutonomyEventSnapshot, ...]


@dataclass(frozen=True)
class FaultSnapshot:
    severity: DisplaySeverity
    source: str
    node_id: str | None
    reason: str
    timestamp_ms: int | None
    fault_flags: int | None
    safety_response: str


@dataclass(frozen=True)
class DiagnosticEventSnapshot:
    """One currently active diagnostic event with source semantics intact."""

    severity: DisplaySeverity
    source: str
    node_id: str | None
    reason: str
    timestamp_ms: int | None
    fault_flags: int | None
    safety_response: str


@dataclass(frozen=True)
class RobotDashboardSnapshot:
    robot_id: RobotId
    timestamp_ms: int
    configured: bool
    backend: BackendKind
    connection: ConnectionState
    controller_connected: bool
    controller_name: str | None
    safety_state: str
    safe: bool
    ready: bool
    armed: bool
    arm_pending: bool
    fault: str | None
    fault_event: FaultSnapshot | None
    diagnostic_events: tuple[DiagnosticEventSnapshot, ...]
    severity: DisplaySeverity
    reconnect_phase: str | None
    communication_age_ms: int | None
    telemetry_age_ms: int | None
    telemetry_sequence: int | None
    telemetry_fault_flags: int | None
    battery_voltage_v: float | None
    battery_percent: float | None
    drive_type: str
    controller_mapping: ControllerInputMappingSnapshot
    machine_coordinate: MachineCoordinateSnapshot
    motion_parameters: MotionParameterSourceSnapshot
    motion: MotionVectorSnapshot
    wheels: tuple[WheelSnapshot, ...]
    nodes: tuple[NodeSnapshot, ...]
    autonomy: AutonomySnapshot
    competition_state: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FleetDashboardSnapshot:
    selected_robot: RobotId
    robots: tuple[RobotDashboardSnapshot, ...]

    def robot(self, robot_id: RobotId) -> RobotDashboardSnapshot:
        for snapshot in self.robots:
            if snapshot.robot_id == robot_id:
                return snapshot
        raise KeyError(robot_id)

    @property
    def selected(self) -> RobotDashboardSnapshot:
        return self.robot(self.selected_robot)


def build_robot_dashboard_snapshot(
    controller: Any,
    robot_id: RobotId,
    *,
    now_ms: int | None = None,
    node_requirements: Iterable[NodeRequirement] = (),
    node_inventory: NodeInventoryReport | None = None,
    autonomy: AutonomyStateMachine | None = None,
    competition_state: CompetitionState | None = None,
) -> RobotDashboardSnapshot:
    """Build one immutable GUI snapshot without changing controller state."""
    _require_robot_id(robot_id)
    if autonomy is not None and autonomy.plan.robot_id != robot_id:
        raise ValueError("autonomy robot_id does not match dashboard robot_id")
    if competition_state is not None and not isinstance(competition_state, CompetitionState):
        raise ValueError("competition_state must be a CompetitionState")

    timestamp_ms = int(controller._now_ms() if now_ms is None else now_ms)
    safety = controller.safety
    backend = _backend_kind(controller)
    connection = _connection_state(controller, backend)
    online = connection == ConnectionState.ONLINE
    telemetry = controller.last_telemetry if isinstance(controller.last_telemetry, dict) else {}
    identity = controller.node_identity if isinstance(controller.node_identity, dict) else None
    requirements = tuple(node_requirements)
    report = node_inventory or _current_node_report(controller, requirements, identity, online)
    nodes = _node_snapshots(report)
    node_ready = report.ready if report is not None else (online and (identity is not None or backend == BackendKind.LEGACY_SIMULATION))

    fault_flags = _optional_int(telemetry.get("fault_flags"))
    fault = safety.fault
    if fault is None and fault_flags not in (None, 0):
        fault = f"ESP32 fault_flags={fault_flags}"

    warnings = _warnings(controller, report, fault_flags)
    ready = bool(
        online
        and safety.config_accepted
        and node_ready
        and fault is None
        and connection != ConnectionState.BLOCKED
    )
    safe = safety.state == SafetyState.SAFE and not safety.armed
    severity = DisplaySeverity.ERROR if fault or connection == ConnectionState.BLOCKED or not node_ready else (
        DisplaySeverity.WARNING if warnings else DisplaySeverity.INFO
    )

    last_motion = getattr(controller, "last_motion_request", (0.0, 0.0, 0.0))
    motion = _motion_snapshot(last_motion, safety.state == SafetyState.NORMAL and bool(safety.armed))
    command = getattr(controller, "last_drive_command", None)
    wheels = _wheel_snapshots(controller.config, telemetry, command)
    controller_mapping = _controller_mapping_snapshot(getattr(controller, "mapping", {}))
    machine_coordinate = _machine_coordinate_snapshot(controller.config)
    motion_parameters = _motion_parameter_source_snapshot(controller.config)
    fault_event = _fault_snapshot(controller, fault, fault_flags)

    return RobotDashboardSnapshot(
        robot_id=robot_id,
        timestamp_ms=timestamp_ms,
        configured=True,
        backend=backend,
        connection=connection,
        controller_connected=bool(getattr(controller, "last_connected", False)),
        controller_name=_controller_name(controller),
        safety_state=safety.state.value,
        safe=safe,
        ready=ready,
        armed=bool(safety.armed),
        arm_pending=safety.state == SafetyState.ARM_PENDING,
        fault=fault,
        fault_event=fault_event,
        diagnostic_events=_diagnostic_events(controller, fault_flags, report),
        severity=severity,
        reconnect_phase=str(getattr(controller, "reconnect_phase", "")) or None,
        communication_age_ms=_age(timestamp_ms, safety.last_rx_ms),
        telemetry_age_ms=_age(timestamp_ms, safety.last_valid_telemetry_ms),
        telemetry_sequence=safety.last_telemetry_seq,
        telemetry_fault_flags=fault_flags,
        battery_voltage_v=_first_optional_float(telemetry, "battery_voltage_v", "battery_v"),
        battery_percent=_first_optional_float(telemetry, "battery_percent", "battery_pct"),
        drive_type=_drive_type(controller.config),
        controller_mapping=controller_mapping,
        machine_coordinate=machine_coordinate,
        motion_parameters=motion_parameters,
        motion=motion,
        wheels=wheels,
        nodes=nodes,
        autonomy=_autonomy_snapshot(autonomy),
        competition_state=competition_state.value if competition_state is not None else None,
        warnings=warnings,
    )


def build_fleet_dashboard_snapshot(
    selected_robot: RobotId,
    snapshots: Iterable[RobotDashboardSnapshot],
    *,
    now_ms: int,
) -> FleetDashboardSnapshot:
    """Compose R1/R2 without copying one robot's state into the other."""
    _require_robot_id(selected_robot)
    by_robot: dict[RobotId, RobotDashboardSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.robot_id in by_robot:
            raise ValueError(f"duplicate dashboard snapshot for {snapshot.robot_id.value}")
        by_robot[snapshot.robot_id] = snapshot
    robots = tuple(
        by_robot.get(robot_id, _unbound_snapshot(robot_id, int(now_ms)))
        for robot_id in (RobotId.R1, RobotId.R2)
    )
    return FleetDashboardSnapshot(selected_robot=selected_robot, robots=robots)


def _unbound_snapshot(robot_id: RobotId, now_ms: int) -> RobotDashboardSnapshot:
    return RobotDashboardSnapshot(
        robot_id=robot_id,
        timestamp_ms=now_ms,
        configured=False,
        backend=BackendKind.UNBOUND,
        connection=ConnectionState.OFFLINE,
        controller_connected=False,
        controller_name=None,
        safety_state="UNKNOWN",
        safe=False,
        ready=False,
        armed=False,
        arm_pending=False,
        fault=None,
        fault_event=None,
        diagnostic_events=(
            DiagnosticEventSnapshot(
                DisplaySeverity.WARNING,
                "GUI_BINDING",
                None,
                "robot controller is not configured",
                None,
                None,
                "NONE",
            ),
        ),
        severity=DisplaySeverity.WARNING,
        reconnect_phase=None,
        communication_age_ms=None,
        telemetry_age_ms=None,
        telemetry_sequence=None,
        telemetry_fault_flags=None,
        battery_voltage_v=None,
        battery_percent=None,
        drive_type="UNKNOWN",
        controller_mapping=_controller_mapping_snapshot({}),
        machine_coordinate=_machine_coordinate_snapshot({}),
        motion_parameters=_motion_parameter_source_snapshot({}),
        motion=_motion_snapshot((0.0, 0.0, 0.0), False),
        wheels=(),
        nodes=(),
        autonomy=_autonomy_snapshot(None),
        competition_state=None,
        warnings=("robot controller is not configured",),
    )


def _backend_kind(controller: Any) -> BackendKind:
    if getattr(controller, "fake_device", None) is not None:
        return BackendKind.FAKE_ESP32
    if bool(getattr(controller.args, "simulate", False)):
        return BackendKind.LEGACY_SIMULATION
    return BackendKind.REAL_SERIAL


def _connection_state(controller: Any, backend: BackendKind) -> ConnectionState:
    phase = str(getattr(controller, "reconnect_phase", ""))
    if phase == "blocked":
        return ConnectionState.BLOCKED
    if phase in {"waiting", "hello_pending", "config_pending"}:
        return ConnectionState.RECONNECTING
    if backend == BackendKind.LEGACY_SIMULATION and getattr(controller, "sim", None) is not None:
        return ConnectionState.ONLINE
    serial = getattr(controller, "serial", None)
    if serial is not None and not bool(getattr(serial, "closed", False)):
        return ConnectionState.ONLINE
    return ConnectionState.OFFLINE


def _current_node_report(
    controller: Any,
    requirements: tuple[NodeRequirement, ...],
    identity: Mapping[str, Any] | None,
    online: bool,
) -> NodeInventoryReport | None:
    if not requirements:
        if identity is None or not online:
            return None
        node_id = identity.get("node_id")
        role = identity.get("role")
        if not isinstance(node_id, str) or not node_id.strip() or not isinstance(role, str) or not role.strip():
            return None
        node_id = node_id.strip()
        role = role.strip()
        requirement = NodeRequirement(node_id, role, True)
        port = str(getattr(getattr(controller, "serial", None), "port", "unknown"))
        return evaluate_node_inventory((requirement,), (SerialProbe(port=port, identity=dict(identity)),))
    probes: tuple[SerialProbe, ...] = ()
    if identity is not None and online:
        port = str(getattr(getattr(controller, "serial", None), "port", "unknown"))
        probes = (SerialProbe(port=port, identity=dict(identity)),)
    return evaluate_node_inventory(requirements, probes)


def _node_snapshots(report: NodeInventoryReport | None) -> tuple[NodeSnapshot, ...]:
    if report is None:
        return ()
    by_id: dict[str, list[SerialProbe]] = {}
    for probe in report.probes:
        identity = probe.identity or {}
        node_id = identity.get("node_id")
        if isinstance(node_id, str) and node_id:
            by_id.setdefault(node_id, []).append(probe)

    snapshots: list[NodeSnapshot] = []
    expected_ids = {item.node_id for item in report.requirements}
    for requirement in report.requirements:
        matches = by_id.get(requirement.node_id, [])
        roles = {str((probe.identity or {}).get("role", "")) for probe in matches}
        if len(matches) > 1:
            state = NodeDisplayState.DUPLICATE
        elif matches and roles != {requirement.role}:
            state = NodeDisplayState.WRONG_ROLE
        elif matches:
            state = NodeDisplayState.PRESENT
        elif requirement.required:
            state = NodeDisplayState.MISSING
        else:
            state = NodeDisplayState.OPTIONAL_MISSING
        snapshots.append(
            NodeSnapshot(
                requirement.node_id,
                requirement.role,
                requirement.required,
                state,
                tuple(sorted(probe.port for probe in matches)),
            )
        )
    for node_id, matches in sorted(by_id.items()):
        if node_id in expected_ids:
            continue
        role = str((matches[0].identity or {}).get("role", "unknown"))
        snapshots.append(
            NodeSnapshot(
                node_id,
                role,
                False,
                NodeDisplayState.UNEXPECTED,
                tuple(sorted(probe.port for probe in matches)),
            )
        )
    return tuple(snapshots)


def _motion_snapshot(values: Any, accepted: bool) -> MotionVectorSnapshot:
    try:
        vx, vy, omega = (float(item) for item in values)
    except (OverflowError, TypeError, ValueError):
        vx, vy, omega = 0.0, 0.0, 0.0
    if not all(isfinite(value) for value in (vx, vy, omega)):
        vx, vy, omega = 0.0, 0.0, 0.0
    magnitude = hypot(vx, vy)
    heading = degrees(atan2(vy, vx)) if magnitude > 1e-9 else None
    direction = "CCW" if omega > 1e-9 else "CW" if omega < -1e-9 else "STOP"
    return MotionVectorSnapshot(vx, vy, omega, magnitude, heading, direction, accepted)


def _controller_mapping_snapshot(mapping: Any) -> ControllerInputMappingSnapshot:
    values = mapping if isinstance(mapping, Mapping) else {}
    return ControllerInputMappingSnapshot(
        axis_vx=_optional_int(values.get("axis_vx")),
        axis_vy=_optional_int(values.get("axis_vy")),
        axis_omega=_optional_int(values.get("axis_omega")),
        invert_vx=values.get("invert_vx") if isinstance(values.get("invert_vx"), bool) else None,
        invert_vy=values.get("invert_vy") if isinstance(values.get("invert_vy"), bool) else None,
        invert_omega=values.get("invert_omega") if isinstance(values.get("invert_omega"), bool) else None,
        deadzone=_optional_float(values.get("deadzone")),
        linear_scale=_optional_float(values.get("linear_scale")),
        angular_scale=_optional_float(values.get("angular_scale")),
        logical_front=(
            str(values.get("logical_front", "FRONT")).strip().upper()
            if values.get("logical_front", "FRONT") is not None
            else None
        ),
    )


def _machine_coordinate_snapshot(config: Any) -> MachineCoordinateSnapshot:
    values = config if isinstance(config, Mapping) else {}
    motion = values.get("motion") if isinstance(values.get("motion"), Mapping) else {}
    pivot = motion.get("pivot_direction_inverted")
    return MachineCoordinateSnapshot(
        x_positive="FORWARD",
        y_positive="LEFT",
        omega_positive="CCW",
        max_linear_speed_mps=_optional_float(motion.get("max_linear_speed_mps")),
        max_angular_speed_radps=_optional_float(motion.get("max_angular_speed_radps")),
        pivot_direction_inverted=pivot if isinstance(pivot, bool) else None,
    )


def _motion_parameter_source_snapshot(config: Any) -> MotionParameterSourceSnapshot:
    values = config if isinstance(config, Mapping) else {}
    motion = values.get("motion") if isinstance(values.get("motion"), Mapping) else {}
    return MotionParameterSourceSnapshot(
        open_loop_max_pwm=_optional_float(motion.get("open_loop_max_pwm")),
        pivot_max_pwm=_optional_float(motion.get("pivot_max_pwm")),
    )


def _wheel_snapshots(
    config: Mapping[str, Any],
    telemetry: Mapping[str, Any],
    command: Mapping[str, Any] | None,
) -> tuple[WheelSnapshot, ...]:
    motors = config.get("motors") if isinstance(config.get("motors"), list) else []
    servos = config.get("servos") if isinstance(config.get("servos"), list) else []
    encoder = _numeric_list(telemetry.get("encoder_count"), integer=True)
    rpm = _numeric_list(telemetry.get("wheel_rpm"))
    pwm = _numeric_list(telemetry.get("motor_pwm"))
    observed_steer = _numeric_list(telemetry.get("servo_deg"))
    command_target = _numeric_list(command.get("drive_target") if command else None)
    commanded_steer = _numeric_list(command.get("steer_deg") if command else None)
    control = str(command.get("control")) if command and command.get("control") in {"pwm", "rpm"} else None
    count = max(len(motors), len(servos), 4 if any((encoder, rpm, pwm, observed_steer, command_target, commanded_steer)) else 0)
    wheels: list[WheelSnapshot] = []
    for index in range(count):
        motor = motors[index] if index < len(motors) and isinstance(motors[index], dict) else {}
        servo = servos[index] if index < len(servos) and isinstance(servos[index], dict) else {}
        target = _at(command_target, index)
        wheels.append(
            WheelSnapshot(
                logical_index=index,
                name=str(motor.get("name") or servo.get("name") or f"W{index}"),
                configured=bool(motor or servo),
                motor_inverted=bool(motor.get("inverted")) if "inverted" in motor else None,
                servo_inverted=bool(servo.get("direction_inverted")) if "direction_inverted" in servo else None,
                servo_channel=_optional_int(servo.get("channel")),
                servo_center_us=_optional_int(servo.get("center_us")),
                servo_min_us=_optional_int(servo.get("min_us")),
                servo_max_us=_optional_int(servo.get("max_us")),
                servo_trim_deg=_optional_float(servo.get("trim_deg")),
                servo_min_angle_deg=_optional_float(servo.get("min_angle_deg")),
                servo_max_angle_deg=_optional_float(servo.get("max_angle_deg")),
                servo_calibrated=bool(servo.get("calibrated")) if "calibrated" in servo else None,
                command_control=control,
                command_target=target,
                command_direction=_direction(target),
                commanded_steering_deg=_at(commanded_steer, index),
                observed_rpm=_at(rpm, index),
                observed_pwm=_at(pwm, index),
                observed_steering_deg=_at(observed_steer, index),
                encoder_count=_int_at(encoder, index),
                fault=None,
            )
        )
    return tuple(wheels)


def _autonomy_snapshot(machine: AutonomyStateMachine | None) -> AutonomySnapshot:
    if machine is None:
        return AutonomySnapshot(
            configured=False,
            state=None,
            mission_id=None,
            step_index=None,
            step_count=None,
            current_step=None,
            next_step=None,
            attempt=None,
            max_retries=None,
            retry_delay_ms=None,
            retry_deadline_ms=None,
            failure_action=None,
            fallback_id=None,
            configured_fallback_id=None,
            reason=None,
            skipped_steps=(),
            recent_events=(),
        )
    step = machine.current_step
    next_index = machine.step_index + 1
    next_step = machine.plan.steps[next_index] if 0 <= next_index < len(machine.plan.steps) else None
    return AutonomySnapshot(
        configured=True,
        state=machine.state.value,
        mission_id=machine.plan.mission_id,
        step_index=machine.step_index if step is not None else None,
        step_count=len(machine.plan.steps),
        current_step=step.step_id if step else None,
        next_step=next_step.step_id if next_step else None,
        attempt=machine.attempt or None,
        max_retries=step.max_retries if step else None,
        retry_delay_ms=step.retry_delay_ms if step else None,
        retry_deadline_ms=machine.retry_deadline_ms,
        failure_action=step.on_failure.value if step else None,
        fallback_id=machine.active_fallback_id,
        configured_fallback_id=step.fallback_id if step else None,
        reason=machine.stop_reason,
        skipped_steps=tuple(machine.skipped_steps),
        recent_events=tuple(
            AutonomyEventSnapshot(
                timestamp_ms=event.timestamp_ms,
                state=event.state.value,
                event=event.event,
                step_id=event.step_id,
                attempt=event.attempt,
                reason=event.reason,
            )
            for event in machine.events[-20:]
        ),
    )


def _fault_snapshot(controller: Any, safety_fault: str | None, fault_flags: int | None) -> FaultSnapshot | None:
    event = getattr(controller, "last_fault_event", None)
    if isinstance(event, dict) and safety_fault is not None:
        timestamp = event.get("timestamp_ms")
        return FaultSnapshot(
            DisplaySeverity.ERROR,
            str(event.get("source") or "ESP32"),
            str(event["node_id"]) if event.get("node_id") else None,
            str(event.get("reason") or safety_fault),
            int(timestamp) if isinstance(timestamp, int) and not isinstance(timestamp, bool) else None,
            _optional_int(event.get("fault_flags")),
            f"{controller.safety.state.value}/DISARMED",
        )
    if safety_fault is None:
        return None
    identity = controller.node_identity if isinstance(controller.node_identity, dict) else {}
    return FaultSnapshot(
        DisplaySeverity.ERROR,
        "PC_SAFETY",
        str(identity["node_id"]) if identity.get("node_id") else None,
        safety_fault,
        None,
        fault_flags,
        f"{controller.safety.state.value}/DISARMED",
    )


def _diagnostic_events(
    controller: Any,
    fault_flags: int | None,
    report: NodeInventoryReport | None,
) -> tuple[DiagnosticEventSnapshot, ...]:
    """Preserve active Safety, ESP32, transport, and inventory semantics.

    Timestamps are supplied only when the originating component retained one.
    A history consumer may record the snapshot time as ``FIRST_OBSERVED`` but
    must not present that fallback as the exact event time.
    """

    events: list[DiagnosticEventSnapshot] = []
    safety = controller.safety
    safety_response = f"{safety.state.value}/{'ARMED' if safety.armed else 'DISARMED'}"
    safety_fault = safety.fault
    if safety_fault:
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.ERROR,
                "PC_SAFETY",
                None,
                str(safety_fault),
                None,
                None,
                safety_response,
            )
        )

    structured = getattr(controller, "last_fault_event", None)
    if isinstance(structured, dict):
        timestamp = structured.get("timestamp_ms")
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.ERROR,
                str(structured.get("source") or "ESP32"),
                str(structured["node_id"]) if structured.get("node_id") else None,
                str(structured.get("reason") or "ESP32 fault"),
                int(timestamp) if isinstance(timestamp, int) and not isinstance(timestamp, bool) else None,
                _optional_int(structured.get("fault_flags")),
                safety_response,
            )
        )

    identity = controller.node_identity if isinstance(controller.node_identity, dict) else {}
    node_id = str(identity["node_id"]) if identity.get("node_id") else None
    if fault_flags not in (None, 0):
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.ERROR,
                "ESP32_TELEMETRY",
                node_id,
                f"fault_flags={fault_flags}",
                None,
                fault_flags,
                safety_response,
            )
        )
    if safety.warning:
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.WARNING,
                "PC_SAFETY",
                None,
                "communication timeout warning",
                None,
                None,
                "WARNING_ONLY",
            )
        )
    if safety.stopped_by_timeout:
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.WARNING,
                "PC_SAFETY",
                None,
                "drive stopped by communication timeout",
                None,
                None,
                "STOP_OUTPUT",
            )
        )
    reconnect_error = getattr(controller, "reconnect_last_error", None)
    if reconnect_error:
        events.append(
            DiagnosticEventSnapshot(
                DisplaySeverity.WARNING,
                "PC_TRANSPORT",
                node_id,
                str(reconnect_error),
                None,
                None,
                safety_response,
            )
        )
    if report is not None:
        for issue in report.issues:
            severity = DisplaySeverity.ERROR if issue.severity == "error" else DisplaySeverity.WARNING
            events.append(
                DiagnosticEventSnapshot(
                    severity,
                    "NODE_INVENTORY",
                    None,
                    issue.message,
                    None,
                    None,
                    "READINESS_BLOCKED" if severity == DisplaySeverity.ERROR else "NONE",
                )
            )
    return tuple(events)


def _warnings(controller: Any, report: NodeInventoryReport | None, fault_flags: int | None) -> tuple[str, ...]:
    warnings: list[str] = []
    safety = controller.safety
    if safety.warning:
        warnings.append("communication timeout warning")
    if safety.stopped_by_timeout:
        warnings.append("drive stopped by communication timeout")
    reconnect_error = getattr(controller, "reconnect_last_error", None)
    if reconnect_error:
        warnings.append(str(reconnect_error))
    if fault_flags not in (None, 0):
        warnings.append(f"ESP32 fault_flags={fault_flags}")
    if report is not None:
        warnings.extend(issue.message for issue in report.issues)
    return tuple(dict.fromkeys(warnings))


def _drive_type(config: Mapping[str, Any]) -> str:
    motion = config.get("motion") if isinstance(config.get("motion"), dict) else {}
    explicit = motion.get("drive_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().upper()
    motors = config.get("motors") if isinstance(config.get("motors"), list) else []
    servos = config.get("servos") if isinstance(config.get("servos"), list) else []
    if len(motors) == 4 and len(servos) == 4:
        return "4WIS"
    return "UNKNOWN"


def _controller_name(controller: Any) -> str | None:
    source = getattr(controller, "controller", None)
    joystick = getattr(source, "joystick", None)
    if joystick is None:
        return None
    name = getattr(joystick, "get_name", None)
    return str(name()) if callable(name) else None


def _age(now_ms: int, timestamp_ms: int) -> int | None:
    if timestamp_ms <= 0:
        return None
    return max(0, int(now_ms) - int(timestamp_ms))


def _first_optional_float(values: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(values.get(key))
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = float(value)
    except OverflowError:
        return None
    return parsed if isfinite(parsed) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _numeric_list(value: Any, *, integer: bool = False) -> tuple[float | int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    parsed: list[float | int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return ()
        try:
            finite = isfinite(float(item))
        except OverflowError:
            return ()
        if not finite:
            return ()
        parsed.append(int(item) if integer else float(item))
    return tuple(parsed)


def _at(values: tuple[float | int, ...], index: int) -> float | None:
    return float(values[index]) if index < len(values) else None


def _int_at(values: tuple[float | int, ...], index: int) -> int | None:
    return int(values[index]) if index < len(values) else None


def _direction(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value > 1e-9:
        return "FORWARD"
    if value < -1e-9:
        return "REVERSE"
    return "STOP"


def _require_robot_id(robot_id: RobotId) -> None:
    if not isinstance(robot_id, RobotId):
        raise ValueError("robot_id must be RobotId.R1 or RobotId.R2")
