"""Runtime application orchestration."""

from __future__ import annotations

import argparse
import os
import sys
import time
from math import copysign, hypot, isfinite
from pathlib import Path
from typing import Any, Callable

from .config_manager import ensure_config_files, validate_vehicle_config
from .controller_input import (
    ControllerState,
    PygameController,
    list_controllers,
    transform_for_logical_front,
)
from .kinematics import calculate_wheel_vectors, max_wheel_speed_mps, wheel_speed_mps_to_rpm
from .node_inventory import evaluate_node_inventory, format_node_inventory, load_node_manifest
from .protocol import ProtocolError, arm_message, disarm_message, drive_message, encode_message, hello_message
from .safety import SafetyMonitor, SafetyState
from .serial_discovery import (
    AmbiguousSerialNodeError,
    discover_serial_nodes,
    format_probe_summary,
    open_discovered_serial_link,
)
from .serial_link import SerialLink
from .simulator import SimulatedEsp32
from .virtual_serial import VirtualSerialLink
from .steering_optimizer import (
    OptimizerSettings,
    ServoLimit,
    SteeringTransitionController,
    TransitionState,
    apply_wheel_direction_inversions,
    apply_open_loop_static_compensation,
    optimize_coordinated_four_ws,
    optimize_pure_translation,
    optimize_pivot_rotation,
    optimize_wheel,
    translation_angle_and_magnitude,
)

PID_FILE = Path(".codex_work") / "pc_controller.pid"


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def _sim_armable_config(config: dict[str, Any]) -> dict[str, Any]:
    sim = dict(config)
    sim["motion"] = dict(config.get("motion", {}))
    sim["motion"].update(
        {
            "wheelbase_m": sim["motion"].get("wheelbase_m") or 0.327,
            "track_width_m": sim["motion"].get("track_width_m") or 0.327,
            "wheel_diameter_m": sim["motion"].get("wheel_diameter_m") or 0.055,
            "max_wheel_rpm": sim["motion"].get("max_wheel_rpm") or 520.0,
            "max_linear_speed_mps": sim["motion"].get("max_linear_speed_mps") or 1.5,
            "max_angular_speed_radps": sim["motion"].get("max_angular_speed_radps") or 4.0,
        }
    )
    sim["servos"] = [dict(item, calibrated=True) for item in config.get("servos", [])]
    return sim


class ControllerApp:
    """Main PC-side controller app."""

    def __init__(self, args: argparse.Namespace, *, now_ms: Callable[[], int] | None = None) -> None:
        self.args = args
        self._clock_ms = now_ms or _monotonic_ms
        self.config, self.mapping = ensure_config_files(Path(args.config_dir))
        if args.simulate:
            self.config = _sim_armable_config(self.config)
        self.safety = SafetyMonitor()
        self.seq = int(time.time() * 1000) % 2_000_000_000
        self.last_angles = [0.0, 0.0, 0.0, 0.0]
        self.previous_speed_signs = [1, 1, 1, 1]
        self.previous_representation: str | None = None
        self.last_telemetry: dict[str, Any] | None = None
        # Read-only GUI/diagnostic state.  The GUI must observe commands that
        # passed through ControllerApp; it must never invent or send a parallel
        # transport command path.
        self.last_motion_request = (0.0, 0.0, 0.0)
        self.last_drive_command: dict[str, Any] | None = None
        self.sim = SimulatedEsp32(clock_ms=self._clock_ms) if args.simulate else None
        self.fake_device = (
            SimulatedEsp32(clock_ms=self._clock_ms) if bool(getattr(args, "fake_esp32", False)) else None
        )
        self.serial: SerialLink | VirtualSerialLink | None = (
            VirtualSerialLink(
                self.fake_device,
                trace=bool(getattr(args, "fake_trace", False)),
                now_ms=self._clock_ms,
            )
            if self.fake_device is not None
            else None
        )
        self.controller: PygameController | None = None
        self.controller_error: str | None = None
        self.arm_pressed_since_ms: int | None = None
        self.last_status_ms = 0
        self.last_rpm_monitor_ms = 0
        self.last_connected = False
        self.last_fault_text: str | None = None
        self.last_fault_event: dict[str, Any] | None = None
        self.last_serial_error_text: str | None = None
        self.recent_serial_lines: list[str] = []
        self.last_button_status: tuple[bool, bool] | None = None
        self.node_identity: dict[str, Any] | None = None
        self.auto_reconnect = bool(getattr(args, "auto_reconnect", True)) and not bool(args.simulate)
        self.reconnect_interval_ms = max(
            100,
            int(float(getattr(args, "reconnect_interval", 1.0)) * 1000),
        )
        self.reconnect_handshake_timeout_ms = max(
            100,
            int(float(getattr(args, "reconnect_handshake_timeout", 2.0)) * 1000),
        )
        self.reconnect_active = self.auto_reconnect and self.serial is not None
        self.reconnect_phase = "ready" if self.serial is not None else "idle"
        self.reconnect_next_attempt_ms: int | None = None
        self.reconnect_deadline_ms: int | None = None
        self.reconnect_attempts = 0
        self.reconnect_last_error: str | None = None
        self.reconnect_require_arm_release = False
        self.reconnect_expected_node_id = str(getattr(args, "node_id", "") or "") or None
        self.reconnect_expected_role = str(getattr(args, "node_role", "drive"))
        if self.fake_device is not None:
            self.node_identity = self.fake_device.node_identity()
            self.reconnect_expected_node_id = self.fake_device.node_id
        self.transition = self._build_transition_controller()

    def start(self) -> None:
        """Run the app loop."""
        validate_vehicle_config(self.config, require_armable=False)
        self._write_pid_file()
        try:
            self._print_startup_status()
            self.safety.apply_config()
            if not self.args.simulate and self.fake_device is None:
                try:
                    self._open_initial_serial_transport()
                except AmbiguousSerialNodeError:
                    # Multiple candidates require explicit operator selection.
                    # Retrying could later select whichever duplicate happens
                    # to remain visible, which violates fail-closed identity.
                    raise
                except RuntimeError as exc:
                    if not self._resident_startup_retry_enabled():
                        raise
                    self._schedule_startup_retry(exc)
            if not self.args.simulate and bool(self.args.joystick) and not self.args.once:
                print("opening controller input", flush=True)
                try:
                    self.controller = PygameController(self.mapping)
                except RuntimeError as exc:
                    self.controller_error = str(exc)
                else:
                    if self.controller.joystick is not None:
                        print(f"controller opened: {self.controller.joystick.get_name()}", flush=True)
                    else:
                        print("controller not detected at startup", flush=True)
            if self.serial:
                self._write_serial_message(hello_message())
                self._write_serial_message(self.config)
            if self.args.simulate:
                validate_vehicle_config(self.config, require_armable=True)
                self.safety.arm(self._now_ms())
            self._run_loop()
        finally:
            if self.serial:
                try:
                    self.serial.write(encode_message(disarm_message()))
                except Exception as exc:  # pragma: no cover - shutdown best effort
                    print(f"serial disarm during shutdown failed: {exc}", file=sys.stderr, flush=True)
                try:
                    self.serial.close()
                except Exception as exc:  # pragma: no cover - shutdown best effort
                    print(f"serial close during shutdown failed: {exc}", file=sys.stderr, flush=True)
            self._remove_pid_file()

    def _open_initial_serial_transport(self) -> None:
        """Open the configured physical transport for the first time."""
        if self.args.port:
            print(f"opening serial: {self.args.port}", flush=True)
            self.serial = SerialLink(self.args.port)
            print(f"serial opened: {self.serial.port}", flush=True)
        else:
            print(
                f"discovering serial node: role={self.args.node_role}"
                + (f" node_id={self.args.node_id}" if self.args.node_id else ""),
                flush=True,
            )
            probe = open_discovered_serial_link(
                role=self.args.node_role,
                node_id=self.args.node_id,
                timeout=self.args.discovery_timeout,
            )
            if probe.link is None:
                raise RuntimeError("serial discovery returned no open link")
            self.serial = probe.link
            self.node_identity = probe.identity
            print(f"serial opened: {self._describe_serial_node()}", flush=True)
        self._pin_reconnect_identity(self.node_identity)
        self.reconnect_active = self.auto_reconnect and self.serial is not None
        self.reconnect_phase = "ready" if self.serial is not None else "idle"

    def _resident_startup_retry_enabled(self) -> bool:
        """Return whether an unbounded run may remain resident while disconnected."""
        return (
            self.auto_reconnect
            and not bool(getattr(self.args, "once", False))
            and getattr(self.args, "duration", None) is None
        )

    def _schedule_startup_retry(self, error: RuntimeError) -> None:
        """Enter SAFE resident retry after a retryable initial open failure."""
        now_ms = self._now_ms()
        detail = f"initial serial connection failed: {error}"
        self.safety.disarm("serial unavailable at startup")
        self.arm_pressed_since_ms = None
        self.reconnect_require_arm_release = True
        self.transition.reset(now_ms)
        self.reconnect_attempts = 0
        self._schedule_reconnect_retry(now_ms, detail)
        print(
            f"{detail}; remaining SAFE and retrying in {self.reconnect_interval_ms / 1000:g} seconds",
            file=sys.stderr,
            flush=True,
        )

    def _write_pid_file(self) -> None:
        try:
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(str(os.getpid()), encoding="ascii")
        except OSError:
            pass

    def _remove_pid_file(self) -> None:
        try:
            if PID_FILE.exists() and PID_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except OSError:
            pass

    def _now_ms(self) -> int:
        return self._clock_ms()

    def _run_loop(self) -> None:
        period = 1.0 / 50.0
        started = time.monotonic()
        next_tick = time.monotonic()
        while True:
            now = time.monotonic()
            if self.args.duration is not None and now - started >= self.args.duration:
                print("duration reached, stopping", flush=True)
                break
            if now < next_tick:
                time.sleep(min(0.005, next_tick - now))
                continue
            next_tick = now + period
            if self.controller is not None:
                self.tick_controller(self.controller.read())
            else:
                self.tick(0.0, 0.0, 0.0)
            if self.args.once:
                break

    def _print_startup_status(self) -> None:
        if self.args.simulate:
            mode = "simulate (direct)"
        elif self.fake_device is not None:
            mode = f"fake ESP32 over {self.serial.port if self.serial else 'virtual serial'}"
        else:
            mode = f"serial {self.args.port or 'auto-discovery'}"
        print(f"pc_controller started: {mode}", flush=True)
        self._print_speed_settings()
        if self.args.once:
            print("once mode: send hello/config and exit after one tick", flush=True)
            return
        if self.args.duration is not None:
            print(f"duration mode: stop after {self.args.duration:g} seconds", flush=True)
        if self.args.rpm_monitor:
            print(
                f"rpm monitor: {float(self.args.rpm_monitor_hz):g} Hz, "
                "prints encoder wheel_rpm, pwm, and servo while running",
                flush=True,
            )
        if not self.args.joystick:
            print("joystick disabled: sending zero input only. Stop with Ctrl+C.", flush=True)
            return
        print("waiting: hold L1 + R1 + X for about 1 second to ARM. OPTIONS sends SAFE. Stop with Ctrl+C.", flush=True)

    def _print_speed_settings(self) -> None:
        motion = self.config.get("motion", {}) if isinstance(self.config.get("motion", {}), dict) else {}
        logical_front = str(self.mapping.get("logical_front", "FRONT")).strip().upper()
        if self.config.get("pid_enabled"):
            print(
                "speed config: control=rpm "
                f"pid_max_target_rpm={float(motion.get('pid_max_target_rpm', 0.0)):g} "
                f"pid_pivot_max_target_rpm={float(motion.get('pid_pivot_max_target_rpm', 0.0)):g} "
                f"logical_front={logical_front}",
                flush=True,
            )
            return
        open_loop_limit = self._pwm_limit(motion, "open_loop_max_pwm", 120)
        pivot_limit = self._pwm_limit(motion, "pivot_max_pwm", open_loop_limit)
        linear_scale = self._mapping_scale("linear_scale", 0.12)
        angular_scale = self._mapping_scale("angular_scale", 0.35)
        translation_deadzone = self._translation_deadzone_mps(motion)
        print(
            "speed config: control=pwm "
            f"full_forward_pwm={open_loop_limit} full_pivot_pwm={pivot_limit} "
            f"linear_scale={linear_scale:g} angular_scale={angular_scale:g} "
            f"translation_deadzone_mps={translation_deadzone:g} "
            f"logical_front={logical_front}",
            flush=True,
        )

    def _describe_serial_node(self) -> str:
        if not self.serial:
            return "not connected"
        if not self.node_identity:
            return self.serial.port
        identity = self.node_identity
        return (
            f"{self.serial.port} node_id={identity.get('node_id', '?')} "
            f"role={identity.get('role', '?')} board={identity.get('board', '?')} "
            f"firmware={identity.get('firmware', '?')}"
        )

    def _pin_reconnect_identity(self, identity: dict[str, Any] | None) -> None:
        """Remember a discovered node so reconnect cannot switch controllers."""
        if not identity:
            return
        node_id = str(identity.get("node_id", ""))
        role = str(identity.get("role", ""))
        if node_id:
            self.reconnect_expected_node_id = node_id
        if role:
            self.reconnect_expected_role = role

    def _identity_mismatch_reason(self, identity: dict[str, Any]) -> str | None:
        node_id = str(identity.get("node_id", ""))
        role = str(identity.get("role", ""))
        if self.reconnect_expected_node_id and node_id and node_id != self.reconnect_expected_node_id:
            return (
                "reconnect node mismatch: "
                f"expected {self.reconnect_expected_node_id}, got {node_id}"
            )
        if self.reconnect_expected_role and role and role != self.reconnect_expected_role:
            return (
                "reconnect role mismatch: "
                f"expected {self.reconnect_expected_role}, got {role}"
            )
        return None

    def _close_serial(self) -> None:
        if not self.serial:
            return
        try:
            self.serial.close()
        except Exception:
            pass
        self.serial = None

    def _schedule_reconnect_retry(self, now_ms: int, reason: str) -> None:
        """Close the failed link and schedule a bounded, non-busy retry."""
        self._close_serial()
        self.reconnect_last_error = reason
        self.reconnect_deadline_ms = None
        if not self.auto_reconnect:
            self.reconnect_phase = "idle"
            self.reconnect_next_attempt_ms = None
            return
        self.reconnect_active = True
        self.reconnect_phase = "waiting"
        exponent = min(max(self.reconnect_attempts - 1, 0), 4)
        self.reconnect_next_attempt_ms = now_ms + self.reconnect_interval_ms * (2**exponent)

    def _handle_transport_failure(self, reason: str, detail: str) -> None:
        """Fail SAFE immediately and begin rediscovery after a quiet interval."""
        now_ms = self._now_ms()
        was_handshaking = self.reconnect_phase in {"hello_pending", "config_pending"}
        self.safety.disarm(reason)
        self.arm_pressed_since_ms = None
        self.reconnect_require_arm_release = True
        self.transition.reset(now_ms)
        if not was_handshaking:
            self.reconnect_attempts = 0
        self._schedule_reconnect_retry(now_ms, detail)

    def _block_reconnect(self, reason: str) -> None:
        """Stop automatic retries when a connected node fails a safety check."""
        self.safety.disarm(reason)
        self.transition.reset(self._now_ms())
        self._close_serial()
        self.reconnect_phase = "blocked"
        self.reconnect_next_attempt_ms = None
        self.reconnect_deadline_ms = None
        self.reconnect_last_error = reason
        print(f"automatic serial reconnect blocked: {reason}", file=sys.stderr, flush=True)

    def _open_reconnect_transport(
        self,
    ) -> tuple[SerialLink | VirtualSerialLink, dict[str, Any] | None]:
        """Open the configured transport without weakening node selection."""
        if self.fake_device is not None:
            self.fake_device.reconnect(self._now_ms())
            return (
                VirtualSerialLink(
                    self.fake_device,
                    trace=bool(getattr(self.args, "fake_trace", False)),
                    now_ms=self._clock_ms,
                    reconnect=True,
                ),
                self.fake_device.node_identity(),
            )

        port = getattr(self.args, "port", None)
        if port:
            return SerialLink(port), None

        probe = open_discovered_serial_link(
            role=self.reconnect_expected_role,
            node_id=self.reconnect_expected_node_id,
            timeout=float(getattr(self.args, "discovery_timeout", 1.2)),
        )
        if probe.link is None:
            raise RuntimeError("serial discovery returned no open link")
        return probe.link, probe.identity

    def _service_serial_connection(self, now_ms: int) -> None:
        """Advance automatic reconnect and re-handshake without auto-arming."""
        if not self.reconnect_active or not self.auto_reconnect:
            return
        if self.reconnect_phase == "blocked":
            return
        if self.serial is not None:
            if (
                self.reconnect_phase in {"hello_pending", "config_pending"}
                and self.reconnect_deadline_ms is not None
                and now_ms >= self.reconnect_deadline_ms
            ):
                self._schedule_reconnect_retry(now_ms, "reconnect handshake timeout")
            return
        if self.reconnect_next_attempt_ms is None or now_ms < self.reconnect_next_attempt_ms:
            return

        self.reconnect_attempts += 1
        try:
            link, identity = self._open_reconnect_transport()
        except AmbiguousSerialNodeError as exc:
            self._block_reconnect(str(exc))
            return
        except Exception as exc:
            detail = f"serial reconnect attempt {self.reconnect_attempts} failed: {exc}"
            if detail != self.last_serial_error_text:
                print(detail, file=sys.stderr, flush=True)
                self.last_serial_error_text = detail
            self._schedule_reconnect_retry(now_ms, detail)
            return

        mismatch = self._identity_mismatch_reason(identity or {})
        if mismatch:
            self.serial = link
            self._block_reconnect(mismatch)
            return
        if identity and not bool(identity.get("pca9685_ok", True)):
            self.serial = link
            self._block_reconnect("ESP32 reports PCA9685 not ready")
            return

        self.serial = link
        if identity:
            self.node_identity = identity
            self._pin_reconnect_identity(identity)
        self.safety.apply_config(preserve_fault=True)
        self.transition.reset(now_ms)
        self.reconnect_phase = "hello_pending"
        self.reconnect_next_attempt_ms = None
        self.reconnect_deadline_ms = now_ms + self.reconnect_handshake_timeout_ms
        print(f"serial reconnected: {self._describe_serial_node()}; re-handshaking", flush=True)
        if not self._write_serial_message(disarm_message()):
            return
        self._write_serial_message(hello_message())

    def _handle_reconnect_identity(self, message: dict[str, Any], now_ms: int) -> bool:
        """Validate HELLO identity and send config while remaining SAFE."""
        mismatch = self._identity_mismatch_reason(message)
        if mismatch:
            self._block_reconnect(mismatch)
            return False
        if not bool(message.get("pca9685_ok", True)):
            self._block_reconnect("ESP32 reports PCA9685 not ready")
            return False
        self.node_identity = dict(message)
        self._pin_reconnect_identity(message)
        self.safety.apply_config(preserve_fault=True)
        self.reconnect_phase = "config_pending"
        self.reconnect_deadline_ms = now_ms + self.reconnect_handshake_timeout_ms
        return self._write_serial_message(self.config)

    def _complete_reconnect(self) -> None:
        self.reconnect_phase = "ready_disarmed"
        self.reconnect_next_attempt_ms = None
        self.reconnect_deadline_ms = None
        self.reconnect_attempts = 0
        self.reconnect_last_error = None
        print("serial re-handshake complete: READY_DISARMED until explicit ARM", flush=True)

    def tick_controller(self, state: ControllerState) -> None:
        """Apply joystick state to explicit ARM/DISARM and 50 Hz drive output."""
        now_ms = self._now_ms()
        self._service_serial_connection(now_ms)
        self._print_button_status(state)
        self._print_runtime_status(state, now_ms)
        self._print_rpm_monitor(state, now_ms)
        if not state.connected:
            if self.safety.armed:
                self._send_zero_drive(armed=True)
            if self.safety.state != SafetyState.SAFE:
                self._send_disarm("controller disconnected")
            self._read_serial_messages()
            return

        if state.safe_pressed:
            self._send_zero_drive(armed=self.safety.armed)
            self._send_disarm("safe button")
            print("SAFE requested by controller", flush=True)
            self._read_serial_messages()
            return

        if self.reconnect_require_arm_release:
            self.arm_pressed_since_ms = None
            if state.arm_pressed:
                self._read_serial_messages()
                return
            self.reconnect_require_arm_release = False

        if not self.safety.armed:
            if state.arm_pressed:
                if self.arm_pressed_since_ms is None:
                    self.arm_pressed_since_ms = now_ms
                hold_ms = int(float(self.mapping.get("arm_hold_seconds", 1.0)) * 1000)
                if now_ms - self.arm_pressed_since_ms >= hold_ms:
                    try:
                        validate_vehicle_config(self.config, require_armable=True)
                    except ValueError as exc:
                        self.safety.disarm(str(exc))
                        self._read_serial_messages()
                        return
                    if self.serial:
                        self._read_serial_messages()
                        if not self.safety.config_accepted:
                            self.safety.disarm("waiting for config_ack")
                            return
                        if self._write_serial_message(arm_message("normal")):
                            self.safety.request_arm(now_ms)
                            print("ARM requested: waiting for ESP32 arm_ack", flush=True)
                    elif self.args.simulate:
                        self.safety.arm(now_ms)
                    else:
                        self.arm_pressed_since_ms = None
                        self.safety.disarm("serial unavailable")
            else:
                self.arm_pressed_since_ms = None
            self._read_serial_messages()
            return

        motion = self.config.get("motion", {})
        max_linear = float(motion.get("max_linear_speed_mps", 0.0)) if isinstance(motion, dict) else 0.0
        max_angular = float(motion.get("max_angular_speed_radps", 0.0)) if isinstance(motion, dict) else 0.0
        linear_scale = max(0.0, min(1.0, float(self.mapping.get("linear_scale", 0.12))))
        angular_scale = max(0.0, min(1.0, float(self.mapping.get("angular_scale", 0.20))))
        try:
            machine_vx, machine_vy = transform_for_logical_front(
                state.vx,
                state.vy,
                self.mapping.get("logical_front", "FRONT"),
            )
        except ValueError as exc:
            self._send_zero_drive(armed=self.safety.armed)
            self._send_disarm(str(exc))
            self._read_serial_messages()
            return
        self.tick(
            machine_vx * max_linear * linear_scale,
            machine_vy * max_linear * linear_scale,
            state.omega * max_angular * angular_scale,
            steer_input=state.omega,
        )

    def _print_runtime_status(self, state: ControllerState, now_ms: int) -> None:
        if state.connected != self.last_connected:
            if state.connected:
                print(f"controller connected: {state.name}", flush=True)
            else:
                print("controller disconnected or not detected", flush=True)
            self.last_connected = state.connected
            self.last_status_ms = now_ms
            return
        if now_ms - self.last_status_ms < 2000:
            return
        self.last_status_ms = now_ms
        telemetry_state = ""
        if isinstance(self.last_telemetry, dict):
            state_text = self.last_telemetry.get("state")
            fault = self.last_telemetry.get("fault_flags")
            motor_pwm = self.last_telemetry.get("motor_pwm")
            wheel_rpm = self.last_telemetry.get("wheel_rpm")
            servo_deg = self.last_telemetry.get("servo_deg")
            if state_text is not None:
                telemetry_state = f" esp32={state_text}"
            if fault not in (None, 0):
                telemetry_state += f" fault_flags={fault}"
            if isinstance(motor_pwm, list) and len(motor_pwm) == 4:
                telemetry_state += f" pwm={motor_pwm}"
            if isinstance(wheel_rpm, list) and len(wheel_rpm) == 4:
                telemetry_state += f" rpm={[round(float(value), 1) for value in wheel_rpm]}"
            if isinstance(servo_deg, list) and len(servo_deg) == 4:
                telemetry_state += f" servo={servo_deg}"
        if not state.connected:
            print("status: waiting for controller. Run .\\run-pc-controller.cmd --list-controllers to check Windows input.", flush=True)
            return
        if self.safety.armed:
            print(
                f"status: ARMED vx={state.vx:.2f} vy={state.vy:.2f} omega={state.omega:.2f}{telemetry_state}",
                flush=True,
            )
        elif state.arm_pressed:
            print(f"status: ARM buttons held{telemetry_state}", flush=True)
        else:
            print(f"status: SAFE. hold L1 + R1 + X to ARM{telemetry_state}", flush=True)

    def _print_rpm_monitor(self, state: ControllerState, now_ms: int) -> None:
        if not bool(getattr(self.args, "rpm_monitor", False)):
            return
        hz = max(0.2, float(getattr(self.args, "rpm_monitor_hz", 5.0)))
        interval_ms = int(1000.0 / hz)
        if now_ms - self.last_rpm_monitor_ms < interval_ms:
            return
        self.last_rpm_monitor_ms = now_ms

        telemetry = self.last_telemetry if isinstance(self.last_telemetry, dict) else {}
        wheel_rpm = telemetry.get("wheel_rpm")
        motor_pwm = telemetry.get("motor_pwm")
        servo_deg = telemetry.get("servo_deg")
        if not (isinstance(wheel_rpm, list) and len(wheel_rpm) == 4):
            return

        rpm = [float(value) for value in wheel_rpm]
        avg_abs = sum(abs(value) for value in rpm) / 4.0
        max_abs = max(abs(value) for value in rpm)
        left_abs = (abs(rpm[0]) + abs(rpm[2])) / 2.0
        right_abs = (abs(rpm[1]) + abs(rpm[3])) / 2.0
        pwm_text = motor_pwm if isinstance(motor_pwm, list) and len(motor_pwm) == 4 else ["?", "?", "?", "?"]
        servo_text = (
            [round(float(value), 1) for value in servo_deg]
            if isinstance(servo_deg, list) and len(servo_deg) == 4
            else ["?", "?", "?", "?"]
        )
        print(
            "rpm: "
            f"in(vx={state.vx:+.2f} vy={state.vy:+.2f} om={state.omega:+.2f}) "
            f"wheel={[round(value, 1) for value in rpm]} "
            f"avg={avg_abs:.1f} max={max_abs:.1f} L/R={left_abs:.1f}/{right_abs:.1f} "
            f"pwm={pwm_text} servo={servo_text}",
            flush=True,
        )

    def _print_button_status(self, state: ControllerState) -> None:
        status = (state.arm_pressed, state.safe_pressed)
        if status == self.last_button_status:
            return
        self.last_button_status = status
        if state.arm_pressed:
            print("input: ARM combo detected", flush=True)
        elif state.safe_pressed:
            print("input: SAFE button detected", flush=True)

    def tick(self, vx: float, vy: float, omega: float, steer_input: float | None = None) -> None:
        """Run one control tick."""
        self.last_motion_request = (float(vx), float(vy), float(omega))
        now_ms = self._now_ms()
        self._service_serial_connection(now_ms)
        timeout_action = self.safety.update_timeout(now_ms)
        if timeout_action == "stop":
            self._send_zero_drive(armed=True)
            self._read_serial_messages()
            return
        elif timeout_action == "safe":
            self._send_zero_drive(armed=False)
            self._send_disarm()
            if self.serial is not None and self.safety.fault == "telemetry timeout":
                self._handle_transport_failure(
                    "telemetry timeout",
                    "serial liveness lost after telemetry timeout",
                )

        if self.safety.state != SafetyState.NORMAL:
            self._read_serial_messages()
            return

        if not self._motion_config_ready():
            self._send_zero_drive(armed=self.safety.armed)
            self._send_disarm("vehicle dimensions unset")
            self._read_serial_messages()
            return

        motion = self.config.get("motion", {}) if isinstance(self.config.get("motion", {}), dict) else {}
        servo_limits = [
            ServoLimit(float(item["min_angle_deg"]), float(item["max_angle_deg"]), bool(item.get("calibrated", False)))
            for item in self.config["servos"]
        ]
        translation_deadzone = self._translation_deadzone_mps(motion)
        angle, magnitude = translation_angle_and_magnitude(vx, vy, translation_deadzone)
        current_angles = self._current_steering_angles()
        pure_rotation = magnitude < translation_deadzone and abs(omega) >= 0.05
        mixed_motion = angle is not None and abs(omega) >= 0.05
        mixed_omega_inverted = mixed_motion and bool(motion.get("mixed_omega_inverted", False))
        effective_omega = -omega if mixed_omega_inverted else omega
        mixed_mode = str(motion.get("mixed_steering_mode", "limited_arc")).lower()
        coordinated_mixed = mixed_motion and mixed_mode in {"coordinated_4ws", "coordinated", "v29"}
        arc_motion = (
            mixed_motion
            and not coordinated_mixed
            and self._is_limited_arc_motion(mixed_mode, vx, vy, effective_omega, translation_deadzone)
        )
        resolved_omega = self._limit_manual_arc_omega(vx, vy, effective_omega, motion) if arc_motion else effective_omega
        vectors = calculate_wheel_vectors(vx, vy, resolved_omega, self.config, current_angles)
        if pure_rotation:
            turn_speed = max((vector.speed_mps for vector in vectors), default=0.0)
            pivot_omega = resolved_omega * self._pivot_direction_sign(motion)
            pivot_mode = self._pivot_steering_mode(motion)
            if pivot_mode == "straight_tank":
                steer, speeds = self._straight_tank_pivot(turn_speed, pivot_omega)
            elif pivot_mode == "diagonal_parallel":
                steer, speeds = self._diagonal_parallel_pivot(turn_speed, pivot_omega, motion)
            else:
                steer, speeds = optimize_pivot_rotation(turn_speed, pivot_omega, current_angles, servo_limits)
            speeds = apply_wheel_direction_inversions(
                speeds,
                self.mapping.get("pivot_motor_direction_inverted", [False, False, False, False]),
            )
        elif angle is not None and abs(omega) < 0.05:
            optimized = optimize_pure_translation(
                angle,
                magnitude,
                current_angles,
                servo_limits,
                previous_representation=self.previous_representation,
                previous_speed_signs=self.previous_speed_signs,
                settings=self.transition.settings,
            )
            self._remember_group_representation(optimized)
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]
        elif coordinated_mixed:
            effective_steer_input = (
                -steer_input if mixed_omega_inverted and steer_input is not None else steer_input
            )
            resolved_steer_input = self._resolve_steer_input(effective_omega, effective_steer_input)
            optimized = optimize_coordinated_four_ws(
                angle,
                magnitude,
                resolved_steer_input,
                current_angles,
                servo_limits,
                previous_representation=self.previous_representation,
                previous_speed_signs=self.previous_speed_signs,
                settings=self.transition.settings,
                max_steer_deg=float(motion.get("coordinated_4ws_max_steer_deg", 45.0)),
                wheelbase_m=float(motion.get("wheelbase_m", 0.0)),
                track_width_m=float(motion.get("track_width_m", 0.0)),
                inner_outer_speed=bool(motion.get("coordinated_4ws_inner_outer_speed", False)),
                positive_steer_turns_right=bool(motion.get("coordinated_4ws_positive_steer_turns_right", True)),
            )
            self._remember_group_representation(optimized)
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]
        else:
            optimized = self._optimize_vector_wheels(vectors, servo_limits, prefer_direct=mixed_motion)
            steer = [item.angle_deg for item in optimized]
            speeds = [item.speed for item in optimized]

        if mixed_motion and not coordinated_mixed and bool(motion.get("limit_mixed_peak_to_translation", True)):
            peak_speed = max((abs(speed) for speed in speeds), default=0.0)
            if peak_speed > magnitude > 1e-9:
                scale = magnitude / peak_speed
                speeds = [speed * scale for speed in speeds]

        input_cancelled = max((abs(speed) for speed in speeds), default=0.0) < 1e-9
        if input_cancelled:
            self.transition.reset(now_ms)
        else:
            next_signs = [1 if speed >= 0.0 else -1 for speed in speeds]
            direction_switch = any(
                abs(speeds[index]) > 1e-9 and next_signs[index] != self.previous_speed_signs[index]
                for index in range(4)
            )
            transition = self.transition.update(now_ms, steer, current_angles, direction_switch)
            if transition.blocked_reason:
                self._send_zero_drive(armed=True)
                self._send_disarm(transition.blocked_reason)
                self._read_serial_messages()
                return
            if not transition.allow_drive:
                speeds = [0.0, 0.0, 0.0, 0.0]
            else:
                speed_scale = 1.0 if pure_rotation and transition.state == TransitionState.ACCELERATE else transition.speed_scale
                speeds = [speed * speed_scale for speed in speeds]

        self.last_angles = steer

        control = "rpm" if self.config.get("pid_enabled") else "pwm"
        if control == "rpm":
            targets = [wheel_speed_mps_to_rpm(speed, self.config) for speed in speeds]
            rpm_limit = self._pid_target_rpm_limit(pure_rotation)
            if rpm_limit > 0.0:
                targets = [max(-rpm_limit, min(rpm_limit, target)) for target in targets]
        else:
            targets = self._open_loop_pwm_targets(speeds, pure_rotation, motion)
        message = drive_message(self.seq, control, steer, targets, self.safety.armed)
        self.last_drive_command = dict(message)
        self.seq += 1
        if self.safety.armed:
            self.safety.record_drive(now_ms)
            self.previous_speed_signs = [1 if speed >= 0.0 else -1 for speed in speeds]
        if self.sim:
            self.last_telemetry = self.sim.apply_drive(message)
            seq_value = self.last_telemetry.get("seq") if isinstance(self.last_telemetry, dict) else None
            self.safety.record_telemetry(now_ms, seq=seq_value if isinstance(seq_value, int) else None)
        elif self.serial:
            self._write_serial_message(message)
            self._read_serial_messages()

    def _resolve_steer_input(self, omega: float, steer_input: float | None) -> float:
        if steer_input is not None:
            return max(-1.0, min(1.0, steer_input))
        motion = self.config.get("motion", {})
        max_angular = float(motion.get("max_angular_speed_radps", 0.0)) if isinstance(motion, dict) else 0.0
        angular_scale = max(0.0, min(1.0, float(self.mapping.get("angular_scale", 0.20))))
        divisor = max_angular * angular_scale
        if divisor <= 1e-9:
            return 0.0
        return max(-1.0, min(1.0, omega / divisor))

    def _pivot_steering_mode(self, motion: dict[str, Any]) -> str:
        mode = str(motion.get("pivot_steering_mode", "optimized")).lower()
        if mode in {"straight_tank", "tank", "straight", "no_x"}:
            return "straight_tank"
        if mode in {"diagonal_parallel", "parallel_x", "x_parallel", "pivot_x"}:
            return "diagonal_parallel"
        return "optimized"

    def _straight_tank_pivot(self, turn_speed: float, rotate_sign: float) -> tuple[list[float], list[float]]:
        if abs(turn_speed) < 1e-9 or abs(rotate_sign) < 1e-9:
            return [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]
        signed = (1.0 if rotate_sign > 0.0 else -1.0) * abs(turn_speed)
        return [0.0, 0.0, 0.0, 0.0], [-signed, signed, -signed, signed]

    def _pivot_direction_sign(self, motion: dict[str, Any]) -> float:
        return -1.0 if bool(motion.get("pivot_direction_inverted", False)) else 1.0

    def _diagonal_parallel_pivot(self, turn_speed: float, rotate_sign: float, motion: dict[str, Any]) -> tuple[list[float], list[float]]:
        if abs(turn_speed) < 1e-9 or abs(rotate_sign) < 1e-9:
            return [135.0, 45.0, -135.0, -45.0], [0.0, 0.0, 0.0, 0.0]
        signed = (1.0 if rotate_sign > 0.0 else -1.0) * abs(turn_speed)
        return [135.0, 45.0, -135.0, -45.0], [signed, signed, signed, signed]

    def _is_limited_arc_motion(self, mode: str, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if mode in {"forward_arc", "forward", "forward_only_arc", "ackermann"}:
            return self._is_forward_arc_motion(vx, vy, omega, translation_deadzone)
        if mode in {"arc", "manual_arc", "body_velocity_arc", "limited_arc", "translation_arc", "mixed_arc"}:
            return self._is_manual_arc_motion(vx, vy, omega, translation_deadzone)
        return False

    def _is_forward_arc_motion(self, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if abs(omega) < 0.05:
            return False
        lateral_limit = max(translation_deadzone, abs(vx) * 0.20)
        return abs(vx) >= translation_deadzone and abs(vy) <= lateral_limit

    def _is_manual_arc_motion(self, vx: float, vy: float, omega: float, translation_deadzone: float) -> bool:
        if abs(omega) < 0.05:
            return False
        forward_arc = self._is_forward_arc_motion(vx, vy, omega, translation_deadzone)
        forward_limit = max(translation_deadzone, abs(vy) * 0.20)
        strafe_arc = abs(vy) >= translation_deadzone and abs(vx) <= forward_limit
        return forward_arc or strafe_arc

    def _limit_manual_arc_omega(self, vx: float, vy: float, omega: float, motion: dict[str, Any]) -> float:
        translation_speed = max(abs(vx), abs(vy))
        if translation_speed < 1e-9 or abs(omega) < 1e-9:
            return omega
        wheelbase = float(motion.get("wheelbase_m", 0.0))
        track_width = float(motion.get("track_width_m", 0.0))
        configured = float(
            motion.get(
                "mixed_arc_min_radius_m",
                motion.get("manual_arc_min_radius_m", motion.get("forward_arc_min_radius_m", 0.0)),
            )
            or 0.0
        )
        min_radius = max(configured, wheelbase, track_width, 1e-6)
        max_omega = translation_speed / min_radius
        if abs(omega) <= max_omega:
            return omega
        return copysign(max_omega, omega)

    def _optimize_vector_wheels(
        self,
        vectors: list[Any],
        servo_limits: list[ServoLimit],
        *,
        prefer_direct: bool,
    ) -> list[Any]:
        if prefer_direct:
            direct = [
                optimize_wheel(
                    vectors[index].angle_deg,
                    vectors[index].speed_mps,
                    self.last_angles[index],
                    servo_limits[index],
                    previous_speed_sign=self.previous_speed_signs[index],
                    settings=self.transition.settings,
                    allow_reversed_drive=False,
                )
                for index in range(4)
            ]
            if all(getattr(command, "fault", None) is None for command in direct):
                return direct
        return [
            optimize_wheel(
                vectors[index].angle_deg,
                vectors[index].speed_mps,
                self.last_angles[index],
                servo_limits[index],
                previous_speed_sign=self.previous_speed_signs[index],
                settings=self.transition.settings,
            )
            for index in range(4)
        ]

    def _remember_group_representation(self, commands: list[Any]) -> None:
        representations = {getattr(command, "representation", None) for command in commands}
        if len(representations) == 1:
            representation = representations.pop()
            if representation in {"A", "B"}:
                self.previous_representation = str(representation)

    def _send_zero_drive(self, armed: bool) -> None:
        message = drive_message(self.seq, "pwm", list(self.last_angles), [0.0, 0.0, 0.0, 0.0], armed)
        self.last_motion_request = (0.0, 0.0, 0.0)
        self.last_drive_command = dict(message)
        self.seq += 1
        if self.sim:
            self.last_telemetry = self.sim.apply_drive(message)
            now_ms = self._now_ms()
            seq_value = self.last_telemetry.get("seq") if isinstance(self.last_telemetry, dict) else None
            self.safety.record_telemetry(now_ms, seq=seq_value if isinstance(seq_value, int) else None)
        elif self.serial:
            self._write_serial_message(message)
        self.previous_speed_signs = [1, 1, 1, 1]

    def _send_disarm(self, reason: str | None = None) -> None:
        if reason is not None:
            self.safety.disarm(reason)
        self.last_motion_request = (0.0, 0.0, 0.0)
        self.arm_pressed_since_ms = None
        self.transition.reset(self._now_ms())
        if self.serial:
            self._write_serial_message(disarm_message())

    def _write_serial_message(self, message: dict[str, Any]) -> bool:
        """Write one protocol message and fail SAFE on transport errors."""
        if not self.serial:
            return False
        try:
            self.serial.write(encode_message(message))
        except Exception as exc:
            text = f"serial write failed: {exc}"
            if text != self.last_serial_error_text:
                print(text, file=sys.stderr, flush=True)
                self.last_serial_error_text = text
            self._handle_transport_failure("serial write failed", text)
            return False
        return True

    def _read_serial_messages(self) -> None:
        """Read available serial messages without requiring NORMAL motion config."""
        if not self.serial:
            return
        from .protocol import decode_line

        try:
            lines = list(self.serial.read_lines())
        except Exception as exc:
            text = f"serial read failed: {exc}"
            if text != self.last_serial_error_text:
                print(text, file=sys.stderr, flush=True)
                self.last_serial_error_text = text
            self._handle_transport_failure("serial read failed", text)
            return

        for line in lines:
            self.recent_serial_lines.append(line)
            if len(self.recent_serial_lines) > 500:
                del self.recent_serial_lines[:-500]
            try:
                message = decode_line(line)
            except ProtocolError as exc:
                text = f"malformed serial message: {exc}"
                if text != self.last_serial_error_text:
                    print(text, file=sys.stderr, flush=True)
                    self.last_serial_error_text = text
                self.safety.disarm("malformed serial JSON")
                self._write_serial_message(disarm_message())
                continue
            now_ms = self._now_ms()
            message_type = message.get("type")
            if (
                getattr(self, "reconnect_phase", "idle") == "hello_pending"
                and message_type in {"hello_ack", "node_identity"}
            ):
                self._handle_reconnect_identity(message, now_ms)
                continue
            if message_type == "telemetry":
                seq_value = message.get("seq")
                seq = int(seq_value) if isinstance(seq_value, int) else None
                if not self.safety.record_telemetry(now_ms, seq=seq):
                    if self.safety.state == SafetyState.SAFE:
                        self._write_serial_message(disarm_message())
                    continue
                self.last_telemetry = message
                command_age_value = message.get("command_age_ms")
                command_age_ms = (
                    int(command_age_value)
                    if isinstance(command_age_value, (int, float))
                    and not isinstance(command_age_value, bool)
                    and isfinite(float(command_age_value))
                    and float(command_age_value) >= 0.0
                    else None
                )
                if self.safety.armed and command_age_ms is not None and command_age_ms >= 500:
                    self.safety.disarm("ESP32 command timeout")
                    self._write_serial_message(disarm_message())
                    self.transition.reset(now_ms)
                    continue
                esp_state = str(message.get("state", ""))
                esp_armed = bool(message.get("armed", False))
                if self.safety.armed and (not esp_armed or esp_state in {"SAFE", "BLOCKED"}):
                    self.safety.disarm(f"ESP32 reported {esp_state or 'not armed'}")
                    self.transition.reset(now_ms)
                continue
            self.safety.record_rx(now_ms)
            if message_type == "config_ack":
                if bool(message.get("ok", False)):
                    self.last_fault_event = None
                    self.safety.mark_config_accepted()
                    if getattr(self, "reconnect_phase", "idle") == "config_pending":
                        self._complete_reconnect()
                else:
                    reason = str(message.get("reason", "config rejected"))
                    if getattr(self, "reconnect_phase", "idle") == "config_pending":
                        self._block_reconnect(reason)
                    else:
                        self.safety.disarm(reason)
                continue
            if message_type in {"hello_ack", "node_identity"}:
                mismatch = self._identity_mismatch_reason(message)
                if mismatch:
                    self._block_reconnect(mismatch)
                    continue
                self.node_identity = dict(message)
                self._pin_reconnect_identity(message)
                if not bool(message.get("pca9685_ok", True)):
                    self.safety.disarm("ESP32 reports PCA9685 not ready")
                continue
            if message_type == "arm_ack":
                ok = bool(message.get("ok", False))
                armed = bool(message.get("armed", False))
                state = str(message.get("state", ""))
                if (
                    getattr(self, "reconnect_phase", "idle") in {"hello_pending", "config_pending"}
                    and ok
                    and not armed
                    and state == "SAFE"
                ):
                    # This is the expected acknowledgement to the fail-safe
                    # DISARM sent before HELLO. It is never an ARM decision.
                    continue
                if ok and armed and state in {"NORMAL", "DEBUG"}:
                    if self.safety.confirm_arm(now_ms, debug=state == "DEBUG"):
                        self.last_fault_event = None
                        print(f"ARM confirmed by ESP32: {state}", flush=True)
                    else:
                        # A late/stale ACK after a cancelled request must never
                        # re-arm the PC. Reassert DISARM without replacing the
                        # cancellation root cause.
                        self.safety.disarm("unexpected arm_ack")
                        self._write_serial_message(disarm_message())
                else:
                    self.safety.disarm(str(message.get("reason", "arm rejected")))
                    self.transition.reset(now_ms)
                continue
            if message_type == "fault":
                flags = message.get("fault_flags")
                reason = message.get("reason", "")
                self.last_fault_event = {
                    "timestamp_ms": now_ms,
                    "source": "ESP32",
                    "node_id": str((getattr(self, "node_identity", None) or {}).get("node_id", "")) or None,
                    "reason": str(reason or "ESP32 fault"),
                    "fault_flags": flags if isinstance(flags, int) and not isinstance(flags, bool) else None,
                }
                self.safety.disarm(str(reason or "ESP32 fault"))
                self._write_serial_message(disarm_message())
                self.transition.reset(now_ms)
                text = f"ESP32 fault: flags={flags} reason={reason}"
                if text != self.last_fault_text:
                    print(text, file=sys.stderr, flush=True)
                    self.last_fault_text = text

    def _current_steering_angles(self) -> list[float]:
        """Prefer ESP32 telemetry angles over the last command estimate."""
        telemetry = self.last_telemetry if isinstance(self.last_telemetry, dict) else {}
        servo_deg = telemetry.get("servo_deg")
        if isinstance(servo_deg, list) and len(servo_deg) == 4:
            try:
                return [float(value) for value in servo_deg]
            except (TypeError, ValueError):
                return list(self.last_angles)
        return list(self.last_angles)

    def _motion_config_ready(self) -> bool:
        """Return whether kinematics can be calculated safely."""
        motion = self.config.get("motion", {})
        if not isinstance(motion, dict):
            return False
        return (
            float(motion.get("wheelbase_m", 0.0)) > 0.0
            and float(motion.get("track_width_m", 0.0)) > 0.0
            and float(motion.get("wheel_diameter_m", 0.0)) > 0.0
            and float(motion.get("max_wheel_rpm", 0.0)) > 0.0
        )

    def _pid_target_rpm_limit(self, pure_rotation: bool) -> float:
        """Return the PC-side safety clamp for RPM target commands."""
        motion = self.config.get("motion", {})
        if not isinstance(motion, dict):
            return 0.0
        max_wheel_rpm = float(motion.get("max_wheel_rpm", 0.0))
        limit = float(motion.get("pid_max_target_rpm", max_wheel_rpm))
        if pure_rotation:
            pivot_limit = float(motion.get("pid_pivot_max_target_rpm", limit))
            if pivot_limit > 0.0:
                limit = min(limit, pivot_limit) if limit > 0.0 else pivot_limit
        if max_wheel_rpm > 0.0:
            limit = min(limit, max_wheel_rpm) if limit > 0.0 else max_wheel_rpm
        return max(0.0, limit)

    def _open_loop_pwm_targets(self, speeds: list[float], pure_rotation: bool, motion: dict[str, Any]) -> list[int]:
        """Map commanded wheel speeds to PWM with JSON values as full-stick limits."""
        full_scale_speed = self._open_loop_full_scale_speed_mps(motion, pure_rotation)
        if full_scale_speed <= 1e-9:
            full_scale_speed = max_wheel_speed_mps(self.config) or max((abs(speed) for speed in speeds), default=0.0) or 1.0

        open_loop_limit = self._pwm_limit(motion, "open_loop_max_pwm", 120)
        pwm_limit = open_loop_limit if open_loop_limit > 0 else 1023
        if pure_rotation:
            pivot_limit = self._pwm_limit(motion, "pivot_max_pwm", pwm_limit)
            if pivot_limit > 0:
                pwm_limit = pivot_limit

        targets = [int(pwm_limit * speed / full_scale_speed) for speed in speeds]
        if bool(motion.get("open_loop_static_compensation_enabled", False)):
            targets = apply_open_loop_static_compensation(targets, pwm_limit, self.config.get("motors", []))
        return [max(-pwm_limit, min(pwm_limit, target)) for target in targets]

    def _open_loop_full_scale_speed_mps(self, motion: dict[str, Any], pure_rotation: bool) -> float:
        """Return the wheel speed represented by a full stick in open-loop PWM mode."""
        configured_limit = max_wheel_speed_mps(self.config)
        if pure_rotation:
            wheelbase = float(motion.get("wheelbase_m", 0.0))
            track_width = float(motion.get("track_width_m", 0.0))
            max_angular = float(motion.get("max_angular_speed_radps", 0.0))
            radius = hypot(wheelbase / 2.0, track_width / 2.0)
            full_scale_speed = radius * max_angular * self._mapping_scale("angular_scale", 0.35)
        else:
            max_linear = float(motion.get("max_linear_speed_mps", 0.0))
            full_scale_speed = max_linear * self._mapping_scale("linear_scale", 0.12)
        if configured_limit > 0.0 and full_scale_speed > configured_limit:
            return configured_limit
        return full_scale_speed

    def _translation_deadzone_mps(self, motion: dict[str, Any]) -> float:
        """Return translation hold threshold in m/s.

        Values in translation_deadzone up to 1.0 are treated as a stick fraction,
        matching the controller deadzone convention used in the v29-derived config.
        """
        raw = max(0.0, float(motion.get("translation_deadzone", 0.12)))
        explicit = motion.get("translation_deadzone_mps")
        if explicit is not None:
            return max(0.0, float(explicit))
        if raw <= 1.0:
            max_linear = float(motion.get("max_linear_speed_mps", 0.0))
            full_scale_speed = max_linear * self._mapping_scale("linear_scale", 0.12)
            if full_scale_speed > 0.0:
                return raw * full_scale_speed
        return raw

    def _mapping_scale(self, key: str, default: float) -> float:
        return max(0.0, min(1.0, float(self.mapping.get(key, default))))

    def _pwm_limit(self, motion: dict[str, Any], key: str, default: int) -> int:
        return int(max(0.0, min(1023.0, float(motion.get(key, default)))))

    def _build_transition_controller(self) -> SteeringTransitionController:
        motion = self.config.get("motion", {})
        if not isinstance(motion, dict):
            motion = {}
        settings = OptimizerSettings(
            hysteresis_deg=float(motion.get("candidate_switch_hysteresis_deg", 20.0)),
            end_margin_deg=float(motion.get("servo_end_margin_deg", 10.0)),
            realign_threshold_deg=float(motion.get("realign_threshold_deg", 30.0)),
        )
        return SteeringTransitionController(
            settings=settings,
            decel_time_ms=int(motion.get("decel_time_ms", 200)),
            accel_time_ms=int(motion.get("accel_time_ms", 200)),
            settle_time_ms=int(motion.get("alignment_settle_time_ms", 100)),
            alignment_timeout_ms=int(motion.get("alignment_timeout_ms", 2000)),
        )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(description="MCB44 four wheel independent steering controller")
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--simulate", action="store_true", help="legacy direct simulator without serial/protocol transport")
    backend.add_argument("--fake-esp32", action="store_true", help="run against an in-memory ESP32 using the real NDJSON protocol path")
    parser.add_argument("--fake-trace", action="store_true", help="print virtual serial TX/RX while using --fake-esp32")
    parser.add_argument("--port", default=None, help="serial port, for example COM7. If omitted, auto-discover by node role")
    parser.add_argument("--node-role", default="drive", help="auto-discovery role to open when --port is omitted")
    parser.add_argument("--node-id", default=None, help="auto-discovery node_id to open when --port is omitted")
    parser.add_argument("--discovery-timeout", type=float, default=1.2, help="seconds to wait for each serial identity reply")
    parser.add_argument(
        "--no-auto-reconnect",
        dest="auto_reconnect",
        action="store_false",
        help="exit on startup failure and remain disconnected after a later serial transport failure",
    )
    parser.add_argument(
        "--reconnect-interval",
        type=float,
        default=1.0,
        help="initial seconds between automatic reconnect attempts (bounded exponential backoff)",
    )
    parser.add_argument(
        "--reconnect-handshake-timeout",
        type=float,
        default=2.0,
        help="seconds to wait for HELLO or config acknowledgement after reconnect",
    )
    parser.add_argument("--list-nodes", action="store_true", help="probe serial ports and print robot node identities")
    parser.add_argument(
        "--node-manifest",
        default=None,
        help="with --list-nodes, validate required/optional nodes from this JSON manifest",
    )
    parser.add_argument("--config-dir", default="config", help="configuration directory")
    parser.add_argument("--once", action="store_true", help="run one tick then exit")
    parser.add_argument("--duration", type=float, default=None, help="run for this many seconds then exit")
    parser.add_argument("--no-joystick", dest="joystick", action="store_false", help="do not read pygame joystick in serial or fake-ESP32 mode")
    parser.add_argument("--list-controllers", action="store_true", help="list pygame joystick devices and exit")
    parser.add_argument("--debug-controller", type=float, metavar="SECONDS", help="print raw controller axes/buttons for SECONDS and exit")
    parser.add_argument("--rpm-monitor", action="store_true", help="print encoder RPM telemetry while running")
    parser.add_argument("--rpm-monitor-hz", type=float, default=5.0, help="RPM monitor print rate")
    parser.set_defaults(joystick=True, auto_reconnect=True)
    return parser


def print_controller_list() -> None:
    """Print visible controller devices."""
    devices = list_controllers()
    print(f"controllers: {len(devices)}", flush=True)
    for device in devices:
        print(
            f"{device['index']}: {device['name']} "
            f"axes={device['axes']} buttons={device['buttons']} hats={device['hats']}",
            flush=True,
        )


def print_node_list(timeout: float = 1.2, manifest_path: str | None = None) -> None:
    """Print visible serial robot nodes."""
    probes = discover_serial_nodes(timeout=timeout)
    found = sum(1 for probe in probes if probe.identity)
    print(f"serial nodes: {found}", flush=True)
    print(format_probe_summary(probes), flush=True)
    if manifest_path is None:
        return
    try:
        requirements = load_node_manifest(manifest_path)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    report = evaluate_node_inventory(requirements, probes)
    print(format_node_inventory(report), flush=True)
    if not report.ready:
        raise RuntimeError("serial node inventory is BLOCKED")
