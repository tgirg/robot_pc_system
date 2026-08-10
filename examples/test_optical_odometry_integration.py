from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from sensors.optical_odometry_state import OpticalOdometryConfig, OpticalOdometryState


def assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 0.001:
        raise SystemExit(f"失敗: {label}: {actual} != {expected}")


def main() -> None:
    config = OpticalOdometryConfig(
        scale_x_mm_per_count=2.0,
        scale_y_mm_per_count=3.0,
        stale_timeout_ms=1000,
    )
    state = OpticalOdometryState(config=config)
    state.update_status("OK", source="REAL")
    converted = state.update_delta(10, 5, source="REAL")
    if converted is None:
        raise SystemExit("失敗: REAL + OK のOPTICAL差分が反映されません")
    assert_close(converted[0], 20.0, "scale x")
    assert_close(converted[1], 15.0, "scale y")
    field_dx, field_dy = state.transform_robot_delta_to_field(10.0, 0.0, 90.0)
    assert_close(round(field_dx, 6), 0.0, "theta 90 field dx")
    assert_close(round(field_dy, 6), 10.0, "theta 90 field dy")

    config.swap_xy = True
    config.invert_x = True
    state.zero()
    state.update_status("OK", source="REAL")
    converted = state.update_delta(10, 5, source="REAL")
    if converted is None:
        raise SystemExit("失敗: swap/invertの差分が反映されません")
    assert_close(converted[0], -10.0, "swap invert x")
    assert_close(converted[1], 30.0, "swap y")

    for status in ["DUMMY", "ERROR", "UNCONNECTED"]:
        state.zero()
        state.update_status(status, source="REAL")
        if state.update_delta(10, 5, source="REAL") is not None:
            raise SystemExit(f"失敗: {status} でR2位置へ反映されました")

    state.zero()
    state.update_status("OK", source="MOCK")
    if state.update_delta(10, 5, source="MOCK") is not None:
        raise SystemExit("失敗: MOCKでR2位置へ反映されました")

    state.zero()
    state.update_status("OK", source="REAL")
    state.last_received_time = time.monotonic() - 2.0
    if state.can_apply():
        raise SystemExit("失敗: 古い光学式データでR2位置へ反映されました")

    config.swap_xy = False
    config.invert_x = False
    config.max_delta_counts = 100.0
    state.zero()
    state.update_status("OK", source="REAL")
    if state.update_delta(101, 0, source="REAL") is not None:
        raise SystemExit("失敗: 異常に大きい差分でR2位置へ反映されました")

    print("optical odometry integration test ok")


if __name__ == "__main__":
    main()
