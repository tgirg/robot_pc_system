from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
PC_DIR = ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from PySide6.QtWidgets import QApplication

from field import FieldModel
from widgets.test_field_widget import TestFieldWidget


def main() -> int:
    model = FieldModel.load()
    assert model.get_field_size() == (4500.0, 2400.0)
    assert model.is_inside_field(0, 0) is True
    assert model.is_inside_field(4500, 2400) is True
    assert model.is_inside_field(-1, 0) is False
    assert model.is_inside_field(4501, 0) is False
    assert isinstance(model.get_zone_at(100, 100), str)
    assert model.get_zone_at(2100, 2100) == "R2スタートゾーン"
    distance = model.distance_to_nearest_wall(2000, 1200)
    assert isinstance(distance, float)
    assert distance >= 0.0
    assert model.raycast_to_walls(2000, 1200, 0) is not None
    assert model.get_expected_wall_distance("front", 2000, 1200, 0) is not None

    r1 = model.get_robot_initial_pose("r1")
    r2 = model.get_robot_initial_pose("r2")
    assert r1 == (2100.0, 300.0, 0.0)
    assert r2 == (2100.0, 2100.0, 0.0)
    assert model.is_inside_zone("r1_start", r1[0], r1[1])
    assert model.is_inside_zone("r2_start", r2[0], r2[1])
    r2_start_rect = model.get_zone_rect("r2_start")
    assert r2_start_rect is not None
    line_inset_mm = float(model.tape.get("normal_width_mm", 19))
    assert r2_start_rect.left + line_inset_mm < r2[0] < r2_start_rect.right - line_inset_mm
    assert r2_start_rect.top + line_inset_mm < r2[1] < r2_start_rect.bottom - line_inset_mm
    assert model.is_inside_field(r1[0], r1[1])
    assert model.is_inside_field(r2[0], r2[1])
    assert (r1[0], r1[1]) != (r2[0], r2[1])

    app = QApplication.instance() or QApplication([])
    widget = TestFieldWidget()
    assert (widget.r1_pose[0], widget.r1_pose[1], widget.r1_pose[2]) == r1
    assert (widget.state.x_mm, widget.state.y_mm, widget.state.theta_deg) == r2
    assert r2_start_rect.left + line_inset_mm < widget.state.x_mm < r2_start_rect.right - line_inset_mm
    assert r2_start_rect.top + line_inset_mm < widget.state.y_mm < r2_start_rect.bottom - line_inset_mm
    widget.update_from_pose("シミュレーション", 2500, 1200, 45, has_data=True)
    assert (widget.state.x_mm, widget.state.y_mm, widget.state.theta_deg) == (2500.0, 1200.0, 45.0)
    widget.reset_r2_to_start(emit_signal=False)
    assert (widget.state.x_mm, widget.state.y_mm, widget.state.theta_deg) == r2
    widget.update_from_pose("シミュレーション", 2500, 1200, 45, has_data=True)
    widget.r1_pose = (2200.0, 300.0, 0.0)
    widget.reset_all(emit_signal=False)
    assert (widget.r1_pose[0], widget.r1_pose[1], widget.r1_pose[2]) == r1
    assert (widget.state.x_mm, widget.state.y_mm, widget.state.theta_deg) == r2
    app.processEvents()
    print("field model test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
