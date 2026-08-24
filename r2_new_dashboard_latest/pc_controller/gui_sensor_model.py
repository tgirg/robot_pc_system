"""Read-only Sensor Diagnostic state derived from the shared GUI snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from .custom_board_sensor_inventory import R2_SENSOR_CHECK_ORDER
from .gui_model import FaultSnapshot, RobotDashboardSnapshot


@dataclass(frozen=True)
class SensorDiagnosticRow:
    """One sensor check row shown in R2 Sensor Diagnostic."""

    sensor_name: str
    gpio: str
    purpose: str
    connection: str
    current_value: float | str | None
    unit: str | None
    validity: str
    stale: bool | None
    fault: str | None
    last_update_ms: int | None
    note: str | None = None


@dataclass(frozen=True)
class UnmappedSensorNode:
    """A sensor-role node that lacks a per-sensor mapping and telemetry contract."""

    node_id: str
    required: bool
    node_state: str
    ports: tuple[str, ...]
    mapping_state: str = "UNMAPPED"


@dataclass(frozen=True)
class SensorDiagnosticSnapshot:
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
    sensors: tuple[SensorDiagnosticRow, ...]
    unmapped_nodes: tuple[UnmappedSensorNode, ...]
    excluded_drive_nodes: int
    excluded_non_sensor_nodes: int
    shared_telemetry_age_ms: int | None
    fault: str | None
    fault_event: FaultSnapshot | None
    warnings: tuple[str, ...]


def build_sensor_diagnostic_snapshot(
    robot: RobotDashboardSnapshot,
) -> SensorDiagnosticSnapshot:
    """Build renderer-ready sensor boundaries from one immutable robot snapshot."""

    robot_id = _enum_value(robot.robot_id)
    connection = _enum_value(robot.connection)
    drive_nodes = tuple(node for node in robot.nodes if _role(node.role) == "drive")
    sensor_nodes = tuple(node for node in robot.nodes if _role(node.role) == "sensor")
    other_nodes = tuple(
        node for node in robot.nodes if _role(node.role) not in {"drive", "sensor"}
    )
    unmapped_nodes = tuple(
        UnmappedSensorNode(
            node_id=node.node_id,
            required=node.required,
            node_state=_enum_value(node.state),
            ports=node.ports,
        )
        for node in sensor_nodes
    )

    sensors = _build_r2_sensor_rows(robot_id) if robot.configured and robot_id == "R2" else ()

    if not robot.configured:
        inventory_state = "UNBOUND"
        inventory_summary = "No controller is bound to this robot"
    elif unmapped_nodes:
        inventory_state = "NODE_MAPPING_REQUIRED"
        inventory_summary = (
            f"{len(unmapped_nodes)} sensor-role node(s) are visible, but no authoritative "
            "per-sensor inventory or telemetry mapping is present"
        )
    else:
        inventory_state = "DEFINED_PENDING_CHECK" if sensors else "NOT_CONFIGURED"
        inventory_summary = (
            "R2 custom ESP32 sensor connector names/GPIOs are defined; live RAW/connection "
            "values are pending individual serial checks"
            if sensors
            else "No authoritative per-robot sensor inventory is present in the shared snapshot; "
            "wheel encoders remain in Drive Diagnostic"
        )

    return SensorDiagnosticSnapshot(
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
        sensors=sensors,
        unmapped_nodes=unmapped_nodes,
        excluded_drive_nodes=len(drive_nodes),
        excluded_non_sensor_nodes=len(other_nodes),
        shared_telemetry_age_ms=robot.telemetry_age_ms,
        fault=robot.fault,
        fault_event=robot.fault_event,
        warnings=robot.warnings,
    )


def _role(value: object) -> str:
    return str(value).strip().lower()


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _build_r2_sensor_rows(robot_id: str) -> tuple[SensorDiagnosticRow, ...]:
    rows: list[SensorDiagnosticRow] = []
    for sensor in R2_SENSOR_CHECK_ORDER:
        rows.append(
            SensorDiagnosticRow(
                sensor_name=sensor.name,
                gpio=sensor.gpio_label,
                purpose=sensor.purpose,
                connection="未確認",
                current_value=None,
                unit=sensor.unit,
                validity="PENDING_INDIVIDUAL_CHECK",
                stale=None,
                fault=None,
                last_update_ms=None,
                note=sensor.note or f"{robot_id}正式確認リスト",
            )
        )
    return tuple(rows)
