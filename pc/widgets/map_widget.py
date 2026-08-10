from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

try:
    from ..sensor_fusion import Pose
except ImportError:
    from sensor_fusion import Pose


class MapWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(480, 260)
        self.pose = Pose()
        self.pose_source = "Mock"
        self.boundary_status = ""
        self.obstacle_status = ""
        self.obstacles = []
        self.path: list[QPointF] = []
        self.scale = 90.0

    def set_pose(self, pose: Pose, source: str = "Mock", boundary_status: str = "", obstacle_status: str = "") -> None:
        self.pose = pose
        self.pose_source = source
        self.boundary_status = boundary_status
        self.obstacle_status = obstacle_status
        self.path.append(QPointF(pose.x, pose.y))
        if len(self.path) > 700:
            self.path = self.path[-700:]
        self.update()

    def clear_trail(self) -> None:
        self.path.clear()
        self.update()

    def set_obstacles(self, obstacles) -> None:
        self.obstacles = list(obstacles or [])
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101820"))

        center = QPointF(self.width() / 2, self.height() / 2)
        field_rect = QRectF(8, 8, self.width() - 16, self.height() - 16)
        painter.setPen(QPen(QColor("#475569"), 2))
        painter.drawRect(field_rect)

        grid_pen = QPen(QColor("#2a3540"), 1)
        painter.setPen(grid_pen)
        for x in range(0, self.width(), 40):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 40):
            painter.drawLine(0, y, self.width(), y)

        painter.setPen(QPen(QColor("#60a5fa"), 2))
        painter.setBrush(QColor(148, 163, 184, 90))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        for obstacle in self.obstacles:
            top_left = self._to_screen(QPointF(obstacle.left / 1000.0, obstacle.top / 1000.0), center)
            bottom_right = self._to_screen(QPointF(obstacle.right / 1000.0, obstacle.bottom / 1000.0), center)
            rect_x = min(top_left.x(), bottom_right.x())
            rect_y = min(top_left.y(), bottom_right.y())
            rect_w = abs(bottom_right.x() - top_left.x())
            rect_h = abs(bottom_right.y() - top_left.y())
            painter.drawRect(rect_x, rect_y, rect_w, rect_h)
            if obstacle.label:
                painter.drawText(rect_x + 4, rect_y + 16, obstacle.label)

        painter.setBrush(QColor(0, 0, 0, 0))
        painter.setPen(QPen(QColor("#60a5fa"), 2))
        if len(self.path) > 1:
            points = [self._to_screen(p, center) for p in self.path]
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)

        robot = self._to_screen(QPointF(self.pose.x, self.pose.y), center)
        theta = math.radians(self.pose.theta)
        heading = QPointF(robot.x() + 30 * math.cos(theta), robot.y() - 30 * math.sin(theta))
        painter.setBrush(QColor("#f59e0b"))
        painter.setPen(QPen(QColor("#f8fafc"), 2))
        painter.drawEllipse(robot, 10, 10)
        painter.drawLine(robot, heading)

        painter.setPen(QColor("#dfe7ef"))
        painter.drawText(
            12,
            24,
            f"ロボット位置: {self._source_label()}  x={self.pose.x:.2f} m  y={self.pose.y:.2f} m  θ={self.pose.theta:.1f} deg",
        )
        boundary_text = self.boundary_status or "正常"
        obstacle_text = self.obstacle_status or "正常"
        painter.drawText(12, 44, f"境界状態: {boundary_text} / 障害物状態: {obstacle_text}")

    def _source_label(self) -> str:
        labels = {
            "Mock": "Mock推定",
            "Simulation": "シミュレーション",
            "Real": "実機推定",
            "NoData": "データなし",
        }
        return labels.get(self.pose_source, self.pose_source)

    def _to_screen(self, point: QPointF, center: QPointF) -> QPointF:
        return QPointF(center.x() + point.x() * self.scale, center.y() - point.y() * self.scale)
