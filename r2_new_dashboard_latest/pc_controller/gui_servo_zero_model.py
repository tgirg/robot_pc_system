"""Local-only Servo Zero draft state derived from Calibration snapshots.

The draft store is deliberately disconnected from ControllerApp, Serial, config
files, and hardware output.  It lets the GUI keep current, pending, and saved
values distinct while the required Safety-governed controller API is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .gui_calibration_model import CalibrationDiagnosticSnapshot, ServoCalibrationSnapshot


@dataclass(frozen=True)
class ServoZeroRowSnapshot:
    robot_id: str
    logical_index: int
    logical_name: str
    channel: int | None
    min_us: int | None
    max_us: int | None
    current_center_us: int | None
    current_trim_deg: float | None
    current_command_angle_deg: float | None
    observed_angle_deg: float | None
    calibrated: bool | None
    pending_center_us: int | None
    pending_trim_deg: float | None
    pending_center_us_text: str | None
    pending_trim_deg_text: str | None
    saved_center_us: int | None
    saved_trim_deg: float | None
    validation: str
    revert_state: str
    apply_state: str
    save_state: str

    @property
    def has_pending(self) -> bool:
        return self.pending_center_us_text is not None or self.pending_trim_deg_text is not None


@dataclass(frozen=True)
class ServoZeroAdjustmentSnapshot:
    robot_id: str
    configured: bool
    workflow_state: str
    controller_api_state: str
    output_state: str
    pending_count: int
    rows: tuple[ServoZeroRowSnapshot, ...]


@dataclass(frozen=True)
class _PendingDraft:
    center_us_text: str
    trim_deg_text: str
    base_saved_center_us: int | None
    base_saved_trim_deg: float | None


class ServoZeroDraftStore:
    """In-memory draft state only; this class has no persistence or output API."""

    def __init__(self) -> None:
        self._drafts: dict[tuple[str, int], _PendingDraft] = {}

    def stage(
        self,
        diagnostic: CalibrationDiagnosticSnapshot,
        logical_index: int,
        *,
        center_us_text: str,
        trim_deg_text: str,
    ) -> ServoZeroAdjustmentSnapshot:
        servo = _find_servo(diagnostic, logical_index)
        center_text = str(center_us_text).strip()
        trim_text = str(trim_deg_text).strip()
        validation, center_us, trim_deg = _validate_pending(servo, center_text, trim_text)
        key = (diagnostic.robot_id, logical_index)
        if (
            validation == "PENDING_VALID_LOCAL_ONLY"
            and center_us == servo.saved_center_us
            and trim_deg == servo.saved_trim_deg
        ):
            self._drafts.pop(key, None)
        else:
            self._drafts[key] = _PendingDraft(
                center_us_text=center_text,
                trim_deg_text=trim_text,
                base_saved_center_us=servo.saved_center_us,
                base_saved_trim_deg=servo.saved_trim_deg,
            )
        return self.build(diagnostic)

    def revert(self, robot_id: str, logical_index: int) -> bool:
        """Discard one local draft without changing config or hardware."""
        return self._drafts.pop((str(robot_id), int(logical_index)), None) is not None

    def build(self, diagnostic: CalibrationDiagnosticSnapshot) -> ServoZeroAdjustmentSnapshot:
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
        return ServoZeroAdjustmentSnapshot(
            robot_id=diagnostic.robot_id,
            configured=diagnostic.configured,
            workflow_state=workflow_state,
            controller_api_state=diagnostic.controller_api_state,
            output_state=diagnostic.output_state,
            pending_count=len(pending_rows),
            rows=rows,
        )

    def _row(self, robot_id: str, servo: ServoCalibrationSnapshot) -> ServoZeroRowSnapshot:
        draft = self._drafts.get((robot_id, servo.logical_index))
        pending_center_us: int | None = None
        pending_trim_deg: float | None = None
        pending_center_text: str | None = None
        pending_trim_text: str | None = None
        validation = servo.validation
        revert_state = "NO_PENDING_CHANGE"
        if draft is not None:
            pending_center_text = draft.center_us_text
            pending_trim_text = draft.trim_deg_text
            if (
                draft.base_saved_center_us != servo.saved_center_us
                or draft.base_saved_trim_deg != servo.saved_trim_deg
            ):
                validation = "STALE_BASE_CONFIG"
            else:
                validation, pending_center_us, pending_trim_deg = _validate_pending(
                    servo,
                    draft.center_us_text,
                    draft.trim_deg_text,
                )
            revert_state = "AVAILABLE_LOCAL_ONLY"
        return ServoZeroRowSnapshot(
            robot_id=robot_id,
            logical_index=servo.logical_index,
            logical_name=servo.logical_name,
            channel=servo.channel,
            min_us=servo.min_us,
            max_us=servo.max_us,
            current_center_us=servo.current_center_us,
            current_trim_deg=servo.current_trim_deg,
            current_command_angle_deg=servo.current_command_angle_deg,
            observed_angle_deg=servo.observed_angle_deg,
            calibrated=servo.calibrated,
            pending_center_us=pending_center_us,
            pending_trim_deg=pending_trim_deg,
            pending_center_us_text=pending_center_text,
            pending_trim_deg_text=pending_trim_text,
            saved_center_us=servo.saved_center_us,
            saved_trim_deg=servo.saved_trim_deg,
            validation=validation,
            revert_state=revert_state,
            apply_state="BLOCKED_NO_CONTROLLER_API",
            save_state="BLOCKED_NO_CONTROLLER_API",
        )


def _find_servo(
    diagnostic: CalibrationDiagnosticSnapshot,
    logical_index: int,
) -> ServoCalibrationSnapshot:
    if not diagnostic.configured:
        raise ValueError("cannot create Servo Zero draft for an unbound robot")
    for servo in diagnostic.servos:
        if servo.logical_index == logical_index:
            return servo
    raise ValueError(f"servo logical index {logical_index} is not configured")


def _validate_pending(
    servo: ServoCalibrationSnapshot,
    center_us_text: str,
    trim_deg_text: str,
) -> tuple[str, int | None, float | None]:
    try:
        center_us = int(center_us_text)
        trim_deg = float(trim_deg_text)
    except (TypeError, ValueError):
        return "PENDING_INVALID_FORMAT", None, None
    if not isfinite(trim_deg):
        return "PENDING_INVALID_FORMAT", None, None
    if servo.validation != "CONFIG_ONLY_VALID" or servo.min_us is None or servo.max_us is None:
        return "PENDING_BLOCKED_BASE_CONFIG_INVALID", center_us, trim_deg
    if not servo.min_us < center_us < servo.max_us:
        return "PENDING_INVALID_CENTER_RANGE", center_us, trim_deg
    return "PENDING_VALID_LOCAL_ONLY", center_us, trim_deg
