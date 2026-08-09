"""
Файл: backend/app/services/spatial/geometry_kernel.py
Назначение: Чистые математические примитивы для 2D геометрии. Не знают о домене и сервисах.
"""

from __future__ import annotations

import math
from typing import Tuple

EPSILON = 1e-9

def _dist_sq(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

def point_to_segment_dist_sq(p: Tuple[float, float], s1: Tuple[float, float], s2: Tuple[float, float]) -> float:
    l2 = _dist_sq(s1, s2)
    if l2 == 0:
        return _dist_sq(p, s1)
    t = max(0, min(1, ((p[0] - s1[0]) * (s2[0] - s1[0]) + (p[1] - s1[1]) * (s2[1] - s1[1])) / l2))
    proj = (s1[0] + t * (s2[0] - s1[0]), s1[1] + t * (s2[1] - s1[1]))
    return _dist_sq(p, proj)

def _orientation(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

def _on_segment(a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float]) -> bool:
    return (min(a[0], b[0]) - EPSILON <= p[0] <= max(a[0], b[0]) + EPSILON and
            min(a[1], b[1]) - EPSILON <= p[1] <= max(a[1], b[1]) + EPSILON)

def segments_intersect(a1: Tuple[float, float], a2: Tuple[float, float], b1: Tuple[float, float], b2: Tuple[float, float]) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if ((o1 > EPSILON and o2 < -EPSILON) or (o1 < -EPSILON and o2 > EPSILON)) and \
       ((o3 > EPSILON and o4 < -EPSILON) or (o3 < -EPSILON and o4 > EPSILON)):
        return True

    if abs(o1) <= EPSILON and _on_segment(a1, a2, b1):
        return True
    if abs(o2) <= EPSILON and _on_segment(a1, a2, b2):
        return True
    if abs(o3) <= EPSILON and _on_segment(b1, b2, a1):
        return True
    if abs(o4) <= EPSILON and _on_segment(b1, b2, a2):
        return True

    return False

def segments_distance_sq(s1p1: Tuple[float, float], s1p2: Tuple[float, float], s2p1: Tuple[float, float], s2p2: Tuple[float, float]) -> float:
    if segments_intersect(s1p1, s1p2, s2p1, s2p2):
        return 0.0
    return min(
        point_to_segment_dist_sq(s1p1, s2p1, s2p2),
        point_to_segment_dist_sq(s1p2, s2p1, s2p2),
        point_to_segment_dist_sq(s2p1, s1p1, s1p2),
        point_to_segment_dist_sq(s2p2, s1p1, s1p2)
    )

def point_in_rect(p: Tuple[float, float], rx: float, ry: float, rw: float, rh: float) -> bool:
    return rx <= p[0] <= rx + rw and ry <= p[1] <= ry + rh

def point_to_rect_min_dist_sq(p: Tuple[float, float], rx: float, ry: float, rw: float, rh: float) -> float:
    cx = max(rx, min(p[0], rx + rw))
    cy = max(ry, min(p[1], ry + rh))
    return _dist_sq(p, (cx, cy))

def segment_to_rect_min_dist_sq(p1: Tuple[float, float], p2: Tuple[float, float], rx: float, ry: float, rw: float, rh: float) -> float:
    """Честное расстояние от отрезка до прямоугольника (включая внутренности)."""
    # 1. Если любой конец внутри прямоугольника — расстояние 0
    if point_in_rect(p1, rx, ry, rw, rh):
        return 0.0
    if point_in_rect(p2, rx, ry, rw, rh):
        return 0.0

    # 2. Если отрезок пересекает любое из 4 рёбер — расстояние 0
    corners = [(rx, ry), (rx+rw, ry), (rx+rw, ry+rh), (rx, ry+rh)]
    for i in range(4):
        if segments_intersect(p1, p2, corners[i], corners[(i+1)%4]):
            return 0.0

    # 3. Иначе — минимальное расстояние до 4 рёбер
    return min(
        segments_distance_sq(p1, p2, corners[i], corners[(i+1)%4])
        for i in range(4)
    )

def expanded_rect(
    rx: float,
    ry: float,
    rw: float,
    rh: float,
    expansion: float
) -> Tuple[float, float, float, float]:
    """Возвращает координаты расширенного AABB (Collision Envelope)."""
    return (
        rx - expansion,
        ry - expansion,
        rw + 2 * expansion,
        rh + 2 * expansion
    )

def point_in_expanded_rect(
    p: Tuple[float, float],
    rx: float,
    ry: float,
    rw: float,
    rh: float,
    expansion: float
) -> bool:
    """Проверяет, находится ли точка внутри расширенного AABB (Collision Envelope)."""
    exp_x, exp_y, exp_w, exp_h = expanded_rect(rx, ry, rw, rh, expansion)
    return (
        exp_x <= p[0] <= exp_x + exp_w
        and
        exp_y <= p[1] <= exp_y + exp_h
    )


def _segments_intersect(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
    dx: float,
    dy: float,
) -> bool:
    """Перенесено из spatial_runtime.py. Пересечение двух отрезков AB и CD."""
    def cross(
        ox: float, oy: float, px: float, py: float, qx: float, qy: float
    ) -> float:
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    d1 = cross(cx, cy, dx, dy, ax, ay)
    d2 = cross(cx, cy, dx, dy, bx, by)
    d3 = cross(ax, ay, bx, by, cx, cy)
    d4 = cross(ax, ay, bx, by, dx, dy)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return False


def _line_rect_intersect(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    rx: float,
    ry: float,
    rw: float,
    rh: float,
) -> bool:
    """Перенесено из spatial_runtime.py. Пересечение линии AB с прямоугольником."""
    if _segments_intersect(ax, ay, bx, by, rx, ry, rx + rw, ry):
        return True
    if _segments_intersect(ax, ay, bx, by, rx + rw, ry, rx + rw, ry + rh):
        return True
    if _segments_intersect(ax, ay, bx, by, rx + rw, ry + rh, rx, ry + rh):
        return True
    if _segments_intersect(ax, ay, bx, by, rx, ry + rh, rx, ry):
        return True
    if (
        rx <= ax <= rx + rw
        and ry <= ay <= ry + rh
        and rx <= bx <= rx + rw
        and ry <= by <= ry + rh
    ):
        return True
    return False
