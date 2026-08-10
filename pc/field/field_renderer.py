from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from .field_model import FieldModel


class FieldRenderer:
    def __init__(self, model: FieldModel) -> None:
        self.model = model
        self.left_px = 0.0
        self.top_px = 0.0
        self.scale_px_per_mm = 1.0
        self.view_width_px = 1.0
        self.view_height_px = 1.0
        self.padding_px = 24.0

    def fit_to_widget(self, width_px: int, height_px: int, zoom: float = 1.0) -> float:
        available_w = max(1.0, float(width_px) - self.padding_px * 2.0)
        available_h = max(1.0, float(height_px) - self.padding_px * 2.0)
        base = min(available_w / self.model.width_mm, available_h / self.model.height_mm)
        self.scale_px_per_mm = max(0.01, base * max(0.1, zoom))
        self.view_width_px = self.model.width_mm * self.scale_px_per_mm
        self.view_height_px = self.model.height_mm * self.scale_px_per_mm
        self.left_px = (float(width_px) - self.view_width_px) / 2.0
        self.top_px = (float(height_px) - self.view_height_px) / 2.0
        return self.scale_px_per_mm

    def mm_to_px(self, x_mm: float, y_mm: float) -> QPointF:
        return QPointF(
            self.left_px + x_mm * self.scale_px_per_mm,
            self.top_px + y_mm * self.scale_px_per_mm,
        )

    def px_to_mm(self, x_px: float, y_px: float) -> tuple[float, float]:
        return (
            (x_px - self.left_px) / self.scale_px_per_mm,
            (y_px - self.top_px) / self.scale_px_per_mm,
        )

    def draw_field_background(self, painter: QPainter) -> None:
        painter.fillRect(QRectF(self.left_px, self.top_px, self.view_width_px, self.view_height_px), QColor("#16a34a"))
        painter.setPen(QPen(QColor("#052e16"), 2))
        painter.drawRect(QRectF(self.left_px, self.top_px, self.view_width_px, self.view_height_px))

    def draw_grid(self, painter: QPainter) -> None:
        thin_pen = QPen(QColor(255, 255, 255, 42), 1)
        thick_pen = QPen(QColor(255, 255, 255, 92), 1)
        label_pen = QPen(QColor("#e2e8f0"), 1)
        font = QFont(painter.font())
        font.setPointSize(8)
        painter.setFont(font)

        x = 0
        while x <= self.model.width_mm:
            painter.setPen(thick_pen if x % 1000 == 0 else thin_pen)
            a = self.mm_to_px(x, 0)
            b = self.mm_to_px(x, self.model.height_mm)
            painter.drawLine(a, b)
            if x % 1000 == 0:
                painter.setPen(label_pen)
                painter.drawText(a + QPointF(4, 14), f"{x} mm")
            x += 500

        y = 0
        while y <= self.model.height_mm:
            painter.setPen(thick_pen if y % 1000 == 0 else thin_pen)
            a = self.mm_to_px(0, y)
            b = self.mm_to_px(self.model.width_mm, y)
            painter.drawLine(a, b)
            if y % 1000 == 0:
                painter.setPen(label_pen)
                painter.drawText(a + QPointF(4, -4), f"{y} mm")
            y += 500

    def draw_zones(self, painter: QPainter, show_labels: bool = True) -> None:
        for zone in reversed(self.model.get_zones()):
            rect = zone.rect
            top_left = self.mm_to_px(rect.left, rect.top)
            qrect = QRectF(
                top_left.x(),
                top_left.y(),
                rect.width_mm * self.scale_px_per_mm,
                rect.height_mm * self.scale_px_per_mm,
            )
            color = QColor(zone.color)
            color.setAlpha(86)
            painter.fillRect(qrect, color)
            painter.setPen(QPen(QColor(255, 255, 255, 72), 1))
            painter.drawRect(qrect)
            if show_labels:
                painter.setPen(QColor("#f8fafc"))
                font = QFont(painter.font())
                font.setBold(True)
                font.setPointSize(9)
                painter.setFont(font)
                painter.drawText(qrect, Qt.AlignmentFlag.AlignCenter, zone.label_ja)

    def draw_wood_frame(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8b5a2b"))
        for wall in self.model.get_walls():
            rect = wall.rect
            top_left = self.mm_to_px(rect.left, rect.top)
            qrect = QRectF(
                top_left.x(),
                top_left.y(),
                max(1.0, rect.width_mm * self.scale_px_per_mm),
                max(1.0, rect.height_mm * self.scale_px_per_mm),
            )
            painter.drawRect(qrect)
        painter.setPen(QPen(QColor("#3f230f"), 1))
        for wall in self.model.get_walls():
            rect = wall.rect
            top_left = self.mm_to_px(rect.left, rect.top)
            painter.drawRect(
                QRectF(
                    top_left.x(),
                    top_left.y(),
                    max(1.0, rect.width_mm * self.scale_px_per_mm),
                    max(1.0, rect.height_mm * self.scale_px_per_mm),
                )
            )

    def draw_lines(self, painter: QPainter) -> None:
        for line in self.model.get_lines():
            if len(line.points) < 2:
                continue
            pen = QPen(QColor(line.color), max(2.0, line.width_mm * self.scale_px_per_mm))
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            for start, end in zip(line.points, line.points[1:]):
                painter.drawLine(self.mm_to_px(start[0], start[1]), self.mm_to_px(end[0], end[1]))

    def draw_objects(self, painter: QPainter, show_labels: bool = True) -> None:
        for item in self.model.get_objects():
            rect = item.rect
            top_left = self.mm_to_px(rect.left, rect.top)
            qrect = QRectF(
                top_left.x(),
                top_left.y(),
                max(2.0, rect.width_mm * self.scale_px_per_mm),
                max(2.0, rect.height_mm * self.scale_px_per_mm),
            )
            self._draw_field_object_shape(painter, item.kind, qrect, QColor(item.color))
            if show_labels:
                font = QFont(painter.font())
                font.setBold(True)
                font.setPointSize(8)
                painter.setFont(font)
                painter.setPen(QColor("#f8fafc") if item.kind == "black_brick" else QColor("#1f2937"))
                painter.drawText(qrect, Qt.AlignmentFlag.AlignCenter, item.label_ja)

    def _draw_field_object_shape(self, painter: QPainter, kind: str, qrect: QRectF, color: QColor) -> None:
        if kind == "watering_can":
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#075985"), 2))
            body = QRectF(qrect.left(), qrect.top() + qrect.height() * 0.22, qrect.width() * 0.72, qrect.height() * 0.62)
            painter.drawEllipse(body)
            spout_start = QPointF(body.right() - 2, body.center().y())
            spout_end = QPointF(qrect.right(), qrect.top() + qrect.height() * 0.24)
            painter.drawLine(spout_start, spout_end)
            handle = QRectF(qrect.left() + qrect.width() * 0.46, qrect.top(), qrect.width() * 0.42, qrect.height() * 0.46)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(handle, 20 * 16, 220 * 16)
            painter.setBrush(color)
            return

        border = QColor("#020617") if kind == "white_brick" else QColor("#713f12")
        painter.setBrush(color)
        painter.setPen(QPen(border, 2))
        painter.drawRect(qrect)
        if kind in {"black_brick", "white_brick"}:
            painter.setPen(QPen(QColor(255, 255, 255, 70) if kind == "black_brick" else QColor(15, 23, 42, 80), 1))
            y = qrect.top() + qrect.height() / 2.0
            painter.drawLine(QPointF(qrect.left(), y), QPointF(qrect.right(), y))
            x = qrect.left() + qrect.width() / 2.0
            painter.drawLine(QPointF(x, qrect.top()), QPointF(x, qrect.bottom()))

    def draw_zone_labels(self, painter: QPainter) -> None:
        self.draw_zones(painter, show_labels=True)

    def draw_odometry_trail(self, painter: QPainter, trail: list[tuple[float, float]]) -> None:
        if len(trail) < 2:
            return
        painter.setPen(QPen(QColor("#0ea5e9"), 2))
        for start, end in zip(trail, trail[1:]):
            painter.drawLine(self.mm_to_px(start[0], start[1]), self.mm_to_px(end[0], end[1]))

    def draw_lidar_rays(self, painter: QPainter, x_mm: float, y_mm: float, theta_deg: float) -> None:
        painter.setPen(QPen(QColor(250, 204, 21, 160), 1))
        origin = self.mm_to_px(x_mm, y_mm)
        for ray in self.model.simulate_lidar_from_field(x_mm, y_mm, theta_deg):
            distance = ray.get("distance_mm")
            angle = float(ray["world_angle_deg"])
            if distance is None:
                continue
            end_x = x_mm + float(distance) * math.cos(math.radians(angle))
            end_y = y_mm + float(distance) * math.sin(math.radians(angle))
            painter.drawLine(origin, self.mm_to_px(end_x, end_y))

    def draw_start_line(self, painter: QPainter, start_x_mm: float, start_y_mm: float, x_mm: float, y_mm: float) -> None:
        painter.setPen(QPen(QColor("#fef08a"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(self.mm_to_px(start_x_mm, start_y_mm), self.mm_to_px(x_mm, y_mm))

    def draw_robot(
        self,
        painter: QPainter,
        x_mm: float,
        y_mm: float,
        theta_deg: float,
        label: str = "R2",
        color: str = "#f59e0b",
        show_coordinate_label: bool = True,
        large: bool = False,
    ) -> None:
        center = self.mm_to_px(x_mm, y_mm)
        radius = max(10.0 if large else 7.0, (135.0 if large else 90.0) * self.scale_px_per_mm)
        painter.setBrush(QColor(color))
        painter.setPen(QPen(QColor("#fff7ed"), 2))
        painter.drawEllipse(center, radius, radius)
        heading_len = max(30.0 if large else 22.0, (250.0 if large else 220.0) * self.scale_px_per_mm)
        end = QPointF(
            center.x() + heading_len * math.cos(math.radians(theta_deg)),
            center.y() + heading_len * math.sin(math.radians(theta_deg)),
        )
        painter.drawLine(center, end)
        arrow_left = QPointF(
            end.x() - 10.0 * math.cos(math.radians(theta_deg - 25)),
            end.y() - 10.0 * math.sin(math.radians(theta_deg - 25)),
        )
        arrow_right = QPointF(
            end.x() - 10.0 * math.cos(math.radians(theta_deg + 25)),
            end.y() - 10.0 * math.sin(math.radians(theta_deg + 25)),
        )
        painter.drawLine(end, arrow_left)
        painter.drawLine(end, arrow_right)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(12 if large else 9)
        painter.setFont(font)
        if large:
            painter.setPen(QColor("#111827"))
            painter.drawText(QRectF(center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0), Qt.AlignmentFlag.AlignCenter, label)
        else:
            painter.drawText(center + QPointF(radius + 4, -radius - 4), label)
        if show_coordinate_label:
            coord_text = f"X:{x_mm:.0f} Y:{y_mm:.0f} θ:{theta_deg:.0f}"
            painter.setPen(QColor("#f8fafc"))
            painter.drawText(center + QPointF(radius + 4, radius + 14), coord_text)

    def draw_mouse_coordinate(self, painter: QPainter, x_mm: float, y_mm: float) -> None:
        text = f"マウス座標 X:{x_mm:.0f} mm / Y:{y_mm:.0f} mm"
        painter.setPen(QColor("#f8fafc"))
        painter.fillRect(QRectF(12, 12, 280, 28), QColor(15, 23, 42, 190))
        painter.drawText(QRectF(20, 17, 270, 20), Qt.AlignmentFlag.AlignLeft, text)
