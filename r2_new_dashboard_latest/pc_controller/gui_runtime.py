"""Single-owner runtimes for the new shared dashboard.

The Fake runtime remains output-free.  The real runtime is an explicit R2-only
bridge that keeps the existing :class:`ControllerApp` safety/protocol path as
the sole transport owner while the new dashboard renders immutable snapshots.
"""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path
from typing import Callable, Protocol

from .app import ControllerApp, build_arg_parser
from .autonomy import RobotId
from .config_manager import validate_vehicle_config
from .controller_input import ControllerState, PygameController
from .gui_model import (
    FleetDashboardSnapshot,
    build_fleet_dashboard_snapshot,
    build_robot_dashboard_snapshot,
)
from .node_inventory import NodeRequirement, load_node_manifest
from .protocol import disarm_message, encode_message, hello_message
from .safety import SafetyState
from .serial_discovery import AmbiguousSerialNodeError


class ControllerInputSource(Protocol):
    """Minimal controller surface used by the Qt-owned real runtime."""

    def read(self) -> ControllerState: ...


class FakeFleetDashboardRuntime:
    """Own one protocol-faithful Fake controller and publish fleet snapshots."""

    def __init__(
        self,
        controller: ControllerApp,
        *,
        robot_id: RobotId,
        node_requirements: tuple[NodeRequirement, ...] = (),
    ) -> None:
        if not isinstance(robot_id, RobotId):
            raise ValueError("robot_id must be a RobotId")
        if controller.fake_device is None or controller.serial is None:
            raise ValueError("FakeFleetDashboardRuntime requires one Fake ESP32 ControllerApp")
        if bool(getattr(controller.args, "simulate", False)):
            raise ValueError("legacy direct simulation is not a Fake ESP32 runtime")
        self.controller = controller
        self.robot_id = robot_id
        self.node_requirements = tuple(node_requirements)
        self._selected_robot = robot_id
        self._started = False
        self._closed = False
        self._last_snapshot: FleetDashboardSnapshot | None = None

    @classmethod
    def create(
        cls,
        *,
        robot_id: RobotId,
        config_dir: str | Path,
        node_manifest: str | Path,
        now_ms: Callable[[], int] | None = None,
        fake_trace: bool = False,
    ) -> "FakeFleetDashboardRuntime":
        """Build the only supported backend: ControllerApp over VirtualSerial."""
        argv = [
            "--fake-esp32",
            "--no-joystick",
            "--config-dir",
            str(Path(config_dir)),
        ]
        if fake_trace:
            argv.append("--fake-trace")
        args = build_arg_parser().parse_args(argv)
        requirements = load_node_manifest(node_manifest)
        return cls(
            ControllerApp(args, now_ms=now_ms),
            robot_id=robot_id,
            node_requirements=requirements,
        )

    @property
    def selected_robot(self) -> RobotId:
        return self._selected_robot

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> FleetDashboardSnapshot:
        """Perform a non-blocking DISARM/HELLO/CONFIG handshake and stay SAFE."""
        self._require_open()
        if self._started:
            return self.snapshot()

        validate_vehicle_config(self.controller.config, require_armable=False)
        self.controller.safety.apply_config()
        self.controller.last_motion_request = (0.0, 0.0, 0.0)

        # Initial GUI attachment is intentionally at least as conservative as
        # reconnect: explicitly DISARM before identity/config negotiation.
        self.controller.reconnect_phase = "hello_pending"
        self.controller.reconnect_deadline_ms = (
            self.controller._now_ms() + self.controller.reconnect_handshake_timeout_ms
        )
        if self.controller._write_serial_message(disarm_message()):
            self.controller._write_serial_message(hello_message())
        # The first drain handles DISARM/HELLO and schedules CONFIG through the
        # existing reconnect identity gate. The second handles an immediate
        # Fake config_ack; delayed responses remain pending for normal ticks.
        self.controller._read_serial_messages()
        self.controller._read_serial_messages()
        self._mark_ready_disarmed()

        self._started = True
        return self.snapshot()

    def tick(self) -> FleetDashboardSnapshot:
        """Advance the shared controller with zero input and publish a snapshot."""
        self._require_started()
        self.controller.tick(0.0, 0.0, 0.0)
        self._mark_ready_disarmed()
        return self.snapshot()

    def select_robot(self, robot_id: RobotId) -> FleetDashboardSnapshot:
        """Change only the local view; never change controller binding or output."""
        self._require_started()
        if not isinstance(robot_id, RobotId):
            raise ValueError("robot_id must be a RobotId")
        self._selected_robot = robot_id
        return self.snapshot()

    def snapshot(self) -> FleetDashboardSnapshot:
        """Build the latest immutable R1/R2 view without changing controller state."""
        self._require_started()
        now_ms = self.controller._now_ms()
        bound = build_robot_dashboard_snapshot(
            self.controller,
            self.robot_id,
            now_ms=now_ms,
            node_requirements=self.node_requirements,
        )
        self._last_snapshot = build_fleet_dashboard_snapshot(
            self._selected_robot,
            (bound,),
            now_ms=now_ms,
        )
        return self._last_snapshot

    def close(self) -> None:
        """Idempotently DISARM and close the runtime's sole transport."""
        if self._closed:
            return
        serial = self.controller.serial
        self.controller.last_motion_request = (0.0, 0.0, 0.0)
        self.controller.safety.disarm()
        if serial is not None:
            try:
                serial.write(self._encoded_disarm())
            except (OSError, RuntimeError) as exc:
                print(f"Fake dashboard shutdown DISARM failed: {exc}", file=sys.stderr, flush=True)
            try:
                serial.close()
            except (OSError, RuntimeError) as exc:
                print(f"Fake dashboard transport close failed: {exc}", file=sys.stderr, flush=True)
        self._closed = True

    @staticmethod
    def _encoded_disarm() -> bytes:
        # Keep protocol encoding inside the normal codec without exposing a
        # general message-send surface on this runtime.
        from .protocol import encode_message

        return encode_message(disarm_message())

    def _mark_ready_disarmed(self) -> None:
        if (
            self.controller.serial is not None
            and self.controller.safety.config_accepted
            and self.controller.safety.state == SafetyState.SAFE
            and not self.controller.safety.armed
            and self.controller.reconnect_phase == "ready"
        ):
            self.controller.reconnect_phase = "ready_disarmed"

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Fake dashboard runtime is closed")

    def _require_started(self) -> None:
        self._require_open()
        if not self._started:
            raise RuntimeError("Fake dashboard runtime is not started")


class RealFleetDashboardRuntime:
    """Own one real R2 controller behind the new shared dashboard.

    Motion is disabled by default and can only be enabled by the explicit
    launcher flag.  Even when enabled, the first-motion PWM clamp is limited to
    120 and normal ControllerApp ARM/DISARM/timeout handling remains in force.
    """

    FIRST_MOTION_MAX_PWM = 120
    view_locked = True

    def __init__(
        self,
        controller: ControllerApp,
        *,
        robot_id: RobotId,
        node_requirements: tuple[NodeRequirement, ...] = (),
        controller_input: ControllerInputSource | None = None,
        motion_enabled: bool = False,
        max_pwm: int = FIRST_MOTION_MAX_PWM,
    ) -> None:
        if robot_id != RobotId.R2:
            raise ValueError("real shared dashboard currently supports R2 only")
        if controller.fake_device is not None or bool(getattr(controller.args, "simulate", False)):
            raise ValueError("real shared dashboard requires the physical serial backend")
        if int(max_pwm) < 1 or int(max_pwm) > self.FIRST_MOTION_MAX_PWM:
            raise ValueError(f"max_pwm must be between 1 and {self.FIRST_MOTION_MAX_PWM}")
        self.controller = controller
        self.robot_id = robot_id
        self.node_requirements = tuple(node_requirements)
        self.controller_input = controller_input
        self.motion_enabled = bool(motion_enabled)
        self.max_pwm = int(max_pwm)
        self._last_controller_state = ControllerState(connected=False, name="")
        self._selected_robot = robot_id
        self._started = False
        self._closed = False
        self._pid_written = False
        self._last_snapshot: FleetDashboardSnapshot | None = None

    @classmethod
    def create(
        cls,
        *,
        robot_id: RobotId,
        config_dir: str | Path,
        node_manifest: str | Path,
        port: str | None = None,
        node_role: str = "drive",
        node_id: str | None = None,
        discovery_timeout: float = 1.2,
        reconnect_interval: float = 1.0,
        reconnect_handshake_timeout: float = 2.0,
        motion_enabled: bool = False,
        max_pwm: int = FIRST_MOTION_MAX_PWM,
        now_ms: Callable[[], int] | None = None,
    ) -> "RealFleetDashboardRuntime":
        """Build an R2 runtime without opening Serial or sending output yet."""
        argv = [
            "--config-dir",
            str(Path(config_dir)),
            "--node-role",
            str(node_role),
            "--discovery-timeout",
            str(float(discovery_timeout)),
            "--reconnect-interval",
            str(float(reconnect_interval)),
            "--reconnect-handshake-timeout",
            str(float(reconnect_handshake_timeout)),
        ]
        if port:
            argv.extend(["--port", str(port)])
        if node_id:
            argv.extend(["--node-id", str(node_id)])
        args = build_arg_parser().parse_args(argv)
        requirements = load_node_manifest(node_manifest)
        return cls(
            ControllerApp(args, now_ms=now_ms),
            robot_id=robot_id,
            node_requirements=requirements,
            motion_enabled=motion_enabled,
            max_pwm=max_pwm,
        )

    @property
    def selected_robot(self) -> RobotId:
        return self._selected_robot

    @property
    def closed(self) -> bool:
        return self._closed

    def start(self) -> FleetDashboardSnapshot:
        """Open the input/transport and begin DISARM -> HELLO -> CONFIG."""
        self._require_open()
        if self._started:
            return self.snapshot()

        validate_vehicle_config(self.controller.config, require_armable=False)
        self._apply_first_motion_clamp()
        self.controller.safety.apply_config()
        self.controller.last_motion_request = (0.0, 0.0, 0.0)
        self.controller.reconnect_require_arm_release = True
        self.controller._write_pid_file()
        self._pid_written = True

        try:
            if self.controller_input is None:
                self.controller_input = PygameController(self.controller.mapping)
            self.controller.controller = self.controller_input
            if self.controller.serial is None:
                try:
                    self.controller._open_initial_serial_transport()
                except AmbiguousSerialNodeError:
                    # Duplicate/wrongly identified candidates require an
                    # operator choice; never let reconnect pick one later.
                    raise
                except RuntimeError as exc:
                    if not self.controller._resident_startup_retry_enabled():
                        raise
                    self.controller._schedule_startup_retry(exc)
            if self.controller.serial is not None:
                self._begin_safe_handshake()
                # VirtualSerial tests can complete immediately; a physical
                # ESP32 completes on later Qt ticks without blocking the UI.
                self.controller._read_serial_messages()
                self.controller._read_serial_messages()
                self._mark_ready_disarmed()
        except Exception:
            self.close()
            raise

        self._started = True
        return self.snapshot()

    def tick(self) -> FleetDashboardSnapshot:
        """Read the controller, advance ControllerApp, and publish one snapshot."""
        self._require_started()
        if self.controller_input is None:
            raise RuntimeError("R2 controller input is not initialized")
        state = self.controller_input.read()
        self._last_controller_state = state
        if not self.motion_enabled:
            # Keep controller presence and the SAFE button observable while
            # suppressing ARM and all axes unless motion was explicitly enabled.
            state = ControllerState(
                connected=state.connected,
                name=state.name,
                safe_pressed=state.safe_pressed,
            )
        self.controller.tick_controller(state)
        self._mark_ready_disarmed()
        return self.snapshot()

    def controller_input_snapshot(self) -> ControllerState:
        """Return the last observed input for GUI diagnostics only."""
        return self._last_controller_state

    def apply_settings(
        self,
        vehicle_config: dict,
        controller_mapping: dict,
        *,
        acknowledgement_timeout: float = 2.0,
    ) -> FleetDashboardSnapshot:
        """Apply validated settings while SAFE and wait for ESP32 CONFIG ACK.

        The previous in-memory settings are restored on any failure.  The
        caller owns restoring the on-disk files from its pre-save backup.
        """
        self._require_started()
        if self.controller.safety.armed or self.controller.safety.state != SafetyState.SAFE:
            raise RuntimeError("R2 must be SAFE and disarmed before applying settings")
        if self.controller.serial is None:
            raise RuntimeError("ESP32 is not connected; settings were not applied")

        candidate_config = copy.deepcopy(vehicle_config)
        candidate_mapping = copy.deepcopy(controller_mapping)
        validate_vehicle_config(candidate_config, require_armable=False)

        previous_config = copy.deepcopy(self.controller.config)
        previous_mapping = copy.deepcopy(self.controller.mapping)
        try:
            self.controller.config = candidate_config
            self.controller.mapping = candidate_mapping
            self._apply_first_motion_clamp()
            self.controller.transition = self.controller._build_transition_controller()
            self._set_input_mapping(candidate_mapping)
            self.controller.last_motion_request = (0.0, 0.0, 0.0)
            self.controller.last_drive_command = None
            self.controller.arm_pressed_since_ms = None
            self.controller.reconnect_require_arm_release = True
            self.controller.safety.apply_config()
            self.controller.reconnect_phase = "config_pending"
            self.controller.reconnect_deadline_ms = (
                self.controller._now_ms() + max(100, int(float(acknowledgement_timeout) * 1000))
            )
            if not self.controller._write_serial_message(disarm_message()):
                raise RuntimeError("failed to send DISARM before applying settings")
            if not self.controller._write_serial_message(self.controller.config):
                raise RuntimeError("failed to send CONFIG to ESP32")
            self._wait_for_config_ack(acknowledgement_timeout)
        except Exception:
            self._restore_previous_settings(previous_config, previous_mapping)
            raise
        self._mark_ready_disarmed()
        return self.snapshot()

    def _wait_for_config_ack(self, timeout: float) -> None:
        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            self.controller._read_serial_messages()
            if (
                self.controller.safety.config_accepted
                and self.controller.reconnect_phase == "ready_disarmed"
            ):
                return
            if self.controller.reconnect_phase == "blocked":
                reason = self.controller.reconnect_last_error or self.controller.safety.fault or "config rejected"
                raise RuntimeError(f"ESP32 rejected settings: {reason}")
            time.sleep(0.01)
        raise RuntimeError("ESP32 CONFIG acknowledgement timed out")

    def _restore_previous_settings(self, vehicle_config: dict, controller_mapping: dict) -> None:
        self.controller.config = vehicle_config
        self.controller.mapping = controller_mapping
        self.controller.transition = self.controller._build_transition_controller()
        self._set_input_mapping(controller_mapping)
        self.controller.last_motion_request = (0.0, 0.0, 0.0)
        self.controller.last_drive_command = None
        self.controller.safety.disarm("live settings apply failed")
        self.controller.reconnect_require_arm_release = True
        if self.controller.reconnect_phase == "blocked" or self.controller.serial is None:
            self.controller.reconnect_attempts = 0
            self.controller._schedule_reconnect_retry(
                self.controller._now_ms(),
                "restoring previous settings after live apply failure",
            )
            return
        self.controller.safety.apply_config()
        self.controller.reconnect_phase = "config_pending"
        self.controller.reconnect_deadline_ms = (
            self.controller._now_ms() + self.controller.reconnect_handshake_timeout_ms
        )
        if self.controller._write_serial_message(disarm_message()):
            self.controller._write_serial_message(self.controller.config)

    def _set_input_mapping(self, mapping: dict) -> None:
        if self.controller_input is not None and hasattr(self.controller_input, "mapping"):
            self.controller_input.mapping = mapping

    def select_robot(self, robot_id: RobotId) -> FleetDashboardSnapshot:
        """Keep the real output view locked to the physically bound R2."""
        self._require_started()
        if not isinstance(robot_id, RobotId):
            raise ValueError("robot_id must be a RobotId")
        self._selected_robot = self.robot_id
        return self.snapshot()

    def snapshot(self) -> FleetDashboardSnapshot:
        """Build the latest immutable R1/R2 view without sending output."""
        self._require_started()
        now_ms = self.controller._now_ms()
        bound = build_robot_dashboard_snapshot(
            self.controller,
            self.robot_id,
            now_ms=now_ms,
            node_requirements=self.node_requirements,
        )
        self._last_snapshot = build_fleet_dashboard_snapshot(
            self._selected_robot,
            (bound,),
            now_ms=now_ms,
        )
        return self._last_snapshot

    def close(self) -> None:
        """Idempotently command zero, DISARM, and close the sole transport."""
        if self._closed:
            return
        serial = self.controller.serial
        self.controller.last_motion_request = (0.0, 0.0, 0.0)
        if serial is not None:
            try:
                if self.controller.safety.armed:
                    self.controller._send_zero_drive(armed=True)
            except (OSError, RuntimeError, ValueError) as exc:
                print(f"R2 dashboard shutdown zero command failed: {exc}", file=sys.stderr, flush=True)
            self.controller.safety.disarm("R2 dashboard closed")
            try:
                serial.write(encode_message(disarm_message()))
            except (OSError, RuntimeError) as exc:
                print(f"R2 dashboard shutdown DISARM failed: {exc}", file=sys.stderr, flush=True)
            try:
                serial.close()
            except (OSError, RuntimeError) as exc:
                print(f"R2 dashboard transport close failed: {exc}", file=sys.stderr, flush=True)
        else:
            self.controller.safety.disarm("R2 dashboard closed")
        if self._pid_written:
            self.controller._remove_pid_file()
            self._pid_written = False
        self._closed = True

    def _begin_safe_handshake(self) -> None:
        self.controller.reconnect_phase = "hello_pending"
        self.controller.reconnect_next_attempt_ms = None
        self.controller.reconnect_deadline_ms = (
            self.controller._now_ms() + self.controller.reconnect_handshake_timeout_ms
        )
        if self.controller._write_serial_message(disarm_message()):
            self.controller._write_serial_message(hello_message())

    def _apply_first_motion_clamp(self) -> None:
        motion = self.controller.config.get("motion")
        if not isinstance(motion, dict):
            raise ValueError("motion config must be an object")
        motion["open_loop_max_pwm"] = min(
            self.max_pwm,
            max(0, int(motion.get("open_loop_max_pwm", self.max_pwm))),
        )
        motion["pivot_max_pwm"] = min(
            self.max_pwm,
            max(0, int(motion.get("pivot_max_pwm", self.max_pwm))),
        )

    def _mark_ready_disarmed(self) -> None:
        if (
            self.controller.serial is not None
            and self.controller.safety.config_accepted
            and self.controller.safety.state == SafetyState.SAFE
            and not self.controller.safety.armed
            and self.controller.reconnect_phase == "ready"
        ):
            self.controller.reconnect_phase = "ready_disarmed"

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("R2 dashboard runtime is closed")

    def _require_started(self) -> None:
        self._require_open()
        if not self._started:
            raise RuntimeError("R2 dashboard runtime is not started")
