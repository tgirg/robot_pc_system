from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PC = ROOT / "apps" / "robot_pc_system_4wis_dashboard" / "pc"
sys.path.insert(0, str(DASHBOARD_PC))

from field.field_model import FieldModel  # noqa: E402


def _field_yaml(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "field": {"width_mm": 4500, "height_mm": 2400, "custom_marker": "preserve-me"},
                "objects": [
                    {
                        "name": "brick_1",
                        "label_ja": "レンガ",
                        "kind": "black_brick",
                        "rect": {"x_mm": 100, "y_mm": 200, "width_mm": 240, "height_mm": 120},
                        "color": "#111827",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_field_object_orientation_bottom_face_and_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "field.yaml"
    _field_yaml(path)
    model = FieldModel.load(path)
    initial = model.get_objects()[0]
    assert initial.orientation_deg == 0.0
    assert initial.bottom_face == "NOT_CONFIGURED"

    assert model.update_object_pose(
        "brick_1",
        x_mm=350,
        y_mm=460,
        orientation_deg=270,
        bottom_face="front",
    ) is True
    model.save_objects()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["field"]["custom_marker"] == "preserve-me"
    assert raw["objects"][0]["orientation_deg"] == -90.0
    assert raw["objects"][0]["bottom_face"] == "FRONT"
    reloaded = FieldModel.load(path).get_objects()[0]
    assert reloaded.rect.x_mm == 350
    assert reloaded.rect.y_mm == 460
    assert reloaded.orientation_deg == -90.0
    assert reloaded.bottom_face == "FRONT"


def test_move_object_preserves_orientation_and_bottom_face(tmp_path: Path) -> None:
    path = tmp_path / "field.yaml"
    _field_yaml(path)
    model = FieldModel.load(path)
    model.update_object_pose(
        "brick_1",
        x_mm=100,
        y_mm=200,
        orientation_deg=45,
        bottom_face="LEFT",
    )
    assert model.move_object("brick_1", 777, 888) is True
    moved = model.get_objects()[0]
    assert moved.orientation_deg == 45
    assert moved.bottom_face == "LEFT"
    assert moved.rect.x_mm == 777
    assert moved.rect.y_mm == 888
