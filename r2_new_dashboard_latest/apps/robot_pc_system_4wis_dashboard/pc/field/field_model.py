from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_FIELD_PATH = Path(__file__).resolve().parents[2] / "config" / "field" / "f3rc2026_field.yaml"


@dataclass(frozen=True)
class FieldRect:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float

    @property
    def left(self) -> float:
        return self.x_mm

    @property
    def top(self) -> float:
        return self.y_mm

    @property
    def right(self) -> float:
        return self.x_mm + self.width_mm

    @property
    def bottom(self) -> float:
        return self.y_mm + self.height_mm

    @property
    def center(self) -> tuple[float, float]:
        return self.x_mm + self.width_mm / 2.0, self.y_mm + self.height_mm / 2.0

    def contains(self, x_mm: float, y_mm: float) -> bool:
        return self.left <= x_mm <= self.right and self.top <= y_mm <= self.bottom

    def distance_to_point(self, x_mm: float, y_mm: float) -> float:
        dx = max(self.left - x_mm, 0.0, x_mm - self.right)
        dy = max(self.top - y_mm, 0.0, y_mm - self.bottom)
        if dx == 0.0 and dy == 0.0:
            return min(
                abs(x_mm - self.left),
                abs(self.right - x_mm),
                abs(y_mm - self.top),
                abs(self.bottom - y_mm),
            )
        return math.hypot(dx, dy)


@dataclass(frozen=True)
class FieldZone:
    name: str
    label_ja: str
    rect: FieldRect
    color: str = "#22c55e"
    priority: int = 0
    source_note: str = ""


@dataclass(frozen=True)
class FieldWall:
    name: str
    label_ja: str
    rect: FieldRect
    group: str = "inner_dividers"
    source_note: str = ""


@dataclass(frozen=True)
class FieldLine:
    name: str
    label_ja: str
    points: tuple[tuple[float, float], ...]
    width_mm: float
    color: str
    source_note: str = ""


@dataclass(frozen=True)
class FieldObject:
    name: str
    label_ja: str
    rect: FieldRect
    color: str = "#facc15"
    kind: str = "generic"
    source_note: str = ""
    orientation_deg: float = 0.0
    bottom_face: str = "NOT_CONFIGURED"


class FieldModel:
    def __init__(
        self,
        width_mm: float,
        height_mm: float,
        tolerance_percent: float,
        floor_material: str,
        wood: dict[str, Any],
        tape: dict[str, Any],
        zones: list[FieldZone],
        walls: list[FieldWall],
        lines: list[FieldLine],
        robots: dict[str, Any] | None = None,
        objects: list[FieldObject] | None = None,
        source_note: str = "",
        source_path: str | Path | None = None,
    ) -> None:
        self.width_mm = float(width_mm)
        self.height_mm = float(height_mm)
        self.tolerance_percent = float(tolerance_percent)
        self.floor_material = str(floor_material)
        self.wood = dict(wood)
        self.tape = dict(tape)
        self.zones = sorted(zones, key=lambda zone: zone.priority, reverse=True)
        self.walls = walls
        self.lines = lines
        self.robots = robots or {}
        self.objects = objects or []
        self._default_objects = list(self.objects)
        self.source_note = source_note
        self.source_path = Path(source_path) if source_path is not None else None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "FieldModel":
        yaml_path = Path(path) if path is not None else DEFAULT_FIELD_PATH
        with yaml_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        model = cls.from_dict(data)
        model.source_path = yaml_path
        return model

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldModel":
        field = data.get("field", {})
        wood = data.get("wood", {})
        tape = data.get("tape", {})
        normal_width = float(tape.get("normal_width_mm", 19))

        zones = [
            FieldZone(
                name=str(item.get("name", "")),
                label_ja=str(item.get("label_ja", item.get("name", ""))),
                rect=_rect_from_dict(item.get("rect", {})),
                color=str(item.get("color", "#22c55e")),
                priority=int(item.get("priority", 0)),
                source_note=str(item.get("source_note", "")),
            )
            for item in data.get("zones", [])
        ]
        walls = [
            FieldWall(
                name=str(item.get("name", "")),
                label_ja=str(item.get("label_ja", item.get("name", ""))),
                rect=_rect_from_dict(item.get("rect", {})),
                group=str(item.get("group", "inner_dividers")),
                source_note=str(item.get("source_note", "")),
            )
            for item in data.get("walls", [])
        ]
        lines = [
            FieldLine(
                name=str(item.get("name", "")),
                label_ja=str(item.get("label_ja", item.get("name", ""))),
                points=tuple((float(point[0]), float(point[1])) for point in item.get("points", [])),
                width_mm=float(item.get("width_mm", normal_width)),
                color=str(item.get("color", "#ffffff")),
                source_note=str(item.get("source_note", "")),
            )
            for item in data.get("lines", [])
        ]
        objects = [
            FieldObject(
                name=str(item.get("name", "")),
                label_ja=str(item.get("label_ja", item.get("name", ""))),
                rect=_rect_from_dict(item.get("rect", {})),
                color=str(item.get("color", "#facc15")),
                kind=str(item.get("kind", "generic")),
                source_note=str(item.get("source_note", "")),
                orientation_deg=float(item.get("orientation_deg", 0.0)),
                bottom_face=str(item.get("bottom_face", "NOT_CONFIGURED")),
            )
            for item in data.get("objects", [])
        ]
        return cls(
            width_mm=float(field.get("width_mm", 4500)),
            height_mm=float(field.get("height_mm", 2400)),
            tolerance_percent=float(field.get("tolerance_percent", 5)),
            floor_material=str(field.get("floor_material", "green_lonleum")),
            wood=wood,
            tape=tape,
            zones=zones,
            walls=walls,
            lines=lines,
            robots=data.get("robots", {}),
            objects=objects,
            source_note=str(field.get("source_note", "")),
        )

    def get_field_size(self) -> tuple[float, float]:
        return self.width_mm, self.height_mm

    def get_zones(self) -> list[FieldZone]:
        return list(self.zones)

    def get_zone_rect(self, zone_name: str) -> FieldRect | None:
        for zone in self.zones:
            if zone.name == zone_name or zone.label_ja == zone_name:
                return zone.rect
        return None

    def get_walls(self) -> list[FieldWall]:
        return list(self.walls)

    def get_lines(self) -> list[FieldLine]:
        return list(self.lines)

    def get_objects(self) -> list[FieldObject]:
        return list(self.objects)

    def reset_objects(self) -> None:
        self.objects = list(self._default_objects)

    def add_object(self, item: FieldObject) -> None:
        self.objects.append(item)

    def remove_object(self, object_name: str) -> bool:
        before = len(self.objects)
        self.objects = [item for item in self.objects if item.name != object_name]
        return len(self.objects) != before

    def move_object(self, object_name: str, x_mm: float, y_mm: float) -> bool:
        updated: list[FieldObject] = []
        changed = False
        for item in self.objects:
            if item.name == object_name:
                rect = FieldRect(float(x_mm), float(y_mm), item.rect.width_mm, item.rect.height_mm)
                updated.append(
                    FieldObject(
                        name=item.name,
                        label_ja=item.label_ja,
                        rect=rect,
                        color=item.color,
                        kind=item.kind,
                        source_note=item.source_note,
                        orientation_deg=item.orientation_deg,
                        bottom_face=item.bottom_face,
                    )
                )
                changed = True
            else:
                updated.append(item)
        self.objects = updated
        return changed

    def update_object_pose(
        self,
        object_name: str,
        *,
        x_mm: float,
        y_mm: float,
        orientation_deg: float,
        bottom_face: str,
    ) -> bool:
        """Update editable object pose while retaining the legacy object keys."""
        updated: list[FieldObject] = []
        changed = False
        normalized_orientation = ((float(orientation_deg) + 180.0) % 360.0) - 180.0
        normalized_face = str(bottom_face).strip().upper() or "NOT_CONFIGURED"
        for item in self.objects:
            if item.name == object_name:
                updated.append(
                    FieldObject(
                        name=item.name,
                        label_ja=item.label_ja,
                        rect=FieldRect(float(x_mm), float(y_mm), item.rect.width_mm, item.rect.height_mm),
                        color=item.color,
                        kind=item.kind,
                        source_note=item.source_note,
                        orientation_deg=normalized_orientation,
                        bottom_face=normalized_face,
                    )
                )
                changed = True
            else:
                updated.append(item)
        self.objects = updated
        return changed

    def save_objects(self, path: str | Path | None = None) -> Path:
        """Atomically update only the YAML objects list and preserve all other keys."""
        target = Path(path) if path is not None else self.source_path
        if target is None:
            raise ValueError("field model has no source path")
        with target.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        if not isinstance(data, dict):
            raise ValueError("field YAML root must be an object")
        data["objects"] = [
            {
                "name": item.name,
                "label_ja": item.label_ja,
                "kind": item.kind,
                "rect": {
                    "x_mm": item.rect.x_mm,
                    "y_mm": item.rect.y_mm,
                    "width_mm": item.rect.width_mm,
                    "height_mm": item.rect.height_mm,
                },
                "color": item.color,
                "orientation_deg": item.orientation_deg,
                "bottom_face": item.bottom_face,
                "source_note": item.source_note,
            }
            for item in self.objects
        ]
        temporary = target.with_suffix(target.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
        os.replace(temporary, target)
        self.source_path = target
        self._default_objects = list(self.objects)
        return target

    def get_object_at(self, x_mm: float, y_mm: float) -> FieldObject | None:
        for item in reversed(self.objects):
            if item.rect.contains(x_mm, y_mm):
                return item
        return None

    def is_inside_field(self, x_mm: float, y_mm: float) -> bool:
        return 0.0 <= x_mm <= self.width_mm and 0.0 <= y_mm <= self.height_mm

    def get_zone_at(self, x_mm: float, y_mm: float) -> str:
        if not self.is_inside_field(x_mm, y_mm):
            return "フィールド外"
        for zone in self.zones:
            if zone.rect.contains(x_mm, y_mm):
                return zone.label_ja
        return "未定義ゾーン"

    def is_inside_zone(self, zone_name: str, x_mm: float, y_mm: float) -> bool:
        for zone in self.zones:
            if zone.name == zone_name or zone.label_ja == zone_name:
                return zone.rect.contains(x_mm, y_mm)
        return False

    def get_robot_initial_pose(self, robot_name: str) -> tuple[float, float, float]:
        robot = self.robots.get(robot_name.lower(), {})
        if "start_x_mm" in robot or "start_y_mm" in robot:
            return (
                float(robot.get("start_x_mm", 0.0)),
                float(robot.get("start_y_mm", 0.0)),
                float(robot.get("start_theta_deg", 0.0)),
            )
        pose = robot.get("initial_pose", {})
        return (
            float(pose.get("x_mm", 0.0)),
            float(pose.get("y_mm", 0.0)),
            float(pose.get("theta_deg", 0.0)),
        )

    def get_robot_label(self, robot_name: str) -> str:
        robot = self.robots.get(robot_name.lower(), {})
        return str(robot.get("display_name", robot.get("label", robot_name.upper())))

    def get_robot_color(self, robot_name: str) -> str:
        robot = self.robots.get(robot_name.lower(), {})
        return str(robot.get("color", "#f97316"))

    def get_robot_start_zone(self, robot_name: str) -> str:
        robot = self.robots.get(robot_name.lower(), {})
        return str(robot.get("start_zone", ""))

    def distance_to_nearest_wall(self, x_mm: float, y_mm: float) -> float:
        distances = [
            abs(x_mm),
            abs(self.width_mm - x_mm),
            abs(y_mm),
            abs(self.height_mm - y_mm),
        ]
        distances.extend(wall.rect.distance_to_point(x_mm, y_mm) for wall in self.walls)
        return float(max(0.0, min(distances)))

    def raycast_to_walls(self, x_mm: float, y_mm: float, angle_deg: float, max_distance_mm: float = 7000.0) -> float | None:
        if not self.is_inside_field(x_mm, y_mm):
            return None
        angle_rad = math.radians(angle_deg)
        dx = math.cos(angle_rad)
        dy = math.sin(angle_rad)
        hits: list[float] = []
        for rect in self._raycast_rects():
            distance = _raycast_rect(x_mm, y_mm, dx, dy, rect)
            if distance is not None and 0.0 <= distance <= max_distance_mm:
                hits.append(distance)
        return min(hits) if hits else None

    def simulate_lidar_from_field(
        self,
        x_mm: float,
        y_mm: float,
        theta_deg: float,
        ray_angles_deg: list[float] | None = None,
    ) -> list[dict[str, float | None]]:
        angles = ray_angles_deg if ray_angles_deg is not None else [-90, -60, -30, 0, 30, 60, 90]
        return [
            {
                "relative_angle_deg": float(relative),
                "world_angle_deg": float(theta_deg + relative),
                "distance_mm": self.raycast_to_walls(x_mm, y_mm, theta_deg + relative),
            }
            for relative in angles
        ]

    def get_expected_wall_distance(self, direction: str, x_mm: float, y_mm: float, theta_deg: float) -> float | None:
        offsets = {
            "front": 0.0,
            "left": -90.0,
            "right": 90.0,
        }
        if direction not in offsets:
            raise ValueError("direction must be front, left, or right")
        return self.raycast_to_walls(x_mm, y_mm, theta_deg + offsets[direction])

    def _raycast_rects(self) -> list[FieldRect]:
        rects = [
            FieldRect(0, 0, self.width_mm, 0),
            FieldRect(0, self.height_mm, self.width_mm, 0),
            FieldRect(0, 0, 0, self.height_mm),
            FieldRect(self.width_mm, 0, 0, self.height_mm),
        ]
        rects.extend(wall.rect for wall in self.walls)
        return rects


def _rect_from_dict(data: dict[str, Any]) -> FieldRect:
    return FieldRect(
        x_mm=float(data.get("x_mm", 0)),
        y_mm=float(data.get("y_mm", 0)),
        width_mm=float(data.get("width_mm", 0)),
        height_mm=float(data.get("height_mm", 0)),
    )


def _raycast_rect(x: float, y: float, dx: float, dy: float, rect: FieldRect) -> float | None:
    hits: list[float] = []
    if rect.width_mm == 0.0:
        _add_vertical_hit(hits, x, y, dx, dy, rect.left, rect.top, rect.bottom)
        return min(hits) if hits else None
    if rect.height_mm == 0.0:
        _add_horizontal_hit(hits, x, y, dx, dy, rect.top, rect.left, rect.right)
        return min(hits) if hits else None

    _add_vertical_hit(hits, x, y, dx, dy, rect.left, rect.top, rect.bottom)
    _add_vertical_hit(hits, x, y, dx, dy, rect.right, rect.top, rect.bottom)
    _add_horizontal_hit(hits, x, y, dx, dy, rect.top, rect.left, rect.right)
    _add_horizontal_hit(hits, x, y, dx, dy, rect.bottom, rect.left, rect.right)
    return min(hits) if hits else None


def _add_vertical_hit(hits: list[float], x: float, y: float, dx: float, dy: float, wall_x: float, y_min: float, y_max: float) -> None:
    if abs(dx) < 1e-9:
        return
    t = (wall_x - x) / dx
    hit_y = y + t * dy
    if t >= 0.0 and y_min <= hit_y <= y_max:
        hits.append(t)


def _add_horizontal_hit(hits: list[float], x: float, y: float, dx: float, dy: float, wall_y: float, x_min: float, x_max: float) -> None:
    if abs(dy) < 1e-9:
        return
    t = (wall_y - y) / dy
    hit_x = x + t * dx
    if t >= 0.0 and x_min <= hit_x <= x_max:
        hits.append(t)


def simulate_lidar_from_field(x_mm: float, y_mm: float, theta_deg: float) -> list[dict[str, float | None]]:
    return FieldModel.load().simulate_lidar_from_field(x_mm, y_mm, theta_deg)


def raycast_to_walls(x_mm: float, y_mm: float, angle_deg: float) -> float | None:
    return FieldModel.load().raycast_to_walls(x_mm, y_mm, angle_deg)


def get_expected_wall_distance(direction: str, x_mm: float, y_mm: float, theta_deg: float) -> float | None:
    return FieldModel.load().get_expected_wall_distance(direction, x_mm, y_mm, theta_deg)
