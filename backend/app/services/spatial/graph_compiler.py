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
        return {}, {}
        
    raw_nodes = editor_data.get("nodes", {})
    raw_passages = editor_data.get("passages", [])

    graph: Dict[str, NodeRef] = {}
    alias_map: Dict[str, str] = {}
    # Собираем все подключения: canonical_id → set[canonical_id]
    connections: Dict[str, Set[str]] = {}

    # ── Обрабатываем nodes ────────────────────────────────────────────
    for editor_id, node_data in raw_nodes.items():
        canonical_id = f"{location_id}:{editor_id}"
        x = float(node_data.get("x", 0.0))
        y = float(node_data.get("y", 0.0))
        label = str(node_data.get("label", ""))
        node_conns = set(node_data.get("connections", []))

        # Роль выводится из label + node_id
        role = resolve_role(node_label=label, node_id=editor_id)

        # Теги — пока пустые (будущий слой editor UI)
        tags: List[str] = []

        node_ref = NodeRef(
            node_id=canonical_id,
            role=role,
            tags=tags,
            x=x,
            y=y,
            zone_id=location_id,
            level=level,
        )
        graph[canonical_id] = node_ref
        alias_map[editor_id] = canonical_id

        # Подключения — пока в legacy-формате, резолвим позже
        connections[canonical_id] = set()
        for conn_id in node_conns:
            # Коннекты внутри той же локации
            conn_canonical = f"{location_id}:{conn_id}"
            connections[canonical_id].add(conn_canonical)

    # ── Обрабатываем passages (двери, переходы, лестницы) ────────────
    for passage in raw_passages:
        passage_id = passage.get("id", "")
        if not passage_id:
            continue

        canonical_id = f"{location_id}:{passage_id}"
        if canonical_id in graph:
            continue  # Уже обработан как node

        x = float(passage.get("position", {}).get("x", 0.0))
        y = float(passage.get("position", {}).get("y", 0.0))
        label = str(passage.get("label", ""))
        editor_type = str(passage.get("type", ""))

        # Роль из type (door/ladder/transition → TRANSITION)
        role = resolve_role(
            node_label=label,
            editor_type=editor_type if editor_type else None,
        )

        tags: List[str] = [editor_type] if editor_type else []

        node_ref = NodeRef(
            node_id=canonical_id,
            role=role,
            tags=tags,
            x=x,
            y=y,
            zone_id=location_id,
            level=level,
        )
        graph[canonical_id] = node_ref
        alias_map[passage_id] = canonical_id

        # Passages не имеют connections в editor JSON — изолированы пока
        connections[canonical_id] = set()

    # ── Резолвим подключения ──────────────────────────────────────────
    # Проверяем что все referenced connections существуют в графе
    for canonical_id, conn_set in connections.items():
        valid_conns = {c for c in conn_set if c in graph}
        if len(valid_conns) != len(conn_set):
            missing = conn_set - valid_conns
            logger.warning(
                f"[GRAPH_COMPILER] Узел {canonical_id}: "
                f"подключения на несуществующие узлы: {missing}"
            )
        connections[canonical_id] = valid_conns

    # ── Валидация связности ───────────────────────────────────────────
    _validate_connectivity(graph, connections, location_id)

    # ── Сохраняем connections в tags для совместимости ────────────────
    # NodeRef immutable — connections храним отдельно
    # Возвращаем вместе с графом

    logger.info(
        f"[GRAPH_COMPILER] {location_id}: {len(graph)} узлов, "
        f"{sum(len(c) for c in connections.values())//2} рёбер"
    )

    return graph, connections, alias_map


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
                # Fallback удалён: файл без location_id не может быть
                # источником графа для произвольной локации — это
                # порождало подмену inn_rooms → tavern
            except (json.JSONDecodeError, OSError):
                continue

    # Fallback: если в кампании нет своего editor JSON, ищем в глобальном location_templates.json
    templates_path = _PROJECT_ROOT / "backend" / "data" / "locations" / "location_templates.json"
    if templates_path.exists():
        try:
            templates_data = json.loads(templates_path.read_text(encoding="utf-8-sig"))
            loc_data = templates_data.get(location_id)
            if loc_data and "nodes" in loc_data:
                logger.info(f"[SPATIAL] Using location_templates.json fallback for '{location_id}'")
                # Шаблон инстанцируется, чтобы мутации в scene_state не ломали "идею" локации
                import copy
                return copy.deepcopy(loc_data)
        except (json.JSONDecodeError, OSError):
            pass

    logger.warning(f"[GRAPH_COMPILER] editor JSON не найден для {campaign_id}/{location_id}")
    return None