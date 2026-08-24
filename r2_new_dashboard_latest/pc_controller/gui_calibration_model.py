"""Read-only Calibration foundation derived from shared GUI snapshots.

The model deliberately exposes no edit, save, apply, ARM, DEBUG, or transport
method.  It audits the controller-loaded servo configuration and keeps current,
pending, saved, validation, revert, and apply concepts distinct until a
Safety-governed controller-level Calibration API exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .gui_model import FaultSnapshot, RobotDashboardSnapshot


@dataclass(frozen=True)
class ServoCalibrationSnapshot:
    logical_index: int
    logical_name: str
    channel: int | None
    current_center_us: int | None
    min_us: int | None
    max_us: int | None
    min_angle_deg: float | None
    max_angle_deg: float | None
    current_trim_deg: float | None
    direction_inverted: bool | None
    current_command_angle_deg: float | None
    observed_angle_deg: float | None
    calibrated: bool | None
    pending_center_us: int | None
    pending_trim_deg: float | None
    saved_center_us: int | None
    saved_trim_deg: float | None
    validation: str
    revert_state: str
    apply_state: str


@dataclass(frozen=True)
class CalibrationDiagnosticSnapshot:
    robot_id: str
    timestamp_ms: int
    configured: bool
    connection: str
    safety_state: str
    ready: bool
    armed: bool
    fault: str | None
    fault_event: FaultSnapshot | None
    warnings: tuple[str, ...]
    workflow_state: str
    controller_api_state: str
    output_state: str
    servos: tuple[ServoCalibrationSnapshot, ...]


def build_calibration_diagnostic_snapshot(
    robot: RobotDashboardSnapshot,
) -> CalibrationDiagnosticSnapshot:
    """Map one robot snapshot without creating pending edits or hardware output."""
    robot_id = _enum_value(robot.robot_id)
    connection = _enum_value(robot.connection)
    if not robot.configured:
        return CalibrationDiagnosticSnapshot(
            robot_id=robot_id,
            timestamp_ms=robot.timestamp_ms,
            configured=False,
            connection=connection,
            safety_state=robot.safety_state,
            ready=False,
            armed=False,
            fault=robot.fault,
            fault_event=robot.fault_event,
            warnings=robot.warnings,
            workflow_state="UNBOUND",
            controller_api_state="UNAVAILABLE",
            output_state="BLOCKED",
            servos=(),
        )

    servos = tuple(_servo_snapshot(wheel) for wheel in robot.wheels if wheel.servo_channel is not None)
    return CalibrationDiagnosticSnapshot(
        robot_id=robot_id,
        timestamp_ms=robot.timestamp_ms,
        configured=True,
        connection=connection,
        safety_state=robot.safety_state,
        ready=robot.ready,
        armed=robot.armed,
        fault=robot.fault,
        fault_event=robot.fault_event,
        warnings=robot.warnings,
        workflow_state="READ_ONLY_AUDIT" if servos else "NOT_CONFIGURED",
        controller_api_state="REQUIRES_SAFETY_GOVERNED_CALIBRATION_API",
        output_state="BLOCKED_NO_CONTROLLER_API",
        servos=servos,
    )


def _servo_snapshot(wheel) -> ServoCalibrationSnapshot:
    validation = _validate_config_values(
        wheel.servo_center_us,
        wheel.servo_min_us,
        wheel.servo_max_us,
        wheel.servo_trim_deg,
        wheel.servo_min_angle_deg,
        wheel.servo_max_angle_deg,
    )
    return ServoCalibrationSnapshot(
        logical_index=wheel.logical_index,
        logical_name=wheel.name,
        channel=wheel.servo_channel,
        current_center_us=wheel.servo_center_us,
        min_us=wheel.servo_min_us,
        max_us=wheel.servo_max_us,
        min_angle_deg=wheel.servo_min_angle_deg,
        max_angle_deg=wheel.servo_max_angle_deg,
        current_trim_deg=wheel.servo_trim_deg,
        direction_inverted=wheel.servo_inverted,
        current_command_angle_deg=wheel.commanded_steering_deg,
        observed_angle_deg=wheel.observed_steering_deg,
        calibrated=wheel.servo_calibrated,
        # There is intentionally no GUI edit session in this milestone.
        pending_center_us=None,
        pending_trim_deg=None,
        # ControllerApp loaded these values from its configured JSON source.
        # They are displayed separately from pending state, but this is not a
        # live disk reread or proof of ESP32/physical calibration.
        saved_center_us=wheel.servo_center_us,
        saved_trim_deg=wheel.servo_trim_deg,
        validation=validation,
        revert_state="NO_PENDING_CHANGE",
        apply_state="BLOCKED_NO_CONTROLLER_API",
    )


def _validate_config_values(
    center_us: int | None,
    min_us: int | None,
    max_us: int | None,
    trim_deg: float | None,
    min_angle_deg: float | None,
    max_angle_deg: float | None,
) -> str:
    values = (center_us, min_us, max_us, trim_deg, min_angle_deg, max_angle_deg)
    if any(value is None for value in values):
        return "CONFIG_INCOMPLETE"
    assert center_us is not None and min_us is not None and max_us is not None
    assert trim_deg is not None and min_angle_deg is not None and max_angle_deg is not None
    if not all(isfinite(float(value)) for value in values):
        return "CONFIG_INVALID"
    if not min_us < center_us < max_us:
        return "CONFIG_INVALID"
    if min_angle_deg >= 0.0 or max_angle_deg <= 0.0:
        return "CONFIG_INVALID"
    return "CONFIG_ONLY_VALID"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
