"""
backend/movement_system.py
Система перемещения — коллизии со стенами, препятствиями, NPC.
Чистые функции без pygame. Координаты в метрах.

path: /backend/movement_system.py
Назначение: Проверка коллизий и обновление позиции игрока — чистая логика без pygame
Зависимости: math, typing
Основные сущности: MovementResult, try_move, move_towards
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class MovementResult:
    """Результат попытки перемещения"""

    success: bool
    new_x: float
    new_y: float
    blocked_by: Optional[str] = None  # "wall", "obstacle", "npc", None


# === Коллизии ===


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
    """Пересечение отрезков AB и CD"""

    def cross(ox, oy, px, py, qx, qy):
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


def _point_in_rect(px: float, py: float, rect: dict) -> bool:
    """Попадание точки в прямоугольник с небольшим отступом"""
    margin = 0.15  # метры — чтобы не прилипать вплотную
    return (
        rect["x"] - margin <= px <= rect["x"] + rect["w"] + margin
        and rect["y"] - margin <= py <= rect["y"] + rect["h"] + margin
    )


def _check_wall_collision(
    old_x: float,
    old_y: float,
    new_x: float,
    new_y: float,
    walls: List[dict],
) -> bool:
    """Проверяет пересечение линии движения со стенами"""
    for wall in walls:
        if _segments_intersect(
            old_x,
            old_y,
            new_x,
            new_y,
            wall["x1"],
            wall["y1"],
            wall["x2"],
            wall["y2"],
        ):
            return True
    return False


def _check_obstacle_collision(
    x: float,
    y: float,
    obstacles: List[dict],
) -> bool:
    """Проверяет попадание точки в непреодолимое препятствие."""
    for obs in obstacles:
        passthrough = obs.get("passability", {})
        # Data-driven: объекты, которые можно перелезть/перепрыгнуть, не блокируют коллизию
        if passthrough.get("jump_over", False) or passthrough.get("crawl_under", False):
            continue
        if _point_in_rect(x, y, obs):
            return True
    return False


def _check_npc_collision(
    x: float,
    y: float,
    npc_positions: Dict[str, dict],
    min_distance: float = 0.5,
) -> bool:
    """Проверяет слишком близкое расстояние до NPC"""
    for npc_data in npc_positions.values():
        lp = npc_data.get("local_position") or {}
        nx, ny = lp.get("x", 0), lp.get("y", 0)
        dist = math.hypot(x - nx, y - ny)
        if dist < min_distance:
            return True
    return False


# === Перемещение ===


def try_move(
    old_x: float,
    old_y: float,
    dx: float,
    dy: float,
    walls: List[dict],
    obstacles: List[dict],
    npc_positions: Dict[str, dict],
    step_size: float = 0.5,
) -> MovementResult:
    """
    Пытается сдвинуться на (dx, dy) с ограничением step_size.
    Проверяет коллизии. При блокировке пробует скольжение вдоль осей.

    Returns:
        MovementResult с новой позицией или причиной блокировки.
    """
    # Нормализуем и ограничиваем вектор
    length = math.hypot(dx, dy)
    if length < 0.01:
        return MovementResult(False, old_x, old_y)

    if length > step_size:
        scale = step_size / length
        dx *= scale
        dy *= scale

    new_x = old_x + dx
    new_y = old_y + dy

    # Проверяем коллизии в точке назначения
    if _check_wall_collision(old_x, old_y, new_x, new_y, walls):
        # Пробуем скольжение по X
        slide_x = old_x + dx
        if (
            not _check_wall_collision(old_x, old_y, slide_x, old_y, walls)
            and not _check_obstacle_collision(slide_x, old_y, obstacles)
            and not _check_npc_collision(slide_x, old_y, npc_positions)
        ):
            return MovementResult(True, slide_x, old_y)

        # Пробуем скольжение по Y
        slide_y = old_y + dy
        if (
            not _check_wall_collision(old_x, old_y, old_x, slide_y, walls)
            and not _check_obstacle_collision(old_x, slide_y, obstacles)
            and not _check_npc_collision(old_x, slide_y, npc_positions)
        ):
            return MovementResult(True, old_x, slide_y)

        return MovementResult(False, old_x, old_y, blocked_by="wall")

    if _check_obstacle_collision(new_x, new_y, obstacles):
        return MovementResult(False, old_x, old_y, blocked_by="obstacle")

    if _check_npc_collision(new_x, new_y, npc_positions):
        return MovementResult(False, old_x, old_y, blocked_by="npc")

    return MovementResult(True, new_x, new_y)


def move_towards(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    walls: List[dict],
    obstacles: List[dict],
    npc_positions: Dict[str, dict],
    step_size: float = 0.3,
    arrival_threshold: float = 0.8,
) -> Tuple[MovementResult, bool]:
    """
    Делает один шаг к цели. Возвращает (result, arrived).
    arrived=True когда расстояние меньше threshold.
    """
    dx = to_x - from_x
    dy = to_y - from_y
    dist = math.hypot(dx, dy)

    if dist < arrival_threshold:
        return MovementResult(True, from_x, from_y), True

    result = try_move(
        from_x, from_y, dx, dy, walls, obstacles, npc_positions, step_size
    )
    return result, False
