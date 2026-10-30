"""
path: /project/frontend/map_editor/render/geometry_builder.py
Назначение: Каноническое преобразование editor JSON -> (wall_segments, obstacles).

    Единый источник истины для:
    - Разрезания стен дверными проёмами (S143 FIX section 1: 3-stage lookup:
      geometric perpendicular -> wall_id field -> rotation prefix "wall_*").
    - Конвертации объектов -> obstacles (center -> top-left).

Используется:
    - SpatialDataLoader._build_spatial_data (game runtime)
    - scene_bridge.build_perceived_scene (Map Editor Game Preview)

Контракт: чистые функции, без состояния, без I/O.
GAME-PREVIEW-IMPLEMENTATION-1.
"""

from typing import Any


def split_wall_by_openings(wall: dict, openings: list[dict]) -> list[dict]:
    """Разрезает сегмент стены на части, исключая проёмы (двери, проходы).

    Port из scene_state_manager._split_wall_by_openings (backend).
    S81-FIX: устраняет дублирование между SpatialDataLoader и scene_bridge.
    """
    if not openings:
        return [
            {
                "x1": float(wall.get("x1", 0)),
                "y1": float(wall.get("y1", 0)),
                "x2": float(wall.get("x2", 0)),
                "y2": float(wall.get("y2", 0)),
            }
        ]

    x1, y1 = float(wall["x1"]), float(wall["y1"])
    x2, y2 = float(wall["x2"]), float(wall["y2"])

    dx = x2 - x1
    dy = y2 - y1
    wall_len = (dx * dx + dy * dy) ** 0.5
    if wall_len == 0:
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]

    ux = dx / wall_len
    uy = dy / wall_len

    gaps = []
    for op in openings:
        pos = op.get("position", {})
        size = op.get("size", {})
        px, py = float(pos.get("x", 0)), float(pos.get("y", 0))
        vx, vy = px - x1, py - y1
        dist_along = vx * ux + vy * uy
        perp_dist = abs(vx * (-uy) + vy * ux)

        if perp_dist > 0.5:
            continue

        if abs(dx) < abs(dy):  # Вертикальная стена
            span = float(size.get("h", 1.0))
        else:  # Горизонтальная стена
            span = float(size.get("w", 1.0))

        gap_start = dist_along - span / 2
        gap_end = dist_along + span / 2
        gaps.append((gap_start, gap_end))

    if not gaps:
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]

    gaps.sort()
    merged = [list(gaps[0])]
    for gs, ge in gaps[1:]:
        if gs <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], ge)
        else:
            merged.append([gs, ge])

    segments = []
    current = 0.0
    for gs, ge in merged:
        gs = max(0.0, gs)
        ge = min(wall_len, ge)
        if gs > current:
            segments.append(
                {
                    "x1": x1 + ux * current,
                    "y1": y1 + uy * current,
                    "x2": x1 + ux * gs,
                    "y2": y1 + uy * gs,
                }
            )
        current = ge

    if current < wall_len:
        segments.append(
            {
                "x1": x1 + ux * current,
                "y1": y1 + uy * current,
                "x2": x2,
                "y2": y2,
            }
        )

    return segments


def build_geometry(editor_data: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Построить (wall_segments, obstacles) из editor JSON.

    Единая каноническая функция для:
    - SpatialDataLoader._build_spatial_data (game runtime)
    - scene_bridge.build_perceived_scene (Map Editor Game Preview)

    Шаги:
    1. Найти door/door_transition объекты и сопоставить их со стенами
       (S143 FIX section 1: 3-stage lookup - geometric -> wall_id -> rotation).
    2. Разрезать стены на сегменты, исключая проёмы.
    3. Конвертировать объекты -> obstacles (center -> top-left).

    Args:
        editor_data: dict с ключами "walls", "objects" (формат campaign JSON).

    Returns:
        walls: list[dict] с ключами x1, y1, x2, y2 (сегменты с проёмами).
        obstacles: list[dict] с ключами x, y, w, h, type, id, passability, blocks_los.
    """
    walls: list[dict] = []
    wall_openings: dict[str, list[dict]] = {}
    for obj in editor_data.get("objects", []):
        if not obj.get("passability", {}).get("walk", True):
            continue
        if obj.get("type") not in ("door", "door_transition"):
            continue

        walls_for_door: list[str] = []
        door_pos = obj.get("position", {})
        px, py = door_pos.get("x", 0), door_pos.get("y", 0)
        for wall in editor_data.get("walls", []):
            wid = wall.get("id")
            x1, y1 = wall.get("x1", 0), wall.get("y1", 0)
            x2, y2 = wall.get("x2", 0), wall.get("y2", 0)
            dx, dy = x2 - x1, y2 - y1
            wall_len = (dx * dx + dy * dy) ** 0.5
            if wall_len == 0:
                continue
            ux = dx / wall_len
            uy = dy / wall_len
            vx, vy = px - x1, py - y1
            perp_dist = abs(vx * (-uy) + vy * ux)
            if perp_dist <= 0.5:
                walls_for_door.append(wid)

        explicit_wall_id = obj.get("wall_id")  # ME-1.5: unified root form
        if not explicit_wall_id:
            rot = obj.get("rotation")
            if isinstance(rot, str) and rot.startswith("wall_"):
                explicit_wall_id = rot

        if explicit_wall_id and explicit_wall_id not in walls_for_door:
            walls_for_door.append(explicit_wall_id)

        for wid in walls_for_door:
            wall_openings.setdefault(wid, []).append(obj)

    for wall in editor_data.get("walls", []):
        wall_id = wall.get("id", "")
        openings = wall_openings.get(wall_id, [])
        segments = split_wall_by_openings(wall, openings)
        walls.extend(segments)

    obstacles: list[dict] = []
    for obj in editor_data.get("objects", []):
        pos = obj.get("position", {})
        obj_size = obj.get("size", {})
        ow = float(obj_size.get("w", 1.0))
        oh = float(obj_size.get("h", 1.0))
        obstacles.append(
            {
                "x": float(pos.get("x", 0.0)) - ow / 2,  # center -> top-left
                "y": float(pos.get("y", 0.0)) - oh / 2,  # center -> top-left
                "w": ow,
                "h": oh,
                "type": obj.get("type", "decoration"),
                "id": obj.get("id", ""),
                "passability": obj.get("passability", {}),
                "blocks_los": obj.get("cover", 0) >= 0.8,
            }
        )

    return walls, obstacles
