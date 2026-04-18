"""
backend/app/services/npc/spatial_runtime.py
R4 runtime: расстояния XY, LOS, звук, извлечение контекста сцены для NPC.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from app.core.config import settings
from app.core.constants import PERCEPTION_FALLBACK_DISTANCE, PERCEPTION_RADIUS
from app.services.spatial.location_graph import LocationGraph, load_graph, local_xy_distance


def _loc(entity: dict, fallback_location_id: str) -> str:
    """Возвращает location_id сущности или fallback."""
    return str(entity.get("location_id") or fallback_location_id)


def _node(entity: dict) -> str:
    """Возвращает имя узла графа для сущности."""
    return str(entity.get("position") or entity.get("node_id") or "")


def _local(entity: dict) -> tuple[float, float]:
    """Извлекает local_position (x, y) из словаря сущности."""
    local = entity.get("local_position") or {}
    try:
        return float(local.get("x", 0.0)), float(local.get("y", 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def resolve_distance_between_entities(
    scene_state: dict,
    a: dict,
    b: dict,
    graph: Optional[LocationGraph] = None,
) -> float:
    """
    R4.3: дистанция в метрах = расстояние между узлами графа + local XY смещение.

    graph — предзагруженный граф для batch-операций (например, в extract_scene_for_npc).
    Если не передан — загружается автоматически (с кэшем, I/O только при первом вызове).
    Возвращает 999.0 если сущности в разных локациях или узлы не определены.
    """
    location_id = scene_state.get("location_id", "")
    if _loc(a, location_id) != _loc(b, location_id):
        return 999.0

    node_a = _node(a)
    node_b = _node(b)
    if not node_a or not node_b:
        return 999.0

    if graph is None:
        graph = load_graph(location_id, data_dir=str(settings.data_dir))

    return local_xy_distance(graph, node_a, node_b, _local(a), _local(b))


def _point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Минимальное расстояние от точки (px, py) до отрезка (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def is_blocked_by_wall(ax: float, ay: float, bx: float, by: float, scene_state: dict) -> bool:
    """Проверяет, пересекает ли линия AB любую стену из spatial_walls."""
    walls = scene_state.get("spatial_walls", [])
    if not walls:
        return False
    for wall in walls:
        if _segments_intersect(ax, ay, bx, by, wall["x1"], wall["y1"], wall["x2"], wall["y2"]):
            return True
    return False


def is_blocked_by_obstacle(ax: float, ay: float, bx: float, by: float, scene_state: dict) -> bool:
    """Проверяет, пересекает ли линия AB любой прямоугольный obstacle."""
    obstacles = scene_state.get("spatial_obstacles", [])
    if not obstacles:
        return False
    for obs in obstacles:
        if not obs.get("blocks_los", False):
            continue
        if _line_rect_intersect(ax, ay, bx, by, obs["x"], obs["y"], obs["w"], obs["h"]):
            return True
    return False


def is_line_of_sight_clear(ax: float, ay: float, bx: float, by: float, scene_state: dict) -> bool:
    """Полная проверка LOS: стены + непроходимые объекты."""
    return not is_blocked_by_wall(ax, ay, bx, by, scene_state) and not is_blocked_by_obstacle(ax, ay, bx, by, scene_state)


def _segments_intersect(
    ax: float, ay: float, bx: float, by: float,
    cx: float, cy: float, dx: float, dy: float,
) -> bool:
    """Пересечение двух отрезков AB и CD."""
    def cross(ox: float, oy: float, px: float, py: float, qx: float, qy: float) -> float:
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    d1 = cross(cx, cy, dx, dy, ax, ay)
    d2 = cross(cx, cy, dx, dy, bx, by)
    d3 = cross(ax, ay, bx, by, cx, cy)
    d4 = cross(ax, ay, bx, by, dx, dy)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _line_rect_intersect(
    ax: float, ay: float, bx: float, by: float,
    rx: float, ry: float, rw: float, rh: float,
) -> bool:
    """Пересечение линии AB с прямоугольником (rx, ry, rw, rh)."""
    # Проверяем 4 стороны прямоугольника
    if _segments_intersect(ax, ay, bx, by, rx, ry, rx + rw, ry):
        return True
    if _segments_intersect(ax, ay, bx, by, rx + rw, ry, rx + rw, ry + rh):
        return True
    if _segments_intersect(ax, ay, bx, by, rx + rw, ry + rh, rx, ry + rh):
        return True
    if _segments_intersect(ax, ay, bx, by, rx, ry + rh, rx, ry):
        return True
    # Линия полностью внутри прямоугольника
    if rx <= ax <= rx + rw and ry <= ay <= ry + rh and rx <= bx <= rx + rw and ry <= by <= ry + rh:
        return True
    return False


def _effective_modifiers(scene_state: dict) -> dict:
    """
    R4.4: возвращает модификаторы среды с динамической плотностью.
    Чем больше NPC в сцене — тем выше density (толпа режет LOS и звук).
    Закрывает эксплойт фарма minor NPC: в толпе манипулировать сложнее.
    """
    modifiers   = dict(scene_state.get("environment_modifiers", {}))
    base_density = float(modifiers.get("density", 0.0))
    npc_count    = len(scene_state.get("npc_positions", {}))
    # Каждый NPC добавляет 0.05 к плотности, но не выше 1.0
    modifiers["density"] = min(1.0, base_density + npc_count * 0.05)
    return modifiers


def line_of_sight(distance: float, scene_state: dict, ax: float = 0.0, ay: float = 0.0, bx: float = 0.0, by: float = 0.0) -> bool:
    """
    R4.3/R4.4: видимость с учётом освещения, модификаторов среды и стен.
    Если переданы координаты — проверяет физические коллизии.
    """
    # Физическая проверка: стена или непроходимый объект между точками
    if ax != 0.0 or ay != 0.0 or bx != 0.0 or by != 0.0:
        if not is_line_of_sight_clear(ax, ay, bx, by, scene_state):
            return False

    env       = scene_state.get("environment", {})
    modifiers = _effective_modifiers(scene_state)

    light   = env.get("light_level", "dim")
    density = modifiers["density"]
    danger  = float(modifiers.get("danger", 0.0))

    if light == "dark":
        base_range = 4.0
    elif light == "dim":
        base_range = 10.0
    else:
        base_range = 15.0

    los_range = max(1.5, base_range - density * 6.0 - danger * 2.0)
    return distance <= los_range


def sound_reach(base_radius: float, scene_state: dict) -> float:
    """
    R4.4: радиус распространения звука с динамической плотностью.
    Шум усиливает дальность, плотность (стены/толпа) гасит.
    """
    modifiers = _effective_modifiers(scene_state)
    noise   = float(modifiers.get("noise", 0.0))
    density = modifiers["density"]
    return max(0.5, base_radius + noise * 4.0 - density * 3.0)


# Радиусы восприятия по tier — вызывающий код передаёт нужный.
# Из Баги.md: lazy evaluation для minor NPC экономит ресурсы и закрывает эксплойт фарма.


def extract_scene_for_npc(
    scene_state: dict,
    npc_id: str,
    npc_ids: Iterable[str],
    perception_radius: float = PERCEPTION_FALLBACK_DISTANCE,
) -> dict:
    """
    R4.5: снимок сцены для NPC — кто рядом, игрок, доступные действия.

    perception_radius — передаётся вызывающим кодом на основе tier NPC:
        PERCEPTION_RADIUS["minor"] = 3.0м
        PERCEPTION_RADIUS["major"] = 15.0м
    Граф загружается один раз для всех расчётов дистанций в цикле.
    """
    npc_positions = scene_state.get("npc_positions", {})
    me = npc_positions.get(npc_id, {})
    if not me:
        return {"nearby": [], "player": None, "available_actions": ["wait"]}

    location_id = scene_state.get("location_id", "")
    graph = load_graph(location_id, data_dir=str(settings.data_dir))

    # --- Другие NPC в радиусе восприятия ---
    nearby: list[dict] = []
    for other_id in npc_ids:
        if other_id == npc_id:
            continue
        other = npc_positions.get(other_id, {})
        if not other:
            continue

        # Невидимый NPC требует LOS + дистанцию ≤ 1.5м для обнаружения.
        # Иначе — для наблюдателя его не существует в сцене.
        if not other.get("visible", True):
            d = resolve_distance_between_entities(scene_state, me, other, graph=graph)
            if d > 1.5 or not line_of_sight(d, scene_state):
                continue
            nearby.append({"npc_id": other_id, "distance": round(d, 2), "detected": True})
            continue

        d = resolve_distance_between_entities(scene_state, me, other, graph=graph)
        if d <= perception_radius:
            my_xy = _local(me)
            other_xy = _local(other)
            los = line_of_sight(d, scene_state, my_xy[0], my_xy[1], other_xy[0], other_xy[1])
            nearby.append({"npc_id": other_id, "distance": round(d, 2), "in_los": los})

    # --- Игрок в радиусе восприятия ---
    player_snapshot: dict | None = None
    player_data = scene_state.get("player_spatial") or {}
    if isinstance(player_data, dict) and player_data:
        d_player = resolve_distance_between_entities(scene_state, me, player_data, graph=graph)
        if d_player <= perception_radius:
            my_xy = _local(me)
            player_xy = _local(player_data)
            los = line_of_sight(d_player, scene_state, my_xy[0], my_xy[1], player_xy[0], player_xy[1])
            player_snapshot = {
                "distance": round(d_player, 2),
                "in_los":   los,
                "position": player_data.get("position", ""),
            }

    # --- Доступные действия ---
    all_close = nearby + ([{"distance": player_snapshot["distance"]}] if player_snapshot else [])
    available_actions: list[str] = ["wait", "move"]
    if nearby or player_snapshot:
        available_actions.append("interact")
    if any(x["distance"] < 1.5 for x in all_close):
        available_actions.append("melee")

    return {
        "nearby":            sorted(nearby, key=lambda x: x["distance"]),
        "player":            player_snapshot,
        "available_actions": available_actions,
    }


def sound_bleeds_to_adjacent(
    scene_state: dict,
    base_radius: float,
    bleed_threshold: float = 12.0,
    data_dir: str = "data",
) -> list[str]:
    """
    R4.4: громкий звук просачивается в соседние локации через connected_locations.

    Возвращает список location_id которые слышат событие.
    Срабатывает только если sound_reach превышает bleed_threshold —
    тихие события не проходят сквозь стены.
    """
    import json
    from pathlib import Path

    effective_radius = sound_reach(base_radius, scene_state)
    if effective_radius < bleed_threshold:
        return []

    location_id    = scene_state.get("location_id", "")
    templates_path = Path(data_dir) / "locations" / "location_templates.json"

    try:
        templates  = json.loads(templates_path.read_text(encoding="utf-8-sig"))
        connected  = templates.get(location_id, {}).get("connected_locations", [])
        return list(connected)
    except (json.JSONDecodeError, OSError):
        return []