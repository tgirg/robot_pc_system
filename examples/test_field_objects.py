from __future__ import annotations

import sys
import os
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
    objects = model.get_objects()
    assert objects, "フィールドオブジェクト定義がありません"
    for item in objects:
        assert item.name
        assert item.label_ja
        assert item.rect.width_mm > 0
        assert item.rect.height_mm > 0
        cx, cy = item.rect.center
        assert model.is_inside_field(cx, cy), f"オブジェクトがフィールド外です: {item.name}"
    kinds = {item.kind for item in objects}
    assert {"black_brick", "white_brick", "watering_can"}.issubset(kinds), "標準オブジェクトが不足しています"

    app = QApplication.instance() or QApplication([])
    widget = TestFieldWidget()
    initial_count = len(widget.field_model.get_objects())
    widget.object_edit_check.setChecked(True)
    widget.object_type_combo.setCurrentIndex(widget.object_type_combo.findData("black_brick"))
    widget.add_object_at(2200, 1200)
    assert len(widget.field_model.get_objects()) == initial_count + 1
    selected = widget._selected_object()
    assert selected is not None
    assert selected.kind == "black_brick"
    assert widget.field_model.is_inside_field(*selected.rect.center)
    old_x = selected.rect.x_mm
    widget.nudge_selected_object(100, 0)
    moved = widget._selected_object()
    assert moved is not None and moved.rect.x_mm == old_x + 100
    widget.move_step_combo.setCurrentIndex(widget.move_step_combo.findData(50))
    old_y = moved.rect.y_mm
    widget.nudge_selected_object(0, widget._move_step_mm())
    moved = widget._selected_object()
    assert moved is not None and moved.rect.y_mm == old_y + 50
    widget.object_x_spin.setValue(2500)
    widget.object_y_spin.setValue(1400)
    widget.apply_selected_object_position()
    moved = widget._selected_object()
    assert moved is not None and moved.rect.x_mm == 2500 and moved.rect.y_mm == 1400
    original_name = moved.name
    widget.duplicate_selected_object()
    assert len(widget.field_model.get_objects()) == initial_count + 2
    copied = widget._selected_object()
    assert copied is not None and copied.kind == "black_brick"
    widget.move_object_to(copied.name, 2600, 1500)
    dragged = widget._selected_object()
    assert dragged is not None and dragged.rect.x_mm == 2600 and dragged.rect.y_mm == 1500
    widget.delete_selected_object()
    assert len(widget.field_model.get_objects()) == initial_count + 1
    widget.select_object(original_name)
    widget.delete_selected_object()
    assert len(widget.field_model.get_objects()) == initial_count
    widget.add_object_at(2600, 1300)
    assert len(widget.field_model.get_objects()) == initial_count + 1
    widget.reset_objects()
    assert len(widget.field_model.get_objects()) == initial_count
    widget.close()
    app.processEvents()
    print("field objects test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
