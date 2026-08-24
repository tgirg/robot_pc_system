"""Local-only Direction / Coordinate Calibration model.

The model keeps controller input correction, the fixed machine coordinate
convention, motor polarity, servo angle direction, and logical-front preview as
separate semantic layers.  Drafts live only in process memory.  This module has
no ControllerApp, Serial, config-file, ARM, DEBUG, or actuator output API.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from .controller_input import (
    correct_controller_axis,
    transform_for_logical_front as _transform_for_logical_front,
)
from .gui_model import RobotDashboardSnapshot

LOGICAL_FRONTS = ("FRONT", "RIGHT", "REAR", "LEFT")


@dataclass(frozen=True)
class ControllerDirectionRowSnapshot:
    semantic: str
    axis_index: int | None
    current_inverted: bool | None
    pending_inverted: bool | None
    saved_inverted: bool | None
    validation: str


@dataclass(frozen=True)
class WheelDirectionRowSnapshot:
    logical_index: int
    logical_name: str
    current_motor_inverted: bool | None
    pending_motor_inverted: bool | None
    saved_motor_inverted: bool | None
    current_servo_inverted: bool | None
    pending_servo_inverted: bool | None
    saved_servo_inverted: bool | None
    servo_calibrated: bool | None
    validation: str


@dataclass(frozen=True)
class DirectionVectorStage:
    vx: float | None
    vy: float | None
    omega: float | None


@dataclass(frozen=True)
class DirectionPreviewSnapshot:
    raw_controller: DirectionVectorStage
    corrected_controller: DirectionVectorStage
    machine_relative: DirectionVectorStage
    logical_front_transformed: DirectionVectorStage
    final_command_preview: DirectionVectorStage
    logical_front: str
    affected_axes: str
    validation: str


@dataclass(frozen=True)
class DirectionCalibrationSnapshot:
    robot_id: str
    configured: bool
    workflow_state: str
    validation: str
    controller_rows: tuple[ControllerDirectionRowSnapshot, ...]
    wheel_rows: tuple[WheelDirectionRowSnapshot, ...]
    machine_x_positive: str
    machine_y_positive: str
    machine_omega_positive: str
    pivot_direction_inverted: bool | None
    current_logical_front: str
    pending_logical_front: str | None
    saved_logical_front: str
    affected_axes: str
    preview: DirectionPreviewSnapshot
    pending_count: int
    revert_state: str
    apply_state: str
    save_state: str
    output_state: str


@dataclass(frozen=True)
class _PendingDraft:
    invert_vx: object
    invert_vy: object
    invert_omega: object
    logical_front: str
    motor_inverted: tuple[object, ...]
    servo_inverted: tuple[object, ...]
    base_signature: tuple[object, ...]


class DirectionDraftStore:
    """Keep one output-free Direction draft per robot."""

    def __init__(self) -> None:
        self._drafts: dict[str, _PendingDraft] = {}

    def stage(
        self,
        robot: RobotDashboardSnapshot,
        *,
        invert_vx: object,
        invert_vy: object,
        invert_omega: object,
        logical_front: str,
        motor_inverted: Sequence[object],
        servo_inverted: Sequence[object],
        preview_input: Sequence[object] = (0.6, 0.25, 0.2),
    ) -> DirectionCalibrationSnapshot:
        if not robot.configured:
            raise ValueError("cannot create Direction draft for an unbound robot")
        draft = _PendingDraft(
            invert_vx=invert_vx,
            invert_vy=invert_vy,
            invert_omega=invert_omega,
            logical_front=str(logical_front).strip().upper(),
            motor_inverted=tuple(motor_inverted),
            servo_inverted=tuple(servo_inverted),
            base_signature=_base_signature(robot),
        )
        if _draft_matches_current(robot, draft):
            self._drafts.pop(_robot_id(robot), None)
        else:
            self._drafts[_robot_id(robot)] = draft
        return self.build(robot, preview_input=preview_input)

    def revert(self, robot_id: str) -> bool:
        """Discard one local draft without changing config or hardware."""
        return self._drafts.pop(str(robot_id), None) is not None

    def build(
        self,
        robot: RobotDashboardSnapshot,
        *,
        preview_input: Sequence[object] = (0.6, 0.25, 0.2),
    ) -> DirectionCalibrationSnapshot:
        robot_id = _robot_id(robot)
        source_validation = _source_validation(robot)
        draft = self._drafts.get(robot_id)
        validation = source_validation
        if draft is not None:
            if draft.base_signature != _base_signature(robot):
                validation = "STALE_BASE_CONFIG"
            else:
                validation = _draft_validation(robot, draft)

        current_inversions = _current_controller_inversions(robot)
        pending_inversions = _pending_controller_inversions(draft)
        controller_rows = tuple(
            ControllerDirectionRowSnapshot(
                semantic=semantic,
                axis_index=axis,
                current_inverted=current,
                pending_inverted=pending,
                saved_inverted=current,
                validation=validation if draft is not None else source_validation,
            )
            for semantic, axis, current, pending in zip(
                ("vx / forward", "vy / left", "omega / CCW"),
                _current_controller_axes(robot),
                current_inversions,
                pending_inversions,
            )
        )

        pending_motor = draft.motor_inverted if draft is not None else ()
        pending_servo = draft.servo_inverted if draft is not None else ()
        wheel_rows = tuple(
            WheelDirectionRowSnapshot(
                logical_index=wheel.logical_index,
                logical_name=wheel.name,
                current_motor_inverted=wheel.motor_inverted,
                pending_motor_inverted=_bool_at(pending_motor, index),
                saved_motor_inverted=wheel.motor_inverted,
                current_servo_inverted=wheel.servo_inverted,
                pending_servo_inverted=_bool_at(pending_servo, index),
                saved_servo_inverted=wheel.servo_inverted,
                servo_calibrated=wheel.servo_calibrated,
                validation=validation if draft is not None else source_validation,
            )
            for index, wheel in enumerate(robot.wheels)
        )

        current_logical_front = _current_logical_front(robot)
        logical_front = _effective_logical_front(draft, current_logical_front)
        preview = _build_preview(
            robot,
            preview_input,
            pending_inversions if draft is not None else current_inversions,
            logical_front,
        )
        pending_count = _pending_count(robot, draft)
        if not robot.configured:
            workflow_state = "UNBOUND"
        elif draft is None:
            workflow_state = "READ_ONLY_AUDIT" if source_validation == "SOURCE_CONFIG_VALID" else "SOURCE_CONFIG_INVALID"
        elif validation == "PENDING_VALID_LOCAL_ONLY":
            workflow_state = "LOCAL_DRAFT_READY"
        else:
            workflow_state = "LOCAL_DRAFT_INVALID"

        return DirectionCalibrationSnapshot(
            robot_id=robot_id,
            configured=robot.configured,
            workflow_state=workflow_state,
            validation=validation,
            controller_rows=controller_rows,
            wheel_rows=wheel_rows,
            machine_x_positive=robot.machine_coordinate.x_positive,
            machine_y_positive=robot.machine_coordinate.y_positive,
            machine_omega_positive=robot.machine_coordinate.omega_positive,
            pivot_direction_inverted=robot.machine_coordinate.pivot_direction_inverted,
            current_logical_front=current_logical_front,
            pending_logical_front=draft.logical_front if draft is not None else None,
            saved_logical_front=current_logical_front,
            affected_axes=_affected_axes(logical_front),
            preview=preview,
            pending_count=pending_count,
            revert_state="AVAILABLE_LOCAL_ONLY" if draft is not None else "NO_PENDING_CHANGE",
            apply_state="BLOCKED_NO_CONTROLLER_API",
            save_state="BLOCKED_NO_CONTROLLER_API",
            output_state="LOCAL_PREVIEW_ONLY_NO_OUTPUT",
        )


def transform_for_logical_front(vx: float, vy: float, logical_front: str) -> tuple[float, float]:
    """Rotate a logical-front command into the existing machine body frame."""
    return _transform_for_logical_front(vx, vy, logical_front)


def _build_preview(
    robot: RobotDashboardSnapshot,
    preview_input: Sequence[object],
    inversions: tuple[bool | None, bool | None, bool | None],
    logical_front: str,
) -> DirectionPreviewSnapshot:
    raw = _parse_preview_input(preview_input)
    if raw is None or not all(isinstance(value, bool) for value in inversions) or logical_front not in LOGICAL_FRONTS:
        empty = DirectionVectorStage(None, None, None)
        raw_stage = empty if raw is None else DirectionVectorStage(*raw)
        return DirectionPreviewSnapshot(
            raw_stage,
            empty,
            empty,
            empty,
            empty,
            logical_front,
            _affected_axes(logical_front),
            "PREVIEW_INVALID_INPUT",
        )

    mapping = robot.controller_mapping
    deadzone = mapping.deadzone
    linear_scale = mapping.linear_scale
    angular_scale = mapping.angular_scale
    max_linear = robot.machine_coordinate.max_linear_speed_mps
    max_angular = robot.machine_coordinate.max_angular_speed_radps
    if any(value is None for value in (deadzone, linear_scale, angular_scale, max_linear, max_angular)):
        empty = DirectionVectorStage(None, None, None)
        return DirectionPreviewSnapshot(
            DirectionVectorStage(*raw),
            empty,
            empty,
            empty,
            empty,
            logical_front,
            _affected_axes(logical_front),
            "PREVIEW_BLOCKED_SOURCE_CONFIG_INVALID",
        )

    corrected = (
        correct_controller_axis(raw[0], bool(inversions[0]), float(deadzone)),
        correct_controller_axis(raw[1], bool(inversions[1]), float(deadzone)),
        correct_controller_axis(raw[2], bool(inversions[2]), float(deadzone)),
    )
    machine = (
        corrected[0] * float(max_linear) * float(linear_scale),
        corrected[1] * float(max_linear) * float(linear_scale),
        corrected[2] * float(max_angular) * float(angular_scale),
    )
    transformed_vx, transformed_vy = transform_for_logical_front(machine[0], machine[1], logical_front)
    transformed = (transformed_vx, transformed_vy, machine[2])
    return DirectionPreviewSnapshot(
        raw_controller=DirectionVectorStage(*raw),
        corrected_controller=DirectionVectorStage(*corrected),
        machine_relative=DirectionVectorStage(*machine),
        logical_front_transformed=DirectionVectorStage(*transformed),
        final_command_preview=DirectionVectorStage(*transformed),
        logical_front=logical_front,
        affected_axes=_affected_axes(logical_front),
        validation="PREVIEW_VALID_LOCAL_ONLY",
    )


def _source_validation(robot: RobotDashboardSnapshot) -> str:
    if not robot.configured:
        return "UNBOUND"
    mapping = robot.controller_mapping
    axes = (mapping.axis_vx, mapping.axis_vy, mapping.axis_omega)
    inversions = (mapping.invert_vx, mapping.invert_vy, mapping.invert_omega)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in axes):
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    if len(set(axes)) != 3 or any(not isinstance(value, bool) for value in inversions):
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    if mapping.deadzone is None or not 0.0 <= mapping.deadzone <= 0.95:
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    if mapping.linear_scale is None or not 0.0 <= mapping.linear_scale <= 1.0:
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    if mapping.angular_scale is None or not 0.0 <= mapping.angular_scale <= 1.0:
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    if mapping.logical_front not in LOGICAL_FRONTS:
        return "SOURCE_CONTROLLER_MAPPING_INVALID"
    machine = robot.machine_coordinate
    if (machine.x_positive, machine.y_positive, machine.omega_positive) != ("FORWARD", "LEFT", "CCW"):
        return "SOURCE_MACHINE_COORDINATE_INVALID"
    if machine.max_linear_speed_mps is None or machine.max_linear_speed_mps <= 0.0:
        return "SOURCE_MACHINE_COORDINATE_INVALID"
    if machine.max_angular_speed_radps is None or machine.max_angular_speed_radps <= 0.0:
        return "SOURCE_MACHINE_COORDINATE_INVALID"
    if len(robot.wheels) != 4 or any(
        not isinstance(wheel.motor_inverted, bool) or not isinstance(wheel.servo_inverted, bool)
        for wheel in robot.wheels
    ):
        return "SOURCE_WHEEL_DIRECTION_INVALID"
    return "SOURCE_CONFIG_VALID"


def _draft_validation(robot: RobotDashboardSnapshot, draft: _PendingDraft) -> str:
    source_validation = _source_validation(robot)
    if source_validation != "SOURCE_CONFIG_VALID":
        return "PENDING_BLOCKED_SOURCE_CONFIG_INVALID"
    if draft.logical_front not in LOGICAL_FRONTS:
        return "PENDING_INVALID_LOGICAL_FRONT"
    values = (draft.invert_vx, draft.invert_vy, draft.invert_omega, *draft.motor_inverted, *draft.servo_inverted)
    if any(not isinstance(value, bool) for value in values):
        return "PENDING_INVALID_DIRECTION_VALUE"
    if len(draft.motor_inverted) != len(robot.wheels) or len(draft.servo_inverted) != len(robot.wheels):
        return "PENDING_INVALID_WHEEL_COUNT"
    return "PENDING_VALID_LOCAL_ONLY"


def _base_signature(robot: RobotDashboardSnapshot) -> tuple[object, ...]:
    mapping = robot.controller_mapping
    machine = robot.machine_coordinate
    return (
        mapping.axis_vx,
        mapping.axis_vy,
        mapping.axis_omega,
        mapping.invert_vx,
        mapping.invert_vy,
        mapping.invert_omega,
        mapping.logical_front,
        mapping.deadzone,
        mapping.linear_scale,
        mapping.angular_scale,
        machine.x_positive,
        machine.y_positive,
        machine.omega_positive,
        machine.max_linear_speed_mps,
        machine.max_angular_speed_radps,
        machine.pivot_direction_inverted,
        tuple((wheel.logical_index, wheel.motor_inverted, wheel.servo_inverted) for wheel in robot.wheels),
    )


def _draft_matches_current(robot: RobotDashboardSnapshot, draft: _PendingDraft) -> bool:
    if _draft_validation(robot, draft) != "PENDING_VALID_LOCAL_ONLY":
        return False
    return (
        (draft.invert_vx, draft.invert_vy, draft.invert_omega) == _current_controller_inversions(robot)
        and draft.logical_front == _current_logical_front(robot)
        and draft.motor_inverted == tuple(wheel.motor_inverted for wheel in robot.wheels)
        and draft.servo_inverted == tuple(wheel.servo_inverted for wheel in robot.wheels)
    )


def _pending_count(robot: RobotDashboardSnapshot, draft: _PendingDraft | None) -> int:
    if draft is None:
        return 0
    count = sum(
        pending != current
        for pending, current in zip(
            (draft.invert_vx, draft.invert_vy, draft.invert_omega),
            _current_controller_inversions(robot),
        )
    )
    count += int(draft.logical_front != _current_logical_front(robot))
    count += sum(pending != wheel.motor_inverted for pending, wheel in zip(draft.motor_inverted, robot.wheels))
    count += sum(pending != wheel.servo_inverted for pending, wheel in zip(draft.servo_inverted, robot.wheels))
    return max(1, count)


def _current_controller_axes(robot: RobotDashboardSnapshot) -> tuple[int | None, int | None, int | None]:
    mapping = robot.controller_mapping
    return mapping.axis_vx, mapping.axis_vy, mapping.axis_omega


def _current_controller_inversions(robot: RobotDashboardSnapshot) -> tuple[bool | None, bool | None, bool | None]:
    mapping = robot.controller_mapping
    return mapping.invert_vx, mapping.invert_vy, mapping.invert_omega


def _pending_controller_inversions(
    draft: _PendingDraft | None,
) -> tuple[bool | None, bool | None, bool | None]:
    if draft is None:
        return None, None, None
    return _as_bool(draft.invert_vx), _as_bool(draft.invert_vy), _as_bool(draft.invert_omega)


def _current_logical_front(robot: RobotDashboardSnapshot) -> str:
    front = robot.controller_mapping.logical_front
    return front if front in LOGICAL_FRONTS else "FRONT"


def _effective_logical_front(draft: _PendingDraft | None, current: str) -> str:
    return draft.logical_front if draft is not None and draft.logical_front in LOGICAL_FRONTS else current


def _affected_axes(logical_front: str) -> str:
    return {
        "FRONT": "+logical X -> +machine X; +logical Y -> +machine Y",
        "RIGHT": "+logical X -> -machine Y; +logical Y -> +machine X",
        "REAR": "+logical X -> -machine X; +logical Y -> -machine Y",
        "LEFT": "+logical X -> +machine Y; +logical Y -> -machine X",
    }.get(logical_front, "UNKNOWN")


def _parse_preview_input(values: Sequence[object]) -> tuple[float, float, float] | None:
    if len(values) != 3:
        return None
    parsed: list[float] = []
    for value in values:
        try:
            item = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not isfinite(item):
            return None
        parsed.append(item)
    return parsed[0], parsed[1], parsed[2]


def _bool_at(values: Sequence[object], index: int) -> bool | None:
    return _as_bool(values[index]) if index < len(values) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _robot_id(robot: RobotDashboardSnapshot) -> str:
    return str(getattr(robot.robot_id, "value", robot.robot_id))
