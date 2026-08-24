"""Local-only Parameter Editor / Slider foundation.

Only parameters with an authoritative bounded PC runtime clamp are included.
Drafts stay in process memory and this module has no ControllerApp, Serial,
config-file, ARM, DEBUG, or actuator-output API.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .gui_model import RobotDashboardSnapshot


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    group: str
    minimum: float
    maximum: float
    step: float
    unit: str
    source: str


PARAMETER_SPECS = (
    ParameterSpec(
        "controller.deadzone",
        "Controller deadzone",
        "CONTROLLER_INPUT",
        0.0,
        0.95,
        0.01,
        "fraction",
        "controller_mapping.json / correct_controller_axis runtime clamp",
    ),
    ParameterSpec(
        "controller.linear_scale",
        "Linear input scale",
        "CONTROLLER_INPUT",
        0.0,
        1.0,
        0.01,
        "ratio",
        "controller_mapping.json / ControllerApp runtime clamp",
    ),
    ParameterSpec(
        "controller.angular_scale",
        "Angular input scale",
        "CONTROLLER_INPUT",
        0.0,
        1.0,
        0.01,
        "ratio",
        "controller_mapping.json / ControllerApp runtime clamp",
    ),
    ParameterSpec(
        "motion.open_loop_max_pwm",
        "Open-loop PWM limit",
        "PC_MOTION_LIMIT",
        0.0,
        1023.0,
        1.0,
        "PWM",
        "vehicle_config.json / ControllerApp _pwm_limit clamp/int; 0 falls back to 1023",
    ),
    ParameterSpec(
        "motion.pivot_max_pwm",
        "Pivot PWM limit",
        "PC_MOTION_LIMIT",
        0.0,
        1023.0,
        1.0,
        "PWM",
        "vehicle_config.json / ControllerApp _pwm_limit clamp/int; 0 falls back to open-loop limit",
    ),
)

_SPEC_BY_KEY = {spec.key: spec for spec in PARAMETER_SPECS}


@dataclass(frozen=True)
class ParameterRowSnapshot:
    key: str
    label: str
    group: str
    current_value: float | None
    pending_value: float | None
    pending_raw: str | None
    saved_controller_loaded_value: float | None
    minimum: float
    maximum: float
    step: float
    unit: str
    source: str
    validation: str
    revert_state: str
    apply_state: str


@dataclass(frozen=True)
class ParameterEditorSnapshot:
    robot_id: str
    configured: bool
    workflow_state: str
    rows: tuple[ParameterRowSnapshot, ...]
    pending_count: int
    invalid_count: int
    revert_state: str
    apply_state: str
    save_state: str
    output_state: str


@dataclass(frozen=True)
class _ParameterDraft:
    raw_value: object
    base_signature: tuple[object, ...]


class ParameterDraftStore:
    """Keep independent output-free parameter drafts for R1 and R2."""

    def __init__(self) -> None:
        self._drafts: dict[str, dict[str, _ParameterDraft]] = {}

    def stage(
        self,
        robot: RobotDashboardSnapshot,
        parameter_key: str,
        raw_value: object,
    ) -> ParameterEditorSnapshot:
        if not robot.configured:
            raise ValueError("cannot create Parameter draft for an unbound robot")
        if parameter_key not in _SPEC_BY_KEY:
            raise ValueError(f"unsupported parameter key: {parameter_key}")

        robot_id = _robot_id(robot)
        drafts = self._drafts.setdefault(robot_id, {})
        parsed = _parse_value(raw_value)
        saved = _source_values(robot).get(parameter_key)
        if parsed is not None and saved is not None and parsed == saved:
            drafts.pop(parameter_key, None)
        else:
            drafts[parameter_key] = _ParameterDraft(
                raw_value,
                _base_signature(robot, parameter_key, raw_value),
            )
        if not drafts:
            self._drafts.pop(robot_id, None)
        return self.build(robot)

    def revert(self, robot_id: str, parameter_key: str | None = None) -> bool:
        robot_key = str(robot_id)
        drafts = self._drafts.get(robot_key)
        if not drafts:
            return False
        if parameter_key is None:
            self._drafts.pop(robot_key, None)
            return True
        changed = drafts.pop(parameter_key, None) is not None
        if not drafts:
            self._drafts.pop(robot_key, None)
        return changed

    def build(self, robot: RobotDashboardSnapshot) -> ParameterEditorSnapshot:
        robot_id = _robot_id(robot)
        source_values = _source_values(robot)
        drafts = self._drafts.get(robot_id, {})
        rows = tuple(
            _build_row(
                robot,
                spec,
                source_values,
                drafts.get(spec.key),
            )
            for spec in PARAMETER_SPECS
        )
        pending_count = sum(row.pending_raw is not None for row in rows)
        invalid_count = sum(
            row.pending_raw is not None
            and row.validation not in {"PENDING_VALID_LOCAL_ONLY", "PENDING_SOURCE_RUNTIME_CLAMPED"}
            for row in rows
        )

        if not robot.configured:
            workflow_state = "UNBOUND"
        elif pending_count == 0:
            workflow_state = "READ_ONLY_AUDIT"
        elif invalid_count:
            workflow_state = "LOCAL_DRAFT_INVALID"
        else:
            workflow_state = "LOCAL_DRAFT_READY"

        return ParameterEditorSnapshot(
            robot_id=robot_id,
            configured=robot.configured,
            workflow_state=workflow_state,
            rows=rows,
            pending_count=pending_count,
            invalid_count=invalid_count,
            revert_state="AVAILABLE_LOCAL_ONLY" if pending_count else "NO_PENDING_CHANGE",
            apply_state="BLOCKED_NO_CONTROLLER_API",
            save_state="BLOCKED_NO_CONTROLLER_API",
            output_state="LOCAL_DRAFT_ONLY_NO_CONFIG_OR_HARDWARE_OUTPUT",
        )


def _build_row(
    robot: RobotDashboardSnapshot,
    spec: ParameterSpec,
    source_values: dict[str, float | None],
    draft: _ParameterDraft | None,
) -> ParameterRowSnapshot:
    saved = source_values.get(spec.key)
    current = _effective_value(spec, saved, source_values)
    pending = _parse_value(draft.raw_value) if draft is not None else None
    pending_raw = str(draft.raw_value) if draft is not None else None

    if not robot.configured:
        validation = "UNBOUND"
    elif saved is None:
        validation = "SOURCE_MISSING"
    elif not isfinite(saved):
        validation = "SOURCE_NON_FINITE"
    elif draft is None:
        validation = "SOURCE_RUNTIME_CLAMPED" if current != saved else "SOURCE_CONFIG_VALID"
    elif draft.base_signature != _base_signature(robot, spec.key, draft.raw_value):
        validation = "STALE_BASE_CONFIG"
    elif pending is None:
        validation = "PENDING_INVALID_FORMAT"
    elif not spec.minimum <= pending <= spec.maximum:
        validation = "PENDING_OUT_OF_RANGE"
    elif spec.key.startswith("motion.") and pending != int(pending):
        validation = "PENDING_REQUIRES_INTEGER"
    elif current != saved:
        validation = "PENDING_SOURCE_RUNTIME_CLAMPED"
    else:
        validation = "PENDING_VALID_LOCAL_ONLY"

    return ParameterRowSnapshot(
        key=spec.key,
        label=spec.label,
        group=spec.group,
        current_value=current,
        pending_value=pending,
        pending_raw=pending_raw,
        saved_controller_loaded_value=saved,
        minimum=spec.minimum,
        maximum=spec.maximum,
        step=spec.step,
        unit=spec.unit,
        source=spec.source,
        validation=validation,
        revert_state="AVAILABLE_LOCAL_ONLY" if draft is not None else "NO_PENDING_CHANGE",
        apply_state="BLOCKED_NO_CONTROLLER_API",
    )


def _source_values(robot: RobotDashboardSnapshot) -> dict[str, float | None]:
    mapping = robot.controller_mapping
    motion = robot.motion_parameters
    return {
        "controller.deadzone": mapping.deadzone,
        "controller.linear_scale": mapping.linear_scale,
        "controller.angular_scale": mapping.angular_scale,
        "motion.open_loop_max_pwm": motion.open_loop_max_pwm,
        "motion.pivot_max_pwm": motion.pivot_max_pwm,
    }


def _base_signature(
    robot: RobotDashboardSnapshot,
    parameter_key: str,
    pending_raw: object,
) -> tuple[object, ...]:
    values = _source_values(robot)
    if parameter_key == "motion.pivot_max_pwm" and (
        _uses_zero_pwm_fallback(values[parameter_key])
        or _uses_zero_pwm_fallback(pending_raw)
    ):
        return (values[parameter_key], values["motion.open_loop_max_pwm"])
    return (values[parameter_key],)


def _parse_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) else None


def _clamp(value: float, spec: ParameterSpec) -> float:
    return max(spec.minimum, min(spec.maximum, value))


def _uses_zero_pwm_fallback(value: object) -> bool:
    parsed = _parse_value(value)
    return parsed is not None and int(max(0.0, min(1023.0, parsed))) == 0


def _effective_value(
    spec: ParameterSpec,
    saved: float | None,
    source_values: dict[str, float | None],
) -> float | None:
    """Mirror the current ControllerApp clamp, integer, and zero fallback rules."""
    if saved is None:
        return None
    bounded = _clamp(saved, spec)
    if spec.key not in {"motion.open_loop_max_pwm", "motion.pivot_max_pwm"}:
        return bounded

    pwm_limit = int(bounded)
    if pwm_limit > 0:
        return float(pwm_limit)
    if spec.key == "motion.open_loop_max_pwm":
        return 1023.0

    open_loop_spec = _SPEC_BY_KEY["motion.open_loop_max_pwm"]
    return _effective_value(
        open_loop_spec,
        source_values.get(open_loop_spec.key),
        source_values,
    )


def _robot_id(robot: RobotDashboardSnapshot) -> str:
    return str(getattr(robot.robot_id, "value", robot.robot_id))
