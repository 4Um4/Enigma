from __future__ import annotations

# backend/app/services/spatial/graph_compiler.py
# Назначение: Компилирует editor JSON → runtime graph + alias_map
# Читает nodes из editor JSON напрямую. Сохраняет абсолютные x, y.
# Генерирует канонические ID: "location_id:editor_id"
# Строит alias_map для обратной совместимости: {"bar_area": "tavern_silver_wolf:bar_area"}
# Зависимости: app.models.spatial_contracts, app.services.spatial.role_resolver, stdlib
"""
- Добавить поддержку editor_tags, когда UI будет их отдавать
- В будущем: поддержка многоязычных лейблов (сейчас только русский и английский) — может потребоваться более сложная NLP-логика в RoleResolver
- Возможно, добавить в alias_map обратные ссылки для удобства (canonical_id → editor_id), если это будет нужно для UI
- В будущем можно добавить поддержку дополнительных типов узлов из editor JSON (например, "obstacle", "spawn_point") с соответствующими ролями
"""


import json
import logging
from pathlib import Path
from app.errors import SimulationIntegrityError
import math
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple
from app.models.spatial_contracts import NodeRef, NodeRole
from app.services.spatial.role_resolver import resolve_role

logger = logging.getLogger(__name__)

# ADR-121: Role-based legacy aliases — модульная константа (общая для обоих слоёв)
# Schedule/FLEE генерирует "bed", "bar_area" — эти имена должны резолвиться
# в канонические ID графа через alias_map
_ROLE_LEGACY_ALIASES: Dict[NodeRole, Set[str]] = {
    NodeRole.ENTRANCE: {"entrance", "entry"},
    NodeRole.BAR: {"bar_area", "behind_bar", "bar"},
    NodeRole.BED: {"bed", "sleeping_area"},
    NodeRole.TABLE: {"table_area", "dining"},
    NodeRole.WORKBENCH: {"workshop", "forge"},
    NodeRole.MARKET: {"market_area", "shop"},
}

# Корень проекта (Enigma/) — динамическое определение от расположения файла
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


from typing import Any, Dict, List, Set, Tuple
def compile_graph(
    editor_data: Dict[str, Any],
    location_id: str,
    level: Optional[str] = None,
) -> Tuple[
    Dict[str, NodeRef],
    Dict[str, Set[str]],
    Dict[str, str],
    Dict[str, Dict[str, Any]],
    Dict[str, List[Tuple[float, float]]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """Компилирует editor JSON в runtime graph + alias_map.

    Аргументы:
        editor_data: словарь из editor JSON (с ключами "nodes", "passages")
        location_id: идентификатор локации (напр. "tavern_silver_wolf")
        level: вертикальный уровень (ground, basement, floor_2)

    Возвращает:
        (graph, alias_map)
        graph: dict[canonical_id, NodeRef]
        alias_map: dict[legacy_id, canonical_id]
    """
    if not editor_data:
        logger.error(
            f"[GRAPH_COMPILER] editor_data is None для {location_id}. Возвращаем пустой граф."
        )
        return {}, {}, {}, {}, {}, [], [], []

    graph: Dict[str, NodeRef] = {}
    connections: Dict[str, Set[str]] = {}
    alias_map: Dict[str, str] = {}

    # ADR-121: Двухслойная топология
    # "nodes" (dict) — навигационная топология (точки пути + связи между ними)
    # "rooms" (list) — физические контейнеры (bounding boxes для LOS/коллизий)
    # Оба слоя существуют одновременно и компилируются параллельно.
    # Ни один слой не деградирует при наличии другого.
    nodes_raw = editor_data.get("nodes") or {}
    rooms_raw = editor_data.get("rooms")
    _has_nav = isinstance(nodes_raw, dict) and bool(nodes_raw)
    _has_rooms = isinstance(rooms_raw, (list, dict)) and bool(rooms_raw)

    # ── Layer 1: Навигационная топология (nodes) ──────────────────
    # Навигационные узлы имеют точные координаты и явные связи.
    # Это первичный слой для pathfinding и семантического резолва.
    if _has_nav:
        for node_id, node_data in nodes_raw.items():
            if not isinstance(node_data, dict):
                continue
            canonical_id = f"{location_id}:{node_id}"
            nx = node_data.get("x", 0.0)
            ny = node_data.get("y", 0.0)
            node_label = node_data.get("label", node_data.get("name", node_id))

            node_ref = NodeRef(
                node_id=canonical_id,
                x=nx,
                y=ny,
                role=resolve_role(
                    node_label=node_label,
                    editor_type=node_data.get("type"),
                    editor_tags=node_data.get("tags", []),
                    node_id=node_id,
                ),
                tags=node_data.get("tags", []),
                zone_id=location_id,
                level=level,
            )
            graph[canonical_id] = node_ref
            alias_map[node_id] = canonical_id

            # name-alias (label → canonical_id)
            if node_label and node_label.lower() not in alias_map:
                alias_map[node_label.lower()] = canonical_id

            # Явные алиасы из editor JSON
            for alias in node_data.get("aliases", []):
                alias_map[alias.lower()] = canonical_id

            # ADR-114: Role-based legacy aliases
            _legacy_names = _ROLE_LEGACY_ALIASES.get(node_ref.role, set())
            for _alias in _legacy_names:
                if _alias not in alias_map:
                    alias_map[_alias] = canonical_id

    # ── Layer 2: Физические контейнеры (rooms) ────────────────────
    # Комнаты — bounding boxes для LOS, коллизий, контейнмента.
    # Добавляются в граф ТОЛЬКО если не представлены навигационными узлами.
    # Комнаты с навигационным представлением обогащают alias_map своими именами.
    rooms: Dict[str, dict] = {}
    if _has_rooms:
        if isinstance(rooms_raw, list):
            for item in rooms_raw:
                if isinstance(item, dict):
                    rid = item.get("id", item.get("room_id", f"room_{len(rooms)}"))
                    rooms[rid] = item
        elif isinstance(rooms_raw, dict):
            rooms = dict(rooms_raw)

        if rooms:
            # ADR-091: Фильтрация container-комнат (внешних границ)
            room_ids = list(rooms.keys())
            container_ids = set()
            for i in range(len(room_ids)):
                for j in range(len(room_ids)):
                    if i == j:
                        continue
                    r1 = rooms[room_ids[i]]
                    r2 = rooms[room_ids[j]]
                    x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
                    x1_max = x1_min + r1.get("width", 0.0)
                    y1_max = y1_min + r1.get("height", 0.0)
                    x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
                    x2_max = x2_min + r2.get("width", 0.0)
                    y2_max = y2_min + r2.get("height", 0.0)
                    if (
                        x1_min <= x2_min + 0.5
                        and y1_min <= y2_min + 0.5
                        and x1_max >= x2_max - 0.5
                        and y1_max >= y2_max - 0.5
                    ):
                        container_ids.add(room_ids[i])
                        logger.warning(
                            f"[GRAPH_COMPILER] Комната '{room_ids[i]}' содержит "
                            f"'{room_ids[j]}'. Это внешняя граница — исключена."
                        )
            if container_ids:
                rooms = {
                    rid: data for rid, data in rooms.items() if rid not in container_ids
                }

    if not _has_nav and not rooms:
        logger.warning(f"[GRAPH_COMPILER] Нет узлов (rooms/nodes) в {location_id}")
        return {}, {}, {}, {}, {}, [], [], []

    # ── Извлечение физической геометрии (ETKE-IK v1) ─────────────
    # Геометрия комнат нужна WorldTopologyProvider для вычисления AffordanceVector.
    rooms_geometry: Dict[str, List[Tuple[float, float]]] = {}
    for room_id, room_data in rooms.items():
        polygon = room_data.get("polygon")
        if polygon and isinstance(polygon, list) and len(polygon) >= 3:
            rooms_geometry[room_id] = [(float(p[0]), float(p[1])) for p in polygon]
        else:
            rx = room_data.get("x", 0.0)
            ry = room_data.get("y", 0.0)
            rw = room_data.get("width") or room_data.get("w") or 0.0
            rh = room_data.get("height") or room_data.get("h") or 0.0
            if rw > 0 and rh > 0:
                rooms_geometry[room_id] = [
                    (rx, ry),
                    (rx + rw, ry),
                    (rx + rw, ry + rh),
                    (rx, ry + rh),
                ]

    # ── Room → graph (orphan rooms + name enrichment) ──────────────
    # Для каждой комнаты проверяем: есть ли навигационный узел,
    # представляющий эту комнату? Если да — обогащаем alias_map.
    # Если нет — добавляем как самостоятельный узел (обратная совместимость).
    if rooms:
        for room_id, room_data in rooms.items():
            canonical_id = f"{location_id}:{room_id}"
            room_name = room_data.get("name", "")

            # Стратегия маппинга: name → nav node (по label) или position → nav node (по центроиду)
            _nav_match = None

            # 1) Точное совпадение имени комнаты с label навигационного узла
            if _has_nav and room_name:
                # N5-style FIX: Гарантируем, что nodes_raw — это dict
                if not isinstance(nodes_raw, dict):
                    nodes_raw = {}
                
                for nid, ndata in nodes_raw.items():
                    if not isinstance(ndata, dict):
                        continue
                    
                    # Безопасно извлекаем значение, по умолчанию пустая строка
                    nav_label_raw = ndata.get("label", ndata.get("name", ""))
                    # Явно приводим к строке, так как JSON может содержать числа или списки
                    nav_label = str(nav_label_raw) if nav_label_raw else ""
                    
                    if nav_label and nav_label.lower() == str(room_name).lower():
                        _nav_match = f"{location_id}:{nid}"
                        break

            # 2) Центроид комнаты рядом с навигационным узлом
            if _nav_match is None and _has_nav:
                rx = room_data.get("x", 0.0)
                ry = room_data.get("y", 0.0)
                rw = room_data.get("width") or room_data.get("w") or 0.0
                rh = room_data.get("height") or room_data.get("h") or 0.0
                room_cx = rx + rw / 2
                room_cy = ry + rh / 2
                for nid, ndata in nodes_raw.items():
                    if not isinstance(ndata, dict):
                        continue
                    nav_x = ndata.get("x", 0.0)
                    nav_y = ndata.get("y", 0.0)
                    if abs(room_cx - nav_x) < 1.0 and abs(room_cy - nav_y) < 1.0:
                        _nav_match = f"{location_id}:{nid}"
                        break

            if canonical_id in graph or _nav_match:
                # Комната уже представлена навигационным узлом — enrich alias_map
                _target = _nav_match or canonical_id
                if room_name and room_name.lower() not in alias_map:
                    alias_map[room_name.lower()] = _target
                for alias in room_data.get("aliases", []):
                    if alias.lower() not in alias_map:
                        alias_map[alias.lower()] = _target
                continue

            # ADR-S91.1: Навигационная топология (nodes) — первичный источник графа.
            # Если есть nodes, orphan rooms (без навигационного узла) — это физические контейнеры (LOS/коллизии),
            # а не точки пути. Добавление их в graph создаёт изолированные компоненты.
            if _has_nav:
                logger.debug(
                    f"[GRAPH_COMPILER] Orphan room '{room_id}' пропущена (nav layer active)."
                )
                continue

            # Orphan room — нет навигационного представления (fallback mode: graph = rooms)
            rx = room_data.get("x", 0.0)
            ry = room_data.get("y", 0.0)
            rw = room_data.get("width") or room_data.get("w") or 0.0
            rh = room_data.get("height") or room_data.get("h") or 0.0
            center_x = rx + rw / 2
            center_y = ry + rh / 2

            node_ref = NodeRef(
                node_id=canonical_id,
                x=center_x,
                y=center_y,
                role=resolve_role(
                    node_label=room_data.get("name", room_id),
                    editor_type=room_data.get("type"),
                    node_id=room_id,
                ),
                tags=room_data.get("tags", []),
                zone_id=location_id,
                level=level,
            )
            graph[canonical_id] = node_ref
            alias_map[room_id] = canonical_id

            if (
                room_name
                and room_name != room_id
                and room_name.lower() not in alias_map
            ):
                alias_map[room_name.lower()] = canonical_id

            for alias in room_data.get("aliases", []):
                alias_map[alias.lower()] = canonical_id

            _legacy_names = _ROLE_LEGACY_ALIASES.get(node_ref.role, set())
            for _alias in _legacy_names:
                if _alias not in alias_map:
                    alias_map[_alias] = canonical_id

    # ── Компиляция связей ──────────────────────────────────────────
    if _has_nav:
        # Навигационные связи из per-node connections (первичный источник)
        for node_id, node_data in nodes_raw.items():
            if not isinstance(node_data, dict):
                continue
            from_canonical = alias_map.get(node_id, f"{location_id}:{node_id}")
            for target_id in node_data.get("connections", []):
                to_canonical = alias_map.get(target_id, f"{location_id}:{target_id}")
                if from_canonical in graph and to_canonical in graph:
                    connections.setdefault(from_canonical, set()).add(to_canonical)
                    connections.setdefault(to_canonical, set()).add(from_canonical)
                else:
                    logger.warning(
                        f"[GRAPH_COMPILER] Пропуск связи {node_id}→{target_id}: "
                        f"узел не найден в графе"
                    )
    else:
        # Обратная совместимость: passages/connections из editor JSON
        passages = editor_data.get("passages", editor_data.get("connections", []))
        if not passages and len(rooms) > 1:
            passages = _infer_connections_from_adjacency(rooms)

        for passage in passages:
            from_legacy = passage.get("from") or ""
            to_legacy = passage.get("to") or ""
            if not from_legacy or not to_legacy:
                continue
            from_canonical = alias_map.get(from_legacy, f"{location_id}:{from_legacy}")
            to_canonical = alias_map.get(to_legacy, f"{location_id}:{to_legacy}")
            if from_canonical in graph and to_canonical in graph:
                connections.setdefault(from_canonical, set()).add(to_canonical)
                if not passage.get("one_way", False):
                    connections.setdefault(to_canonical, set()).add(from_canonical)
            else:
                logger.warning(
                    f"[GRAPH_COMPILER] Пропуск связи {from_legacy}→{to_legacy}: "
                    f"узел не найден в графе"
                )

    # ── Layer 3: Boundary Nodes (ДОЛГ 6.2) ──────────────────────────
    # Читаем adjacency и создаём виртуальные узлы выхода из чанка.
    # Boundary node — семантическая точка перехода в соседний чанк.
    boundary_map: Dict[str, dict] = {}
    adjacency = editor_data.get("adjacency")
    if isinstance(adjacency, dict) and adjacency and graph:
        _create_boundary_nodes(
            graph=graph,
            connections=connections,
            alias_map=alias_map,
            boundary_map=boundary_map,
            location_id=location_id,
            adjacency=adjacency,
            origin=editor_data.get("origin", {"x": 0.0, "y": 0.0}),
            size=editor_data.get("size", {"w": 10.0, "h": 10.0}),
        )

    _validate_connectivity(graph, connections, location_id)

    logger.info(
        f"[GRAPH_COMPILER] {location_id}: compiled {len(graph)} nodes, "
        f"{sum(len(v) for v in connections.values()) // 2} edges, "
        f"{len(alias_map)} aliases, "
        f"{len(boundary_map)} boundaries (nav={_has_nav}, rooms={_has_rooms})"
    )

    # ДОЛГ 6.2: _legacy_compile не имеет adjacency → boundary_map пуста
    # ETKE-IK v1: возвращаем rooms_geometry 5-м элементом
    # ADR-O-324: возвращаем spatial_walls и spatial_obstacles 6-м и 7-м элементом
    spatial_walls, spatial_obstacles = _build_spatial_data(editor_data)

    # S129 FIX: P4-02 — Геометрическая валидация графа. Ловим рёбра, проходящие сквозь стены.
    _validate_navigation_geometry(graph, connections, spatial_walls, spatial_obstacles, location_id)

    # ADR-O-330: Извлекаем физические объекты с аффордансами (кровати, палатки, верстаки)
    affordance_objects = _extract_affordance_objects(editor_data)
    return graph, connections, alias_map, boundary_map, rooms_geometry, spatial_walls, spatial_obstacles, affordance_objects

def _validate_navigation_geometry(
    graph: Dict[str, Any],
    connections: Dict[str, set],
    spatial_walls: List[Dict[str, Any]],
    spatial_obstacles: List[Dict[str, Any]],
    location_id: str,
) -> None:
    """S129: Проверяет, что навигационные рёбра не пересекают физическую геометрию."""
    for from_id, neighbors in connections.items():
        from_node = graph.get(from_id)
        if not from_node:
            continue

        # S137.1: Собираем заблокированные рёбра, чтобы удалить их из графа.
        _blocked_edges = set()
        for to_id in neighbors:
            # Проверяем только A -> B, чтобы избежать дублирования логов (B -> A)
            if from_id > to_id:
                continue

            to_node = graph.get(to_id)
            if not to_node:
                continue

            is_blocked = False
            _is_wall_block = False  # S-142: Честный флаг блокировки стены
            _blocker = ""
            # 1. Проверка стен
            for wall in spatial_walls:
                if _segments_intersect(
                    from_node.x, from_node.y, to_node.x, to_node.y,
                    wall["x1"], wall["y1"], wall["x2"], wall["y2"]
                ):
                    is_blocked = True
                    _is_wall_block = True
                    _blocker = f"WALL {wall}"
                    break

            # 2. Проверка препятствий (только walk=false)
            if not is_blocked:
                for obs in spatial_obstacles:
                    if not obs.get("passability", {}).get("walk", True):
                        if _line_rect_intersect(
                            from_node.x, from_node.y, to_node.x, to_node.y,
                            obs["x"], obs["y"], obs["w"], obs["h"]
                        ):
                            # S140: Не блокируем ребро, если препятствие можно перепрыгнуть.
                            # LocalTraversalPlanner построит маршрут с JUMP-сегментом.
                            if not obs.get("passability", {}).get("jump_over", False):
                                is_blocked = True
                                _blocker = f"OBSTACLE {obs.get('id', obs)}"
                                break

            if is_blocked:
                # S-142 Topology Gate: Пересечение неразрезанной стены — критическая ошибка карты.
                # Стена уже разрезана дверями (wall_id) на этапе _build_spatial_data.
                # Если ребро пересекает оставшийся сегмент — это архитектурная ошибка карты.
                if _is_wall_block:
                    import os
                    logger.error(
                        f"[MAP_TOPOLOGY_DEFECT] Edge {from_id} -> {to_id} crosses wall. "
                        f"Removing edge. Blocker: {_blocker}. Set ENIGMA_STRICT_MAP=1 to crash."
                    )
                    if os.environ.get("ENIGMA_STRICT_MAP") == "1":
                        raise SimulationIntegrityError(
                            invariant_id="INV-TOPOLOGY-WALL-CROSS",
                            message=f"Edge {from_id} -> {to_id} crosses solid wall. Missing door wall_id? Blocker: {_blocker}",
                            suspect_files=[__file__],
                            file=__file__, line=385,
                        )
                print(f"[DEBUG_GEO_BLOCK] {from_id} ({from_node.x},{from_node.y}) -> {to_id} ({to_node.x},{to_node.y}) blocked by {_blocker}")
                logger.warning(
                    f"[SPATIAL_VALIDATION] {location_id}: edge {from_id} -> {to_id} "
                    f"is geometrically blocked! Edge removed from graph."
                )
                _blocked_edges.add((from_id, to_id))
                _blocked_edges.add((to_id, from_id))

        # S140 FIX: Фактическое удаление заблокированных рёбер из графа.
        for _src, _tgt in _blocked_edges:
            if _src in connections and _tgt in connections[_src]:
                connections[_src].remove(_tgt)

def _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4, eps=1e-6) -> bool:
    """Определение пересечения отрезков с ε-толерантностью (V8-SP-2 FIX)."""
    def _cross(ox, oy, ax, ay, bx, by):
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)
    d1 = _cross(x3, y3, x4, y4, x1, y1)
    d2 = _cross(x3, y3, x4, y4, x2, y2)
    d3 = _cross(x1, y1, x2, y2, x3, y3)
    d4 = _cross(x1, y1, x2, y2, x4, y4)
    if ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and \
       ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)):
        return True
    return False

def _line_rect_intersect(x1, y1, x2, y2, rx, ry, rw, rh) -> bool:
    """Проверка пересечения отрезка с прямоугольником (AABB)."""
    # Если одна из точек внутри — уже пересечение
    if (rx <= x1 <= rx + rw and ry <= y1 <= ry + rh) or (rx <= x2 <= rx + rw and ry <= y2 <= ry + rh):
        return True
    # Проверка пересечения с 4 сторонами прямоугольника
    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx + rw, ry):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx + rw, ry, rx + rw, ry + rh):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry + rh, rx + rw, ry + rh):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx, ry + rh):
        return True
    return False


def _extract_affordance_objects(editor_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Извлекает физические объекты с аффордансами из editor JSON.

    ADR-O-330: Кровать — это физический объект, а не навигационный узел.
    Возвращает список словарей с координатами и типами аффордансов.
    """
    objects = editor_data.get("objects", [])
    if not objects:
        return []

    # Временный детерминированный маппинг типа объекта → аффордансы
    _TYPE_TO_AFFORDANCE = {
        "bed": ["sleep", "rest"],
        "tent": ["sleep", "rest"],
        "forge": ["forge", "work"],
        "workbench": ["work", "craft"],
    }

    affordance_objects = []
    for obj in objects:
        obj_type = obj.get("type", "")
        affordances = _TYPE_TO_AFFORDANCE.get(obj_type)
        if not affordances:
            continue

        pos = obj.get("position", {})
        if not pos:
            continue

        affordance_objects.append({
            "object_id": obj.get("id", obj_type),
            "source_type": obj_type,
            "affordances": affordances,
            "x": float(pos.get("x", 0.0)),
            "y": float(pos.get("y", 0.0)),
            "tags": obj.get("tags", []),
            "destroyed": obj.get("destroyed", False),
        })
    return affordance_objects


def _find_walls_for_door(editor_data: Dict[str, Any], door: Dict[str, Any]) -> List[str]:
    """S143 §1: Авто-поиск ВСЕХ стен для двери по координатам.
    Возвращает список wall_id, на которых лежит дверь (perp_dist <= 0.5).
    Решает проблему дублирующихся стен между комнатами.
    """
    door_pos = door.get("position", {})
    px, py = door_pos.get("x", 0), door_pos.get("y", 0)
    
    found_walls: List[str] = []
    threshold = 0.5 # Порог дистанции
    
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
        
        if perp_dist <= threshold:
            found_walls.append(wid)
            
    return found_walls


def _build_spatial_data(editor_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Извлекает spatial_walls и spatial_obstacles из editor JSON.

    ADR-O-324: Перенесено из SceneStateManager для обеспечения Single Spatial Authority.
    SpatialService теперь владеет геометрией стен и может валидировать сегменты пути.
    """
    spatial_walls: list[dict] = []
    spatial_obstacles: list[dict] = []

    if not editor_data:
        return spatial_walls, spatial_obstacles

    # Разрезаем стены проёмами (двери)
    # S143 FIX §1: Дверь разрезает ВСЕ стены, проходящие через её координаты (решает проблему дубликатов стен)
    wall_openings: dict[str, list[dict]] = {}
    
    # 1. Читаем проёмы из objects (двери-переходы между локациями)
    for obj in editor_data.get("objects", []):
        if not obj.get("passability", {}).get("walk", True):
            continue # Непроходимые объекты не могут быть дверными проёмами
        if obj.get("type") not in ("door", "door_transition"):
            continue
            
        # S143: Ищем ВСЕ стены, на которых лежит дверь
        walls_for_door = _find_walls_for_door(editor_data, obj)
        
        # Fallback: если явный wall_id указан, добавляем его, если не нашли по координатам
        explicit_wall_id = obj.get("wall_id") or obj.get("properties", {}).get("wall_id")
        if not explicit_wall_id:
            rot = obj.get("rotation")
            if isinstance(rot, str) and rot.startswith("wall_"):
                explicit_wall_id = rot
                
        if explicit_wall_id and explicit_wall_id not in walls_for_door:
            walls_for_door.append(explicit_wall_id)
            
        for wid in walls_for_door:
            wall_openings.setdefault(wid, []).append(obj)

    # 2. Читаем проёмы из passages (внутренние двери, созданные инструментом Passage)
    for p in editor_data.get("passages", []):
        wall_id = p.get("wall_id")
        if wall_id:
            wall_openings.setdefault(wall_id, []).append(p)

    for wall in editor_data.get("walls", []):
        wall_id = wall.get("id")
        openings = wall_openings.get(wall_id, [])
        segments = _split_wall_by_openings(wall, openings)
        if wall_id == "wall_7":
            logger.debug(f"[DIAG_SPLIT] wall_7 openings={len(openings)} segments={len(segments)}")
            for seg in segments:
                logger.debug(f"[DIAG_SPLIT_SEG] {seg}")
        spatial_walls.extend(segments)

    # V8-SP-9 FIX: print() заменены на logger.debug() для чистоты stdout в production
    logger.debug(f"[DIAG_RETURN] spatial_walls_count={len(spatial_walls)}")
    for w in spatial_walls:
        if w.get("x1") == 14.0 and w.get("x2") == 14.0 and w.get("y1") == 8.0 and w.get("y2") == 0.5:
            logger.debug(f"[DIAG_RETURN_BROKEN_WALL] {w}")

    # Препятствия с passability и blocks_los
    for obj in editor_data.get("objects", []):
        # S-01 FIX: Двери (type=door/door_transition) обрабатываются как проёмы в стенах выше.
        # Они не должны быть физическими препятствиями, иначе блокируют путь даже при разрезе стены.
        if obj.get("type") in ("door", "door_transition"):
            continue
        if obj.get("passability", {}).get("walk", True):
            continue
        pos = obj.get("position", {})
        size = obj.get("size", {})
        if pos and size:
            # S-01 FIX: Уменьшаем bounding box препятствий на 0.2м (0.1м с каждой стороны).
            # Это даёт NPC "зазор" для прохождения вплотную к мебели, не задевая её математически.
            _w = max(0.0, size.get("w", 0) - 0.2)
            _h = max(0.0, size.get("h", 0) - 0.2)
            spatial_obstacles.append(
                {
                    "x": pos["x"] - _w / 2,
                    "y": pos["y"] - _h / 2,
                    "w": _w,
                    "h": _h,
                    "id": obj.get("id", ""),
                    "type": obj.get("type", "decoration"),
                    "blocks_los": obj.get("cover", 0) >= 0.8,
                    "passability": obj.get("passability", {}),
                }
            )

    return spatial_walls, spatial_obstacles


def _split_wall_by_openings(wall: dict, openings: list[dict]) -> list[dict]:
    """Разрезает сегмент стены на части, исключая проёмы (двери, проходы)."""
    if not openings:
        return [
            {
                "x1": wall["x1"],
                "y1": wall["y1"],
                "x2": wall["x2"],
                "y2": wall["y2"],
            }
        ]

    x1, y1 = wall["x1"], wall["y1"]
    x2, y2 = wall["x2"], wall["y2"]

    dx = x2 - x1
    dy = y2 - y1
    wall_len = (dx * dx + dy * dy) ** 0.5
    if wall_len == 0:
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]

    # единичный вектор вдоль стены
    ux = dx / wall_len
    uy = dy / wall_len

    # Собираем интервалы проёмов вдоль стены (в метрах от начала стены)
    gaps = []
    for op in openings:
        pos = op.get("position", {})
        size = op.get("size", {})
        px, py = pos.get("x", 0), pos.get("y", 0)
        # Вектор от начала стены до центра объекта
        vx, vy = px - x1, py - y1
        # Расстояние вдоль стены от начала
        dist_along = vx * ux + vy * uy
        # Перпендикулярное расстояние (объект должен быть на стене)
        perp_dist = abs(vx * (-uy) + vy * ux)

        if perp_dist > 0.5:
            continue

        w = size.get("w", 0)
        h = size.get("h", 0)
        # Проекция размера объекта на стену
        half_len = (abs(w * ux) + abs(h * uy)) / 2
        gap_start = max(0, dist_along - half_len)
        gap_end = min(wall_len, dist_along + half_len)
        if gap_end > gap_start:
            gaps.append((gap_start, gap_end))

    if not gaps:
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]

    # Сортируем проёмы и объединяем перекрывающиеся
    gaps.sort()
    merged = [gaps[0]]
    for start, end in gaps[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Строим сегменты стены между проёмами
    segments = []
    current = 0.0
    for start, end in merged:
        if start > current:
            segments.append({
                "x1": x1 + ux * current,
                "y1": y1 + uy * current,
                "x2": x1 + ux * start,
                "y2": y1 + uy * start,
            })
        current = end

    if current < wall_len:
        segments.append({
            "x1": x1 + ux * current,
            "y1": y1 + uy * current,
            "x2": x2,
            "y2": y2,
        })

    return segments


def load_editor_json(
    campaign_id: str,
    location_id: str,
    search_dirs: Optional[List[Path]] = None
) -> Optional[Dict[str, Any]]:
    """Загружает JSON-файл локации.

    Поиск: search_dirs (если переданы) -> campaign_dir/locations -> campaign_dir.
    Сопоставление: по имени файла (location_id.json) или по полю location_id/id внутри JSON.
    Включает fuzzy match для случаев вроде "tavern" vs "tavern_silver_wolf".
    """
    # 1. Формируем список директорий для поиска
    dirs_to_search: List[Path] = []
    if search_dirs:
        dirs_to_search.extend(search_dirs)

    project_root = Path(__file__).resolve().parents[4]
    campaign_dir = project_root / "frontend" / "map_editor" / "campaigns" / campaign_id
    dirs_to_search.append(campaign_dir / "locations")
    dirs_to_search.append(campaign_dir)

    # 2. Ищем файл
    for d in dirs_to_search:
        if not d.exists():
            continue

        # Пробуем точное совпадение имени файла
        loc_file = d / f"{location_id}.json"
        if loc_file.exists():
            try:
                with open(loc_file, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[GRAPH_COMPILER] Failed to parse JSON from {loc_file}: {e}")

        # Пробуем искать по содержимому (поле location_id или id)
        for json_file in d.glob("*.json"):
            if json_file.name == "campaign.json":
                continue
            try:
                with open(json_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    file_loc_id = data.get("location_id", data.get("id", ""))
                    if file_loc_id == location_id:
                        return data
                    # Fuzzy match для случаев вроде "tavern" vs "tavern_silver_wolf"
                    if file_loc_id and (file_loc_id in location_id or location_id in file_loc_id):
                        return data
            except Exception as e:
                logger.error(f"[GRAPH_COMPILER] Failed to parse JSON from {json_file}: {e}")

    # 3. Fallback: campaign.json (старый формат, где всё в одном файле)
    campaign_file = campaign_dir / "campaign.json"
    if campaign_file.exists():
        try:
            with open(campaign_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                if "locations" in data:
                    for loc in data["locations"]:
                        if loc.get("id") == location_id or loc.get("location_id") == location_id:
                            return loc
                if data.get("id") == location_id or data.get("location_id") == location_id:
                    return data
        except Exception as e:
            logger.error(f"[GRAPH_COMPILER] Failed to parse JSON from {campaign_file}: {e}")

    logger.warning(f"[GRAPH_COMPILER] No map file found for {campaign_id}/{location_id}")
    return None

def _validate_connectivity(graph: Dict[str, NodeRef], connections: Dict[str, Set[str]], location_id: str) -> None:
    """Проверяет связность графа. Логирует предупреждения об изолированных узлах."""
    if not graph:
        return

    visited: Set[str] = set()
    queue = deque([next(iter(graph))])

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in connections.get(node, set()):
            if neighbor not in visited:
                queue.append(neighbor)

    if len(visited) != len(graph):
        isolated = set(graph.keys()) - visited
        logger.warning(f"[GRAPH_COMPILER] Изолированные узлы в {location_id}: {isolated}")


def _create_boundary_nodes(
    graph: Dict[str, NodeRef],
    connections: Dict[str, Set[str]],
    alias_map: Dict[str, str],
    boundary_map: Dict[str, dict],
    location_id: str,
    adjacency: Dict[str, Any],
    origin: Dict[str, float],
    size: Dict[str, float],
) -> None:
    """Создаёт виртуальные boundary nodes для перехода в соседние чанки (ДОЛГ 6.2)."""
    _OPPOSITE_DIRS = {"north": "south", "south": "north", "east": "west", "west": "east"}

    if not graph:
        return

    _ox = float(origin.get("x", 0.0))
    _oy = float(origin.get("y", 0.0))
    _w = float(size.get("w", 10.0))
    _h = float(size.get("h", 10.0))

    # P4-01A: Геометрические центры границ локации
    _DIR_TO_XY = {
        "north": (_ox + _w / 2.0, _oy + _h - 1.0),
        "south": (_ox + _w / 2.0, _oy + 1.0),
        "east": (_ox + _w - 1.0, _oy + _h / 2.0),
        "west": (_ox + 1.0, _oy + _h / 2.0),
    }

    for direction, neighbor_loc_id in adjacency.items():
        if not isinstance(neighbor_loc_id, str):
            continue

        # V8-SP-15 FIX: Смещаем anchor на 1 метр внутрь локации.
        # Иначе boundary node оказывается за стеной (снаружи), и валидатор блокирует пути к нему.
        _DIR_OFFSETS = {
            "east":  (_ox + _w - 1.0, _oy + _h / 2.0),
            "west":  (_ox + 1.0,      _oy + _h / 2.0),
            "north": (_ox + _w / 2.0, _oy + _h - 1.0),
            "south": (_ox + _w / 2.0, _oy + 1.0),
        }
        _bx, _by = _DIR_OFFSETS.get(direction, (_ox + _w / 2.0, _oy + _h / 2.0))

        # P4-01A FIX: Ищем ближайший навигационный узел к границе (исключая другие boundary nodes)
        _nearest_node = None
        _min_dist_sq = float('inf')
        for node in graph.values():
            if node.role == NodeRole.BOUNDARY:
                continue
            _dx = node.x - _bx
            _dy = node.y - _by
            _dist_sq = _dx * _dx + _dy * _dy
            if _dist_sq < _min_dist_sq:
                _min_dist_sq = _dist_sq
                _nearest_node = node

        if not _nearest_node:
            logger.warning(f"[GRAPH_COMPILER] No navigation node found to attach boundary {direction} in {location_id}")
            continue

        boundary_id = f"{location_id}:exit_{direction}"
        # V8-SP-15 FIX: Если в JSON уже есть узел exit_east, используем его координаты.
        # Иначе используем anchor границы.
        _existing_node = graph.get(boundary_id)
        _final_x = _existing_node.x if _existing_node else _bx
        _final_y = _existing_node.y if _existing_node else _by

        boundary_node = NodeRef(
            node_id=boundary_id,
            x=_final_x,
            y=_final_y,
            role=NodeRole.BOUNDARY,
            tags=["boundary:exit"],
            zone_id=location_id,
        )

        graph[boundary_id] = boundary_node
        alias_map[f"exit_{direction}"] = boundary_id

        # P4-01 FIX: Соединяем boundary node со всеми навигационными узлами в радиусе 3.0 м
        _CONNECTION_RADIUS = 3.0
        _connected_count = 0
        for node in graph.values():
            if node.node_id == boundary_id or node.role == NodeRole.BOUNDARY:
                continue
            _dx = node.x - _bx
            _dy = node.y - _by
            if (_dx * _dx + _dy * _dy) <= (_CONNECTION_RADIUS ** 2):
                connections.setdefault(node.node_id, set()).add(boundary_id)
                connections.setdefault(boundary_id, set()).add(node.node_id)
                _connected_count += 1

        if _connected_count == 0:
            # Fallback: если в радиусе 3м никого нет, цепляем хотя бы за ближайший
            connections.setdefault(_nearest_node.node_id, set()).add(boundary_id)
            connections.setdefault(boundary_id, set()).add(_nearest_node.node_id)
            _connected_count = 1

        logger.info(f"[GRAPH_COMPILER] boundary={direction} connected_to={_connected_count} nodes")

        _entry_dir = _OPPOSITE_DIRS.get(direction, direction)
        boundary_map[boundary_id] = {
            "neighbor_chunk": neighbor_loc_id,
            "node_id": boundary_id,
            "x": _bx,
            "y": _by,
            "direction": direction,
            "entry_direction": _entry_dir,
            "entry_node_hint": f"{neighbor_loc_id}:exit_{_entry_dir}"
        }


def _infer_connections_from_adjacency(
    rooms: Dict[str, dict], tolerance: float = 0.5
) -> List[dict]:
    """Выводит связи между комнатами на основе смежности их bounding box.
    Если две комнаты имеют общую стену (пересечение по оси > tolerance),
    между ними создаётся passage."""
    connections = []
    room_ids = list(rooms.keys())

    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            r1_id = room_ids[i]
            r2_id = room_ids[j]
            r1 = rooms[r1_id]
            r2 = rooms[r2_id]

            x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
            x1_max = x1_min + r1.get("width", 0.0)
            y1_max = y1_min + r1.get("height", 0.0)

            x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
            x2_max = x2_min + r2.get("width", 0.0)
            y2_max = y2_min + r2.get("height", 0.0)

            x_overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
            y_overlap = min(y1_max, y2_max) - max(y1_min, y2_min)

            if abs(x1_max - x2_min) < tolerance and y_overlap > tolerance:
                connections.append({"from": r1_id, "to": r2_id})
            elif abs(x2_max - x1_min) < tolerance and y_overlap > tolerance:
                connections.append({"from": r1_id, "to": r2_id})
            elif abs(y1_max - y2_min) < tolerance and x_overlap > tolerance:
                connections.append({"from": r1_id, "to": r2_id})
            elif abs(y2_max - y1_min) < tolerance and x_overlap > tolerance:
                connections.append({"from": r1_id, "to": r2_id})

    return connections
