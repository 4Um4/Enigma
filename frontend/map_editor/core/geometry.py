"""
map_editor/core/geometry.py
Математические и геометрические хелперы редактора карт.
"""
import math
from typing import Tuple, List

SCALE = 20

class Geometry:
    """Содержит статические методы для преобразования координат и расчётов геометрии."""

    @staticmethod
    def world_to_screen(camera_x: float, camera_y: float, zoom: float, wx: float, wy: float) -> Tuple[int, int]:
        """Преобразует мировые координаты в экранные"""
        sx = int(wx * SCALE * zoom + camera_x)
        sy = int(wy * SCALE * zoom + camera_y)
        return (sx, sy)

    @staticmethod
    def screen_to_world(camera_x: float, camera_y: float, zoom: float, sx: int, sy: int) -> Tuple[float, float]:
        """Преобразует экранные координаты в мировые"""
        wx = (sx - camera_x) / (SCALE * zoom)
        wy = (sy - camera_y) / (SCALE * zoom)
        return (wx, wy)

    @staticmethod
    def snap_to_grid(x: float, y: float, grid_size: float = 0.5) -> Tuple[float, float]:
        """Привязывает координаты к сетке"""
        return (round(x / grid_size) * grid_size, round(y / grid_size) * grid_size)

    @staticmethod
    def rotated_rect_points(cx: float, cy: float, w: float, h: float, angle_deg: float) -> List[Tuple[float, float]]:
        """Возвращает 4 точки повёрнутого прямоугольника"""
        angle = math.radians(angle_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        hw, hh = w / 2, h / 2
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        return [
            (x * cos_a - y * sin_a + cx, x * sin_a + y * cos_a + cy) for x, y in corners
        ]

    @staticmethod
    def point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Расстояние от точки до отрезка"""
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    @staticmethod
    def project_point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float]:
        """Проецирует точку на отрезок. Возвращает (proj_x, proj_y)."""
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return x1, y1
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        return x1 + t * dx, y1 + t * dy

    @staticmethod
    def segments_intersect(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> bool:
        """Стандартный алгоритм проверки пересечения отрезков (CCW)."""
        def ccw(ax, ay, bx, by, cx, cy):
            return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
        
        return (
            ccw(x1, y1, x3, y3, x4, y4) != ccw(x2, y2, x3, y3, x4, y4) and
            ccw(x1, y1, x2, y2, x3, y3) != ccw(x1, y1, x2, y2, x4, y4)
        )

    @staticmethod
    def point_near_line(px: int, py: int, x1: int, y1: int, x2: int, y2: int, threshold: int) -> bool:
        """Проверяет, находится ли точка рядом с отрезком"""
        line_len = math.hypot(x2 - x1, y2 - y1)
        if line_len == 0:
            return math.hypot(px - x1, py - y1) < threshold

        t = max(
            0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_len**2))
        )
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)

        return math.hypot(px - proj_x, py - proj_y) < threshold