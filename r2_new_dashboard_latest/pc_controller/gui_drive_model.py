"""Read-only Drive Diagnostic view state derived from the shared GUI snapshot.

This module deliberately accepts only ``RobotDashboardSnapshot`` values.  It
does not own a transport and exposes no ARM, drive, calibration, or fault
injection API.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gui_model import FaultSnapshot, MotionVectorSnapshot, RobotDashboardSnapshot


@dataclass(frozen=True)
class DriveWheelDiagnostic:
    logical_index: int
    name: str
    status: str
    command_control: str | None
    command_target: float | None
    command_direction: str
    observed_rpm: float | None
    observed_pwm: float | None
    commanded_steering_deg: float | None
    observed_steering_deg: float | None
    motor_inverted: bool | None
    servo_inverted: bool | None
    node_link: str
    fault: str | None


@dataclass(frozen=True)
class DriveDiagnosticSnapshot:
    robot_id: str
    timestamp_ms: int
    configured: bool
    connection: str
    safety_state: str
    ready: bool
    safe: bool
    armed: bool
    drive_type: str
    steering_available: bool
    drive_node_state: str
    drive_node_summary: str
    motion: MotionVectorSnapshot
    wheels: tuple[DriveWheelDiagnostic, ...]
    fault: str | None
    fault_event: FaultSnapshot | None
    warnings: tuple[str, ...]


def build_drive_diagnostic_snapshot(robot: RobotDashboardSnapshot) -> DriveDiagnosticSnapshot:
    """Build renderer-ready drive diagnostics without accessing a controller."""

    robot_id = _enum_value(robot.robot_id)
    connection = _enum_value(robot.connection)
    drive_type = str(robot.drive_type or "UNKNOWN").upper()
    steering_available = drive_type == "4WIS"
    drive_node_state, drive_node_summary = _drive_node_status(robot)
    node_link = f"{connection}/{drive_node_state}"

    wheels = tuple(
        DriveWheelDiagnostic(
            logical_index=wheel.logical_index,
            name=wheel.name,
            status=_wheel_status(robot, wheel, connection, drive_node_state),
            command_control=wheel.command_control,
            command_target=wheel.command_target,
            command_direction=wheel.command_direction,
            observed_rpm=wheel.observed_rpm,
            observed_pwm=wheel.observed_pwm,
            commanded_steering_deg=wheel.commanded_steering_deg if steering_available else None,
            observed_steering_deg=wheel.observed_steering_deg if steering_available else None,
            motor_inverted=wheel.motor_inverted,
            servo_inverted=wheel.servo_inverted if steering_available else None,
            node_link=node_link,
            fault=wheel.fault,
        )
        for wheel in robot.wheels
    )

    return DriveDiagnosticSnapshot(
        robot_id=robot_id,
        timestamp_ms=robot.timestamp_ms,
        configured=robot.configured,
        connection=connection,
        safety_state=robot.safety_state,
        ready=robot.ready,
        safe=robot.safe,
        armed=robot.armed,
        drive_type=drive_type,
        steering_available=steering_available,
        drive_node_state=drive_node_state,
        drive_node_summary=drive_node_summary,
        motion=robot.motion,
        wheels=wheels,
        fault=robot.fault,
        fault_event=robot.fault_event,
        warnings=robot.warnings,
    )


def _drive_node_status(robot: RobotDashboardSnapshot) -> tuple[str, str]:
    if not robot.configured:
        return "UNBOUND", "No controller is bound to this robot"

    nodes = tuple(node for node in robot.nodes if str(node.role).lower() == "drive")
    if not nodes:
        return "UNKNOWN", "No drive-role node is present in the shared snapshot"

    states = tuple(_enum_value(node.state) for node in nodes)
    priority = (
        "DUPLICATE",
        "WRONG_ROLE",
        "MISSING",
        "OPTIONAL_MISSING",
        "UNEXPECTED",
        "PRESENT",
    )
    aggregate = next((state for state in priority if state in states), "UNKNOWN")
    summary = ", ".join(f"{node.node_id}={_enum_value(node.state)}" for node in nodes)
    return aggregate, summary


def _wheel_status(robot, wheel, connection: str, drive_node_state: str) -> str:
    if not robot.configured:
        return "UNBOUND"
    if wheel.fault:
        return "FAULT"
    if robot.fault or robot.fault_event is not None:
        return "SAFETY_FAULT"
    if not wheel.configured:
        return "UNCONFIGURED"
    if connection != "ONLINE":
        return connection
    if drive_node_state != "PRESENT":
        return f"NODE_{drive_node_state}"
    observed = (
        wheel.observed_rpm,
        wheel.observed_pwm,
        wheel.observed_steering_deg,
        wheel.encoder_count,
    )
    if all(value is None for value in observed):
        return "NO_TELEMETRY"
    return "MONITORING"


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))
