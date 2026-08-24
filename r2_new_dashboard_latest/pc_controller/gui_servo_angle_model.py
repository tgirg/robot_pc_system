"""Local-only Servo Angle calibration drafts derived from GUI snapshots.

The authoritative current representation pairs safe pulse endpoints
(``min_us``/``max_us``) with allowed logical angle endpoints
(``min_angle_deg``/``max_angle_deg``).  Drafts stay in process memory and this
module intentionally has no ControllerApp, Serial, config-file, or output API.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .gui_calibration_model import CalibrationDiagnosticSnapshot, ServoCalibrationSnapshot


@dataclass(frozen=True)
class ServoAngleRowSnapshot:
    robot_id: str
    logical_index: int
    logical_name: str
    channel: int | None
    current_center_us: int | None
    current_trim_deg: float | None
    direction_inverted: bool | None
    calibrated: bool | None
    current_command_angle_deg: float | None
    observed_angle_deg: float | None
    current_min_us: int | None
    current_max_us: int | None
    current_min_angle_deg: float | None
    current_max_angle_deg: float | None
    pending_min_us: int | None
    pending_max_us: int | None
    pending_min_angle_deg: float | None
    pending_max_angle_deg: float | None
    pending_min_us_text: str | None
    pending_max_us_text: str | None
    pending_min_angle_deg_text: str | None
    pending_max_angle_deg_text: str | None
    saved_min_us: int | None
    saved_max_us: int | None
    saved_min_angle_deg: float | None
    saved_max_angle_deg: float | None
    validation: str
    revert_state: str
    apply_state: str
    save_state: str
    hardware_validation_state: str

    @property
    def has_pending(self) -> bool:
        return any(
            value is not None
            for value in (
                self.pending_min_us_text,
                self.pending_max_us_text,
                self.pending_min_angle_deg_text,
                self.pending_max_angle_deg_text,
            )
        )


@dataclass(frozen=True)
class ServoAngleAdjustmentSnapshot:
    robot_id: str
    configured: bool
    workflow_state: str
    controller_api_state: str
    output_state: str
    pending_count: int
    rows: tuple[ServoAngleRowSnapshot, ...]


@dataclass(frozen=True)
class _PendingDraft:
    min_us_text: str
    max_us_text: str
    min_angle_deg_text: str
    max_angle_deg_text: str
    base_saved_min_us: int | None
    base_saved_max_us: int | None
    base_saved_min_angle_deg: float | None
    base_saved_max_angle_deg: float | None
    base_center_us: int | None
    base_trim_deg: float | None
    base_direction_inverted: bool | None


class ServoAngleDraftStore:
    """Keep per-robot/per-servo angle endpoint drafts in memory only."""

    def __init__(self) -> None:
        self._drafts: dict[tuple[str, int], _PendingDraft] = {}

    def stage(
        self,
        diagnostic: CalibrationDiagnosticSnapshot,
        logical_index: int,
        *,
        min_us_text: str,
        max_us_text: str,
        min_angle_deg_text: str,
        max_angle_deg_text: str,
    ) -> ServoAngleAdjustmentSnapshot:
        servo = _find_servo(diagnostic, logical_index)
        values = tuple(
            str(value).strip()
            for value in (min_us_text, max_us_text, min_angle_deg_text, max_angle_deg_text)
        )
        validation, parsed = _validate_pending(servo, *values)
        min_us, max_us, min_angle_deg, max_angle_deg = parsed
        key = (diagnostic.robot_id, logical_index)
        if validation == "PENDING_VALID_LOCAL_ONLY" and (
            min_us,
            max_us,
            min_angle_deg,
            max_angle_deg,
        ) == (
            servo.min_us,
            servo.max_us,
            servo.min_angle_deg,
            servo.max_angle_deg,
        ):
            self._drafts.pop(key, None)
        else:
            self._drafts[key] = _PendingDraft(
                min_us_text=values[0],
                max_us_text=values[1],
                min_angle_deg_text=values[2],
                max_angle_deg_text=values[3],
                base_saved_min_us=servo.min_us,
                base_saved_max_us=servo.max_us,
                base_saved_min_angle_deg=servo.min_angle_deg,
                base_saved_max_angle_deg=servo.max_angle_deg,
                base_center_us=servo.current_center_us,
                base_trim_deg=servo.current_trim_deg,
                base_direction_inverted=servo.direction_inverted,
            )
        return self.build(diagnostic)

    def revert(self, robot_id: str, logical_index: int) -> bool:
        """Discard one local draft without changing config or hardware."""
        return self._drafts.pop((str(robot_id), int(logical_index)), None) is not None

    def build(self, diagnostic: CalibrationDiagnosticSnapshot) -> ServoAngleAdjustmentSnapshot:
        rows = tuple(self._row(diagnostic.robot_id, servo) for servo in diagnostic.servos)
        pending_rows = tuple(row for row in rows if row.has_pending)
        if not diagnostic.configured:
            workflow_state = diagnostic.workflow_state
        elif any(row.validation != "PENDING_VALID_LOCAL_ONLY" for row in pending_rows):
            workflow_state = "LOCAL_DRAFT_INVALID"
        elif pending_rows:
            workflow_state = "LOCAL_DRAFT_READY"
        else:
            workflow_state = "READ_ONLY_AUDIT" if rows else "NOT_CONFIGURED"
        return ServoAngleAdjustmentSnapshot(
            robot_id=diagnostic.robot_id,
            configured=diagnostic.configured,
            workflow_state=workflow_state,
            controller_api_state=diagnostic.controller_api_state,
            output_state=diagnostic.output_state,
            pending_count=len(pending_rows),
            rows=rows,
        )

    def _row(self, robot_id: str, servo: ServoCalibrationSnapshot) -> ServoAngleRowSnapshot:
        draft = self._drafts.get((robot_id, servo.logical_index))
        pending_values: tuple[int | float | None, ...] = (None, None, None, None)
        pending_text: tuple[str | None, ...] = (None, None, None, None)
        validation = servo.validation
        revert_state = "NO_PENDING_CHANGE"
        if draft is not None:
            pending_text = (
                draft.min_us_text,
                draft.max_us_text,
                draft.min_angle_deg_text,
                draft.max_angle_deg_text,
            )
            if _base_changed(draft, servo):
                validation = "STALE_BASE_CONFIG"
            else:
                validation, pending_values = _validate_pending(servo, *pending_text)
            revert_state = "AVAILABLE_LOCAL_ONLY"
        return ServoAngleRowSnapshot(
            robot_id=robot_id,
            logical_index=servo.logical_index,
            logical_name=servo.logical_name,
            channel=servo.channel,
            current_center_us=servo.current_center_us,
            current_trim_deg=servo.current_trim_deg,
            direction_inverted=servo.direction_inverted,
            calibrated=servo.calibrated,
            current_command_angle_deg=servo.current_command_angle_deg,
            observed_angle_deg=servo.observed_angle_deg,
            current_min_us=servo.min_us,
            current_max_us=servo.max_us,
            current_min_angle_deg=servo.min_angle_deg,
            current_max_angle_deg=servo.max_angle_deg,
            pending_min_us=_as_int(pending_values[0]),
            pending_max_us=_as_int(pending_values[1]),
            pending_min_angle_deg=_as_float(pending_values[2]),
            pending_max_angle_deg=_as_float(pending_values[3]),
            pending_min_us_text=pending_text[0],
            pending_max_us_text=pending_text[1],
            pending_min_angle_deg_text=pending_text[2],
            pending_max_angle_deg_text=pending_text[3],
            saved_min_us=servo.min_us,
            saved_max_us=servo.max_us,
            saved_min_angle_deg=servo.min_angle_deg,
            saved_max_angle_deg=servo.max_angle_deg,
            validation=validation,
            revert_state=revert_state,
            apply_state="BLOCKED_NO_CONTROLLER_API",
            save_state="BLOCKED_NO_CONTROLLER_API",
            hardware_validation_state="REQUIRED_BEFORE_APPLY",
        )


def _find_servo(
    diagnostic: CalibrationDiagnosticSnapshot,
    logical_index: int,
) -> ServoCalibrationSnapshot:
    if not diagnostic.configured:
        raise ValueError("cannot create Servo Angle draft for an unbound robot")
    for servo in diagnostic.servos:
        if servo.logical_index == logical_index:
            return servo
    raise ValueError(f"servo logical index {logical_index} is not configured")


def _base_changed(draft: _PendingDraft, servo: ServoCalibrationSnapshot) -> bool:
    return (
        draft.base_saved_min_us != servo.min_us
        or draft.base_saved_max_us != servo.max_us
        or draft.base_saved_min_angle_deg != servo.min_angle_deg
        or draft.base_saved_max_angle_deg != servo.max_angle_deg
        or draft.base_center_us != servo.current_center_us
        or draft.base_trim_deg != servo.current_trim_deg
        or draft.base_direction_inverted != servo.direction_inverted
    )


def _validate_pending(
    servo: ServoCalibrationSnapshot,
    min_us_text: str,
    max_us_text: str,
    min_angle_deg_text: str,
    max_angle_deg_text: str,
) -> tuple[str, tuple[int | float | None, ...]]:
    try:
        min_us = int(min_us_text)
        max_us = int(max_us_text)
        min_angle_deg = float(min_angle_deg_text)
        max_angle_deg = float(max_angle_deg_text)
    except (TypeError, ValueError):
        return "PENDING_INVALID_FORMAT", (None, None, None, None)
    parsed: tuple[int | float | None, ...] = (min_us, max_us, min_angle_deg, max_angle_deg)
    if not isfinite(min_angle_deg) or not isfinite(max_angle_deg):
        return "PENDING_INVALID_FORMAT", parsed
    if servo.validation != "CONFIG_ONLY_VALID" or servo.current_center_us is None:
        return "PENDING_BLOCKED_BASE_CONFIG_INVALID", parsed
    if not min_us < servo.current_center_us < max_us:
        return "PENDING_INVALID_PULSE_RANGE", parsed
    if min_angle_deg >= 0.0 or max_angle_deg <= 0.0:
        return "PENDING_INVALID_ANGLE_RANGE", parsed
    return "PENDING_VALID_LOCAL_ONLY", parsed


def _as_int(value: int | float | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_float(value: int | float | None) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
