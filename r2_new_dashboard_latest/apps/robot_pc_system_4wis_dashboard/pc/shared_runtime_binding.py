"""Qt timer binding for a single-owner shared dashboard runtime."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from pc_controller.autonomy import RobotId
from pc_controller.gui_runtime import FakeFleetDashboardRuntime, RealFleetDashboardRuntime

SharedRuntime = FakeFleetDashboardRuntime | RealFleetDashboardRuntime


class QtFleetDashboardBinding(QObject):
    """Periodically inject one runtime's immutable snapshots into MainWindow."""

    failed = Signal(str)

    def __init__(
        self,
        host,
        runtime: SharedRuntime,
        *,
        interval_ms: int = 100,
    ) -> None:
        if not bool(getattr(host, "shared_runtime_only", False)):
            raise ValueError("shared runtime binding requires MainWindow(shared_runtime_only=True)")
        if interval_ms < 20 or interval_ms > 5000:
            raise ValueError("interval_ms must be between 20 and 5000")
        super().__init__(host)
        self.host = host
        self.runtime = runtime
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval_ms))
        self.timer.timeout.connect(self._tick)
        self.host.main_dashboard_widget.robot_selected.connect(self._select_robot)
        self.host.drive_diagnostic_widget.robot_selected.connect(self._select_robot)
        self.host.mechanism_diagnostic_widget.robot_selected.connect(self._select_robot)
        self.host.sensor_diagnostic_widget.robot_selected.connect(self._select_robot)
        self.host.calibration_diagnostic_widget.robot_selected.connect(self._select_robot)
        self.host.fault_history_widget.robot_selected.connect(self._select_robot)
        self.host.autonomy_widget.robot_selected.connect(self._select_robot)
        self.host.logs_widget.robot_selected.connect(self._select_robot)
        self.host.replay_widget.robot_selected.connect(self._select_robot)
        self._started = False
        self._closed = False

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("Qt fleet dashboard binding is closed")
        if self._started:
            return
        snapshot = self.runtime.start()
        self._publish(snapshot)
        self.timer.start()
        self._started = True

    def _tick(self) -> None:
        if not self._started or self._closed:
            return
        try:
            self._publish(self.runtime.tick())
        except Exception as exc:
            self.timer.stop()
            self.runtime.close()
            self._closed = True
            self.failed.emit(str(exc))

    def _select_robot(self, robot_id: str) -> None:
        if not self._started or self._closed:
            return
        try:
            snapshot = self.runtime.select_robot(RobotId(robot_id))
            self._publish(snapshot)
        except (ValueError, RuntimeError) as exc:
            self.timer.stop()
            self.runtime.close()
            self._closed = True
            self.failed.emit(str(exc))

    def close(self) -> None:
        if self._closed:
            return
        self.timer.stop()
        self.runtime.close()
        self._closed = True

    def apply_settings(self, vehicle_config: dict, controller_mapping: dict) -> None:
        """Apply real settings synchronously while the Qt timer is paused."""
        if not self._started or self._closed:
            raise RuntimeError("R2 dashboard runtime is not active")
        apply = getattr(self.runtime, "apply_settings", None)
        if not callable(apply):
            raise RuntimeError("this runtime does not support live settings")
        was_active = self.timer.isActive()
        self.timer.stop()
        try:
            self._publish(apply(vehicle_config, controller_mapping))
        finally:
            if was_active and not self._closed:
                self.timer.start()

    def _publish(self, snapshot) -> None:
        self.host.set_fleet_dashboard_snapshot(snapshot)
        status_reader = getattr(self.runtime, "controller_input_snapshot", None)
        status_writer = getattr(self.host, "set_controller_input_snapshot", None)
        if callable(status_reader) and callable(status_writer):
            status_writer(status_reader())
