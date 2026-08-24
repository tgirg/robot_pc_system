"""Read-only non-drive Mechanism Diagnostic state.

The current shared GUI snapshot contains authoritative drive state and node
inventory, but it does not yet contain a non-drive mechanism inventory or
mechanism telemetry contract.  This module makes that absence explicit.  A
non-drive node may be shown as unmapped, but it is never promoted to a named
mechanism and no command, limit, or telemetry values are fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gui_model import FaultSnapshot, RobotDashboardSnapshot


_RESERVED_NODE_ROLES = frozenset({"drive", "sensor"})


@dataclass(frozen=True)
class UnmappedMechanismNode:
    """A non-drive node that still lacks an authoritative mechanism mapping."""

    node_id: str
    role: str
    required: bool
    node_state: str
    ports: tuple[str, ...]
    mapping_state: str = "UNMAPPED"
    command: str | None = None
    state: str | None = None
    limit: str | None = None
    telemetry: str | None = None
    fault: str | None = None


@dataclass(frozen=True)
class MechanismDiagnosticSnapshot:
    robot_id: str
    timestamp_ms: int
    configured: bool
    connection: str
    safety_state: str
    ready: bool
    safe: bool
    armed: bool
    inventory_state: str
    inventory_summary: str
    unmapped_nodes: tuple[UnmappedMechanismNode, ...]
    excluded_drive_nodes: int
    excluded_sensor_nodes: int
    fault: str | None
    fault_event: FaultSnapshot | None
    warnings: tuple[str, ...]


def build_mechanism_diagnostic_snapshot(
    robot: RobotDashboardSnapshot,
) -> MechanismDiagnosticSnapshot:
    """Build renderer-ready non-drive diagnostics from one shared snapshot."""

    robot_id = _enum_value(robot.robot_id)
    connection = _enum_value(robot.connection)
    drive_nodes = tuple(node for node in robot.nodes if _role(node.role) == "drive")
    sensor_nodes = tuple(node for node in robot.nodes if _role(node.role) == "sensor")
    candidate_nodes = tuple(
        node for node in robot.nodes if _role(node.role) not in _RESERVED_NODE_ROLES
    )
    unmapped_nodes = tuple(
        UnmappedMechanismNode(
            node_id=node.node_id,
            role=node.role,
            required=node.required,
            node_state=_enum_value(node.state),
            ports=node.ports,
        )
        for node in candidate_nodes
    )

    if not robot.configured:
        inventory_state = "UNBOUND"
        inventory_summary = "No controller is bound to this robot"
    elif unmapped_nodes:
        inventory_state = "NODE_MAPPING_REQUIRED"
        inventory_summary = (
            f"{len(unmapped_nodes)} non-drive node(s) are visible, but no authoritative "
            "mechanism inventory maps them to mechanisms"
        )
    else:
        inventory_state = "NOT_CONFIGURED"
        inventory_summary = (
            "No authoritative non-drive mechanism inventory is present in the shared snapshot; "
            "drive motors and steering servos remain in Drive Diagnostic"
        )

    return MechanismDiagnosticSnapshot(
        robot_id=robot_id,
        timestamp_ms=robot.timestamp_ms,
        configured=robot.configured,
        connection=connection,
        safety_state=robot.safety_state,
        ready=robot.ready,
        safe=robot.safe,
        armed=robot.armed,
        inventory_state=inventory_state,
        inventory_summary=inventory_summary,
        unmapped_nodes=unmapped_nodes,
        excluded_drive_nodes=len(drive_nodes),
        excluded_sensor_nodes=len(sensor_nodes),
        fault=robot.fault,
        fault_event=robot.fault_event,
        warnings=robot.warnings,
    )


def _role(value: object) -> str:
    return str(value).strip().lower()


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
