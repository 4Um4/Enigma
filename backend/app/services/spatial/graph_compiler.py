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
        return {}, {}, {}

    graph: Dict[str, NodeRef] = {}
    connections: Dict[str, Set[str]] = {}
    alias_map: Dict[str, str] = {}

    # Поддержка обоих форматов: "rooms" (новый) и "nodes" (старый)
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
        return {}, {}, {}

    if not rooms:
        logger.warning(f"[GRAPH_COMPILER] Нет узлов (rooms/nodes) в {location_id}")
        return {}, {}, {}

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
        
        # Инъекция алиасов (для поиска "кухня" вместо "kitchen")
        for alias in room_data.get("aliases", []):
            alias_map[alias.lower()] = canonical_id

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

    return graph, connections, alias_map

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
        search_dirs = [
            _PROJECT_ROOT / "frontend" / "map_editor" / "campaigns" / campaign_id / "locations",
            _PROJECT_ROOT / "backend" / "data" / "campaigns" / campaign_id / "locations",
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