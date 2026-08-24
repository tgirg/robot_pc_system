from __future__ import annotations

from pc_controller.safety import SafetyMonitor, SafetyState


def test_initial_state_is_safe() -> None:
    monitor = SafetyMonitor()
    assert monitor.state == SafetyState.SAFE
    assert monitor.armed is False


def test_config_does_not_arm() -> None:
    monitor = SafetyMonitor()
    monitor.apply_config()
    assert monitor.state == SafetyState.SAFE
    assert monitor.armed is False
    assert monitor.config_accepted is False


def test_config_ack_is_required_before_real_arm_flow() -> None:
    monitor = SafetyMonitor()
    monitor.apply_config()
    monitor.mark_config_accepted()
    monitor.request_arm(100)
    assert monitor.state == SafetyState.ARM_PENDING
    assert monitor.armed is False
    monitor.confirm_arm(120)
    assert monitor.state == SafetyState.NORMAL
    assert monitor.armed is True


def test_arm_ack_is_ignored_without_a_pending_user_request() -> None:
    monitor = SafetyMonitor()
    assert monitor.confirm_arm(100) is False
    assert monitor.state == SafetyState.SAFE
    assert monitor.armed is False


def test_timeout_warn_stop_and_disarm() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    assert monitor.update_timeout(250) == "warn"
    assert monitor.warning is True
    assert monitor.update_timeout(350) == "stop"
    assert monitor.stopped_by_timeout is True
    assert monitor.update_timeout(550) == "safe"
    assert monitor.state == SafetyState.SAFE
    assert monitor.armed is False


def test_telemetry_refresh_prevents_rx_timeout() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    monitor.record_drive(250)
    assert monitor.update_timeout(250) == "warn"
    monitor.record_telemetry(260, seq=1)
    monitor.record_drive(460)
    monitor.record_telemetry(460, seq=2)
    assert monitor.update_timeout(650) is None


def test_telemetry_sequence_regression_disarms() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    assert monitor.record_telemetry(20, seq=10) is True
    assert monitor.record_telemetry(40, seq=9) is False
    assert monitor.state == SafetyState.SAFE
    assert monitor.fault == "telemetry sequence regression"


def test_duplicate_telemetry_is_stale_and_does_not_refresh_watchdog() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    assert monitor.record_telemetry(100, seq=5) is True
    assert monitor.record_telemetry(400, seq=5) is False
    assert monitor.last_valid_telemetry_ms == 100
    assert monitor.stale_telemetry_count == 1
    assert monitor.state == SafetyState.NORMAL
    monitor.record_drive(500)
    assert monitor.update_timeout(600) == "safe"
    assert monitor.fault == "telemetry timeout"


def test_first_safe_root_cause_survives_disarm_ack_and_follow_on_reasons() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    assert monitor.update_timeout(500) == "safe"
    assert monitor.fault == "telemetry timeout"

    monitor.disarm("communication timeout")
    monitor.disarm("disarmed")

    assert monitor.fault == "telemetry timeout"


def test_controller_disconnect_forces_safe() -> None:
    monitor = SafetyMonitor()
    monitor.arm(0)
    monitor.controller_disconnected()
    assert monitor.state == SafetyState.SAFE
    assert monitor.armed is False
