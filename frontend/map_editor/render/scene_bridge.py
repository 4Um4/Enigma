"""
path: /project/frontend/map_editor/render/scene_bridge.py
Назначение: Синтетический PerceivedScene из campaign-JSON редактора —
    задник игрового вида для F12-редактора интерфейса (MODE_UIWORKBENCH).
    Чистая проекция статических данных редактора (стены/комнаты/NPC/спавн)
    в презентационные структуры игры (фронтенд-копии game_types, duck typing).
    Ничего не вычисляет, не симулирует, бэкенда не касается.
Зависимости: game_types (frontend root)
Основные сущности: build_perceived_scene
"""

from game_types import PerceivedEntity, PerceivedScene


def build_perceived_scene(core):
    """Возвращает (scene, walls, obstacles, floor_rects, scene_w, scene_h,
    player_xy) или None, если локация не открыта. DIAG-зонд — снять после
    первого прогона (Часть VIII.5: формат walls/rooms подтверждается
    рантаймом, не угадывается)."""
    loc = core.dm.locations.get(core.current_file) if core.current_file else None
    if not loc:
        return None
    size = loc.get("size", {})
    scene_w = float(size.get("w", 20.0))
    scene_h = float(size.get("h", 15.0))


    # Стены: только записи с ожидаемым рендером контрактом (x1/y1/x2/y2);
    # чужой формат отсекается — не падаем (зонд покажет фактический).
    walls = [w for w in loc.get("walls", [])
             if isinstance(w, dict) and all(k in w for k in ("x1", "y1", "x2", "y2"))]

    # Комнаты → floor_rects [(ox, oy, w, h)]; fallback — весь пол.
    # Формат комнат подтверждён зондом: x/y/width/height напрямую.
    floor_rects = []
    for r in loc.get("rooms", []):
        _x, _y = r.get("x", 0.0), r.get("y", 0.0)
        _w, _h = r.get("width", 0.0), r.get("height", 0.0)
        if _w and _h:
            floor_rects.append((float(_x), float(_y), float(_w), float(_h)))
    if not floor_rects:
        floor_rects = [(0.0, 0.0, scene_w, scene_h)]

    _name_by_id = {n["id"]: n.get("name", n["id"])
                   for n in getattr(core, "_npc_list", [])}
    entities = []
    for npc in loc.get("npcs", []):
        ref = npc.get("ref_id", "")
        pos = npc.get("position", {})
        entities.append(PerceivedEntity(
            entity_id=ref,
            entity_type="npc",
            x=float(pos.get("x", 0.0)),
            y=float(pos.get("y", 0.0)),
            visible=True,
            clarity=1.0,
            display_name=_name_by_id.get(ref, ref),
            recognition_confidence=1.0,
        ))

    spawn = loc.get("player_spawn") or {}
    player_xy = (float(spawn.get("x", scene_w / 2.0)),
                 float(spawn.get("y", scene_h / 2.0)))

    scene = PerceivedScene(location_id=core.current_file or "editor", entities=entities)
    return scene, walls, [], floor_rects, scene_w, scene_h, player_xy