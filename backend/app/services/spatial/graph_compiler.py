# backend/app/services/spatial/graph_compiler.py
# Назначение: Компилирует editor JSON → runtime graph + alias_map
# Читает nodes из editor JSON напрямую. Сохраняет абсолютные x, y.
# Генерирует канонические ID: "location_id:editor_id"
# Строит alias_map для обратной совместимости: {"bar_area": "tavern_silver_wolf:bar_area"}
# Зависимости: app.models.spatial_contracts, app.services.spatial.role_resolver, stdlib
"""
TODO:
- Добавить поддержку editor_tags, когда UI будет их отдавать
- В будущем: поддержка многоязычных лейблов (сейчас только русский и английский) — может потребоваться более сложная NLP-логика в RoleResolver
- Возможно, добавить в alias_map обратные ссылки для удобства (canonical_id → editor_id), если это будет нужно для UI
- В будущем можно добавить поддержку дополнительных типов узлов из editor JSON (например, "obstacle", "spawn_point") с соответствующими ролями
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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


def compile_graph(
    editor_data: dict,
    location_id: str,
    level: Optional[str] = None,
) -> Tuple[Dict[str, NodeRef], Dict[str, str]]:
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
        logger.error(f"[GRAPH_COMPILER] editor_data is None для {location_id}. Возвращаем пустой граф.")
        return {}, {}, {}, {}

    graph: Dict[str, NodeRef] = {}
    connections: Dict[str, Set[str]] = {}
    alias_map: Dict[str, str] = {}

    # ADR-121: Двухслойная топология
    # "nodes" (dict) — навигационная топология (точки пути + связи между ними)
    # "rooms" (list) — физические контейнеры (bounding boxes для LOS/коллизий)
    # Оба слоя существуют одновременно и компилируются параллельно.
    # Ни один слой не деградирует при наличии другого.
    nodes_raw = editor_data.get("nodes")
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
                    if (x1_min <= x2_min + 0.5 and y1_min <= y2_min + 0.5
                            and x1_max >= x2_max - 0.5 and y1_max >= y2_max - 0.5):
                        container_ids.add(room_ids[i])
                        logger.warning(
                            f"[GRAPH_COMPILER] Комната '{room_ids[i]}' содержит "
                            f"'{room_ids[j]}'. Это внешняя граница — исключена."
                        )
            if container_ids:
                rooms = {rid: data for rid, data in rooms.items() if rid not in container_ids}

    if not _has_nav and not rooms:
        logger.warning(f"[GRAPH_COMPILER] Нет узлов (rooms/nodes) в {location_id}")
        return {}, {}, {}, {}

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
                for nid, ndata in nodes_raw.items():
                    if not isinstance(ndata, dict):
                        continue
                    nav_label = ndata.get("label", ndata.get("name", ""))
                    if nav_label and nav_label.lower() == room_name.lower():
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
                logger.debug(f"[GRAPH_COMPILER] Orphan room '{room_id}' пропущена (nav layer active).")
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

            if room_name and room_name != room_id and room_name.lower() not in alias_map:
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
            from_legacy = passage.get("from")
            to_legacy = passage.get("to")
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
        )

    _validate_connectivity(graph, connections, location_id)

    logger.info(
        f"[GRAPH_COMPILER] {location_id}: compiled {len(graph)} nodes, "
        f"{sum(len(v) for v in connections.values()) // 2} edges, "
        f"{len(alias_map)} aliases, "
        f"{len(boundary_map)} boundaries (nav={_has_nav}, rooms={_has_rooms})"
    )

    # ДОЛГ 6.2: _legacy_compile не имеет adjacency → boundary_map пуста
    return graph, connections, alias_map, boundary_map
    rooms_raw = editor_data.get("rooms", editor_data.get("nodes", {}))
    
    # Map Editor отдаёт узлы как список [{id, x, y...}], компилятор ждёт словарь {id: {x, y...}}
    if isinstance(rooms_raw, list):
        rooms = {}
        for item in rooms_raw:
            if isinstance(item, dict):
                rid = item.get("id", item.get("room_id", f"node_{len(rooms)}"))
                rooms[rid] = item
    elif isinstance(rooms_raw, dict):
        rooms = rooms_raw
    else:
        logger.warning(f"[GRAPH_COMPILER] Неверный тип узлов в {location_id}: {type(rooms_raw)}")
        return {}, {}, {}, {}

    if not rooms:
        logger.warning(f"[GRAPH_COMPILER] Нет узлов (rooms/nodes) в {location_id}")
        return {}, {}, {}, {}

    # ADR-091: Фильтрация container-комнат (внешних границ от Map Editor)
    # Комната, полностью содержащая другую — это внешняя граница, не навигационная зона.
    room_ids = list(rooms.keys())
    container_ids = set()
    
    for i in range(len(room_ids)):
        for j in range(len(room_ids)):
            if i == j: continue
            r1 = rooms[room_ids[i]]
            r2 = rooms[room_ids[j]]
            
            x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
            x1_max = x1_min + r1.get("width", 0.0)
            y1_max = y1_min + r1.get("height", 0.0)
            
            x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
            x2_max = x2_min + r2.get("width", 0.0)
            y2_max = y2_min + r2.get("height", 0.0)
            
            # Если r1 полностью содержит r2
            if x1_min <= x2_min + 0.5 and y1_min <= y2_min + 0.5 and \
               x1_max >= x2_max - 0.5 and y1_max >= y2_max - 0.5:
                container_ids.add(room_ids[i])
                logger.warning(f"[GRAPH_COMPILER] Комната '{room_ids[i]}' содержит '{room_ids[j]}'. Это внешняя граница — исключена из графа.")

    if container_ids:
        rooms = {rid: data for rid, data in rooms.items() if rid not in container_ids}

    # 1. Компиляция узлов
    for room_id, room_data in rooms.items():
        canonical_id = f"{location_id}:{room_id}"
        # Map Editor отдаёт x, y как левый верхний угол. Вычисляем центроид для NodeRef.
        rx = room_data.get("x", 0.0)
        ry = room_data.get("y", 0.0)
        rw = room_data.get("width") or room_data.get("w") or 0.0
        rh = room_data.get("height") or room_data.get("h") or 0.0
        
        center_x = rx + rw / 2
        center_y = ry + rh / 2
        
        # Формируем NodeRef. Резолвер принимает только строковые типы, не весь dict.
        node_ref = NodeRef(
            node_id=canonical_id,
            x=center_x,
            y=center_y,
            role=resolve_role(
                node_label=room_data.get("name", room_id), 
                editor_type=room_data.get("type"), 
                node_id=room_id
            ),
            tags=room_data.get("tags", []),
            zone_id=location_id,
            level=level
        )
        graph[canonical_id] = node_ref
        
        # Маппинг: legacy_id → canonical_id
        alias_map[room_id] = canonical_id
        
        # ADR-114: name-alias для обратной совместимости schedule
        # NPC position ссылается на "main_hall", "bed" — эти имена
        # должны резолвиться в канонические ID графа
        room_name = room_data.get("name", "")
        if room_name and room_name != room_id and room_name.lower() not in alias_map:
            alias_map[room_name.lower()] = canonical_id
        
        # Инъекция алиасов (для поиска "кухня" вместо "kitchen")
        for alias in room_data.get("aliases", []):
            alias_map[alias.lower()] = canonical_id
        
        # ADR-121: Role-based legacy aliases — используем модульную константу
        _legacy_names = _ROLE_LEGACY_ALIASES.get(node_ref.role, set())
        for _alias in _legacy_names:
            if _alias not in alias_map:
                alias_map[_alias] = canonical_id

    # 2. Компиляция связей
    passages = editor_data.get("passages", editor_data.get("connections", []))
    
    # ADR-073: Adjacency Inference. Если Map Editor не дал явные passages (или их мало),
    # компилятор выводит связи из смежности полигонов комнат. Двери фильтруют проходимость, 
    # но не определяют существование топологии (разрушаемость = путь открывается).
    if not passages and len(rooms) > 1:
        passages = _infer_connections_from_adjacency(rooms)

    for passage in passages:
        from_legacy = passage.get("from")
        to_legacy = passage.get("to")
        
        from_canonical = alias_map.get(from_legacy, f"{location_id}:{from_legacy}")
        to_canonical = alias_map.get(to_legacy, f"{location_id}:{to_legacy}")
        
        if from_canonical in graph and to_canonical in graph:
            connections.setdefault(from_canonical, set()).add(to_canonical)
            # Двунаправленная связь по умолчанию (если не указано иное)
            if not passage.get("one_way", False):
                connections.setdefault(to_canonical, set()).add(from_canonical)
        else:
            logger.warning(f"[GRAPH_COMPILER] Пропуск связи {from_legacy}→{to_legacy}: узел не найден в графе")

    _validate_connectivity(graph, connections, location_id)

    # ДОЛГ 6.2: _legacy_compile не имеет adjacency → boundary_map пуста
    return graph, connections, alias_map, {}

def _infer_connections_from_adjacency(rooms: Dict[str, dict], tolerance: float = 0.5) -> List[dict]:
    """Выводит связи между комнатами на основе смежности их bounding box.
    Если две комнаты имеют общую стену (пересечение по оси > tolerance), 
    между ними создаётся passage. Это масштабируемая основа: двери потом модифицируют этот путь."""
    connections = []
    room_ids = list(rooms.keys())
    
    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            r1 = rooms[room_ids[i]]
            r2 = rooms[room_ids[j]]
            
            # Bounding Box: x, y, width, height
            x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
            x1_max = x1_min + r1.get("width", 0.0)
            y1_max = y1_min + r1.get("height", 0.0)
            
            x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
            x2_max = x2_min + r2.get("width", 0.0)
            y2_max = y2_min + r2.get("height", 0.0)
            
            # Вертикальная общая стена (r1 справа или слева от r2)
            if abs(x1_max - x2_min) < tolerance or abs(x2_max - x1_min) < tolerance:
                # Проверяем перекрытие по Y
                y_overlap = min(y1_max, y2_max) - max(y1_min, y2_min)
                if y_overlap > tolerance:
                    connections.append({"from": room_ids[i], "to": room_ids[j]})
                    continue
                    
            # Горизонтальная общая стена (r1 над или под r2)
            if abs(y1_max - y2_min) < tolerance or abs(y2_max - y1_min) < tolerance:
                # Проверяем перекрытие по X
                x_overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
                if x_overlap > tolerance:
                    connections.append({"from": room_ids[i], "to": room_ids[j]})
                    continue
                    
    return connections

# ── Boundary Nodes (ДОЛГ 6.2) ────────────────────────────────────────

# Противоположные направления для резолва entry-узла в соседнем чанке
_OPPOSITE_DIRECTION = {
    "east": "west",
    "west": "east",
    "north": "south",
    "south": "north",
}


def _create_boundary_nodes(
    graph: Dict[str, NodeRef],
    connections: Dict[str, Set[str]],
    alias_map: Dict[str, str],
    boundary_map: Dict[str, dict],
    location_id: str,
    adjacency: dict,
) -> None:
    """Создаёт виртуальные граничные узлы по декларации adjacency.

    Для каждого направления (east, west, north, south) создаётся:
    - Boundary node на краю текущего чанка
    - Связь с ближайшим существующим узлом
    - Метаданные в boundary_map для навигации при переходе

    Boundary node НЕ создаёт связь с узлом соседнего чанка напрямую —
    это ответственность MovementEngine при cross-chunk transition.
    """
    if not graph:
        return

    # Вычисляем bounding box существующих узлов (исключая уже созданные boundary)
    internal_nodes = {
        nid: nref for nid, nref in graph.items()
        if nref.role != NodeRole.BOUNDARY
    }
    if not internal_nodes:
        return

    xs = [nref.x for nref in internal_nodes.values()]
    ys = [nref.y for nref in internal_nodes.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    # Маржа — boundary node ставится за пределами bounding box
    margin = 2.0

    for direction, neighbor_chunk in adjacency.items():
        if not isinstance(neighbor_chunk, str) or not neighbor_chunk:
            continue

        # Координаты boundary node — на краю чанка в направлении выхода
        if direction == "east":
            bx, by = max_x + margin, center_y
        elif direction == "west":
            bx, by = min_x - margin, center_y
        elif direction == "south":
            bx, by = center_x, max_y + margin
        elif direction == "north":
            bx, by = center_x, min_y - margin
        else:
            logger.warning(f"[GRAPH_COMPILER] Неизвестное направление adjacency: {direction}")
            continue

        boundary_id = f"{location_id}:exit_{direction}"
        entry_direction = _OPPOSITE_DIRECTION.get(direction, direction)

        # Создаём boundary node
        node_ref = NodeRef(
            node_id=boundary_id,
            role=NodeRole.BOUNDARY,
            tags=["boundary:exit", f"direction:{direction}", f"neighbor:{neighbor_chunk}", f"entry_direction:{entry_direction}"],
            x=bx,
            y=by,
            zone_id=location_id,
        )
        graph[boundary_id] = node_ref
        alias_map[f"exit_{direction}"] = boundary_id

        # Метаданные для cross-chunk навигации
        boundary_map[boundary_id] = {
            "direction": direction,
            "neighbor_chunk": neighbor_chunk,
            "entry_direction": entry_direction,
            "entry_node_hint": f"{neighbor_chunk}:exit_{entry_direction}",
        }

        # Связываем с ближайшим внутренним узлом (1-2 узла для надёжности)
        # Расстояние от boundary до каждого внутреннего узла
        distances = []
        for nid, nref in internal_nodes.items():
            dist = ((nref.x - bx) ** 2 + (nref.y - by) ** 2) ** 0.5
            distances.append((dist, nid))
        distances.sort()

        # Соединяем с ближайшим узлом (если он не слишком далеко)
        if distances:
            closest_dist, closest_id = distances[0]
            # Минимальный порог: margin * 3 (гарантирует связь даже при одном узле)
            max_link_dist = max(max_x - min_x, max_y - min_y, margin * 3) * 0.8
            if closest_dist <= max_link_dist:
                connections.setdefault(boundary_id, set()).add(closest_id)
                connections.setdefault(closest_id, set()).add(boundary_id)
                # Если есть второй близкий узел — тоже связываем (для альтернативных путей)
                if len(distances) > 1:
                    d2, id2 = distances[1]
                    if d2 <= max_link_dist and d2 <= closest_dist * 1.5:
                        connections.setdefault(boundary_id, set()).add(id2)
                        connections.setdefault(id2, set()).add(boundary_id)

        logger.info(
            f"[GRAPH_COMPILER] Boundary node: {boundary_id} → "
            f"{neighbor_chunk} ({direction}), linked to {closest_id}"
        )


def _validate_connectivity(
    graph: Dict[str, NodeRef],
    connections: Dict[str, Set[str]],
    location_id: str,
) -> None:
    """Проверяет связность графа через BFS. Логирует изолированные компоненты."""
    if not graph:
        return

    visited: Set[str] = set()
    components: List[Set[str]] = []

    for node_id in graph:
        if node_id in visited:
            continue
        # BFS от node_id
        component: Set[str] = set()
        queue = deque([node_id])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in connections.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    if len(components) > 1:
        # Есть изолированные компоненты
        main_component = max(components, key=len)
        for component in components:
            if component is main_component:
                continue
            isolated_ids = [nid.split(":")[-1] for nid in component]
            logger.warning(
                f"[GRAPH_COMPILER] {location_id}: "
                f"изолированная компонента ({len(component)} узлов): {isolated_ids}"
            )


def load_editor_json(
    campaign_id: str,
    location_id: str,
    search_dirs: Optional[List[Path]] = None,
) -> Optional[dict]:
    """Ищет и загружает editor JSON для локации.
    
    Аргументы:
        campaign_id: идентификатор кампании
        location_id: идентификатор локации
        search_dirs: дополнительные директории для поиска
    
    Возвращает:
        dict из editor JSON или None
    """
    if search_dirs is None:
        # ADR-O-146: Единственный источник карт — map_editor/campaigns.
        # backend/data/campaigns — мёртвый путь, удалён.
        search_dirs = [
            _PROJECT_ROOT / "frontend" / "map_editor" / "campaigns" / campaign_id / "locations",
        ]

    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in loc_dir.glob("*.json"):
            try:
                # utf-8-sig корректно обрабатывает BOM (EF BB BF)
                data = json.loads(json_file.read_text(encoding="utf-8-sig"))
                lid = data.get("location_id", "")
                label = data.get("label", "")
                # Точное совпадение
                if lid == location_id or label == location_id:
                    return data
                # Частичное совпадение
                if label and location_id and location_id.lower() in label.lower():
                    return data
                # ADR-061: Compatibility Resolver для legacy данных (без location_id).
                # Строгое правило: инференс только по точному совпадению префикса имени файла.
                if not lid and data.get("rooms"):
                    inferred_lid = json_file.stem.lower()
                    # Проверяем, что целевой location_id начинается с имени файла
                    if location_id.lower().startswith(inferred_lid):
                        logger.warning(
                            f"[GRAPH_COMPILER] DEPRECATION: Файл {json_file.name} не имеет поля 'location_id'. "
                            f"Инференс из имени файла: '{inferred_lid}'. Заполните поле в Map Editor!"
                        )
                        return data
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"[GRAPH_COMPILER] Ошибка чтения {json_file.name}: {e}")
                continue

    logger.warning(f"[GRAPH_COMPILER] editor JSON не найден для {campaign_id}/{location_id}")
    return None

def _infer_adjacency_from_bounds(rooms: dict, tolerance: float = 0.5) -> list:
    """Инференс смежности: если bounding box-ы комнат имеют общую стену,
    между ними создаётся passage. Это масштабируемая основа: двери потом модифицируют этот путь.
    ADR-091: Комната, полностью содержащая другую — это внешняя граница (container), не навигационная зона."""
    
    # ADR-091: Фильтрация container-комнат (внешних границ от Map Editor)
    room_ids = list(rooms.keys())
    container_ids = set()
    
    for i in range(len(room_ids)):
        for j in range(len(room_ids)):
            if i == j: continue
            r1 = rooms[room_ids[i]]
            r2 = rooms[room_ids[j]]
            
            x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
            x1_max = x1_min + r1.get("width", 0.0)
            y1_max = y1_min + r1.get("height", 0.0)
            
            x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
            x2_max = x2_min + r2.get("width", 0.0)
            y2_max = y2_min + r2.get("height", 0.0)
            
            # Если r1 полностью содержит r2
            if x1_min <= x2_min + tolerance and y1_min <= y2_min + tolerance and \
               x1_max >= x2_max - tolerance and y1_max >= y2_max - tolerance:
                container_ids.add(room_ids[i])
                logger.warning(f"[GRAPH_COMPILER] Комната '{room_ids[i]}' содержит '{room_ids[j]}'. Это внешняя граница — исключена из графа.")

    filtered_rooms = {rid: rooms[rid] for rid in rooms if rid not in container_ids}
    
    connections = []
    filtered_ids = list(filtered_rooms.keys())
    
    for i in range(len(filtered_ids)):
        for j in range(i + 1, len(filtered_ids)):
            r1 = filtered_rooms[filtered_ids[i]]
            r2 = filtered_rooms[filtered_ids[j]]
            
            # Bounding Box: x, y, width, height
            x1_min, y1_min = r1.get("x", 0.0), r1.get("y", 0.0)
            x1_max = x1_min + r1.get("width", 0.0)
            y1_max = y1_min + r1.get("height", 0.0)
            
            x2_min, y2_min = r2.get("x", 0.0), r2.get("y", 0.0)
            x2_max = x2_min + r2.get("width", 0.0)
            y2_max = y2_min + r2.get("height", 0.0)
            
            # Вертикальная общая стена (r1 справа или слева от r2)
            if abs(x1_max - x2_min) < tolerance or abs(x2_max - x1_min) < tolerance:
                # Проверяем перекрытие по Y
                y_overlap = min(y1_max, y2_max) - max(y1_min, y2_min)
                if y_overlap > tolerance:
                    connections.append({"from": filtered_ids[i], "to": filtered_ids[j]})
                    continue
                    
            # Горизонтальная общая стена (r1 над или под r2)
            if abs(y1_max - y2_min) < tolerance or abs(y2_max - y1_min) < tolerance:
                # Проверяем перекрытие по X
                x_overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
                if x_overlap > tolerance:
                    connections.append({"from": filtered_ids[i], "to": filtered_ids[j]})
                    continue
                    
    return connections