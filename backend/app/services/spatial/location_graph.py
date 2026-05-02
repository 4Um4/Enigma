"""
path: backend/app/services/npc/location_graph.py
Назначение: Граф узлов локации + XY-расстояния (R4 Spatial)
Зависимости: stdlib only
Основные сущности: LocationNode, LocationGraph, load_graph, invalidate_graph_cache
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SPATIAL_SCALE = "1 unit = 1 meter"
_UNKNOWN_DISTANCE = 5.0

# Кэш графов — живёт на протяжении процесса.
# Инвалидируется явно через invalidate_graph_cache() при изменении шаблонов.
_GRAPH_CACHE: Dict[str, "LocationGraph"] = {}


@dataclass(frozen=True)
class LocationNode:
    """R4.2: узел графа — id, XY, родитель, дети, связи, метка."""

    node_id:     str
    x:           float
    y:           float
    parent:      Optional[str]      = None
    children:    Tuple[str, ...]    = field(default_factory=tuple)
    connections: Tuple[str, ...]    = field(default_factory=tuple)
    label:       str                = ""

    def distance_to(self, other: "LocationNode") -> float:
        return round(math.dist((self.x, self.y), (other.x, other.y)), 2)


class LocationGraph:
    def __init__(self, location_id: str, nodes: Dict[str, LocationNode]) -> None:
        self.location_id = location_id
        self._nodes = nodes

    def get_node(self, node_id: str) -> Optional[LocationNode]:
        return self._nodes.get(node_id)

    def all_nodes(self) -> Dict[str, LocationNode]:
        return dict(self._nodes)

    def find_nearest_node(self, x: float, y: float) -> Optional[str]:
        """Находит ближайший узел к заданным координатам.

        Используется для резолва APPROACH: позиция игрока → ближайший узел графа.
        Возвращает node_id или None если граф пуст.
        """
        best_id: Optional[str] = None
        best_dist: float = float("inf")
        for nid, node in self._nodes.items():
            d = math.dist((node.x, node.y), (x, y))
            if d < best_dist:
                best_dist = d
                best_id = nid
        return best_id

    def find_path(self, from_node: str, to_node: str) -> list[str]:
        """BFS-путь от from_node до to_node по connections.
        
        Returns:
            Список node_id включая from_node и to_node.
            Пустой список если путь не найден или узлы не существуют.
        """
        if from_node == to_node:
            return [from_node]
        if from_node not in self._nodes or to_node not in self._nodes:
            return []

        from collections import deque
        visited: set[str] = {from_node}
        queue: deque[tuple[str, list[str]]] = deque([(from_node, [from_node])])

        while queue:
            current, path = queue.popleft()
            node = self._nodes.get(current)
            if node is None:
                continue
            for neighbor in node.connections:
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == to_node:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))

        return []

    def get_distance(self, from_node: str, to_node: str) -> float:
        src = self._nodes.get(from_node)
        dst = self._nodes.get(to_node)
        if src is None or dst is None:
            logger.debug(
                "[LocationGraph] неизвестный узел в %s: %s -> %s",
                self.location_id, from_node, to_node,
            )
            return _UNKNOWN_DISTANCE
        return src.distance_to(dst)


def _parse_nodes(raw_nodes: dict) -> Dict[str, LocationNode]:
    nodes: Dict[str, LocationNode] = {}
    for node_id, payload in raw_nodes.items():
        try:
            nodes[node_id] = LocationNode(
                node_id    = node_id,
                x          = float(payload.get("x", 0.0)),
                y          = float(payload.get("y", 0.0)),
                parent     = payload.get("parent"),
                children   = tuple(payload.get("children", [])),
                connections= tuple(payload.get("connections", [])),
                label      = str(payload.get("label", "")),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("[LocationGraph] некорректный узел=%s: %s", node_id, exc)
    return nodes


def validate_graph(location_id: str, nodes: Dict[str, LocationNode]) -> list[str]:
    """Проверяет целостность графа — симметрия связей, корректность родителей."""
    errors: list[str] = []
    for node_id, node in nodes.items():
        if node.parent and node.parent not in nodes:
            errors.append(
                f"[{location_id}] node '{node_id}' parent '{node.parent}' not found"
            )
        for child_id in node.children:
            if child_id not in nodes:
                errors.append(
                    f"[{location_id}] node '{node_id}' child '{child_id}' not found"
                )
                continue
            if nodes[child_id].parent != node_id:
                errors.append(
                    f"[{location_id}] node '{node_id}' lists child '{child_id}', "
                    f"but child parent is '{nodes[child_id].parent}'"
                )
        for neighbor in node.connections:
            if neighbor not in nodes:
                errors.append(
                    f"[{location_id}] node '{node_id}' -> unknown connection '{neighbor}'"
                )
                continue
            if node_id not in nodes[neighbor].connections:
                errors.append(
                    f"[{location_id}] asymmetric connection "
                    f"'{node_id}' -> '{neighbor}' (reverse missing)"
                )
    return errors


def local_xy_distance(
    graph: LocationGraph,
    node_a: str,
    node_b: str,
    local_a: tuple[float, float] = (0.0, 0.0),
    local_b: tuple[float, float] = (0.0, 0.0),
) -> float:
    """R4.3: расстояние = дистанция между узлами + смещение внутри узлов."""
    base = graph.get_distance(node_a, node_b)
    return round(base + math.dist(local_a, local_b), 2)


# ---------------------------------------------------------------------------
# Кэш и загрузка
# ---------------------------------------------------------------------------

def invalidate_graph_cache(location_id: Optional[str] = None) -> None:
    """
    Инвалидирует кэш графа.
    Вызывать при изменении location_templates.json в рантайме.
    location_id=None → сбросить весь кэш.
    """
    if location_id is None:
        _GRAPH_CACHE.clear()
        logger.debug("[LocationGraph] весь кэш графов сброшен")
    else:
        _GRAPH_CACHE.pop(location_id, None)
        logger.debug("[LocationGraph] кэш графа '%s' сброшен", location_id)


# Путь к backend/data/ относительно этого файла — не зависит от CWD
_DEFAULT_DATA_DIR: str = str(Path(__file__).resolve().parent.parent.parent.parent / "data")

def load_graph(location_id: str, data_dir: str = _DEFAULT_DATA_DIR) -> LocationGraph:
    """
    Загружает граф локации.
    Результат кэшируется — повторные вызовы бесплатны.
    """
    if location_id in _GRAPH_CACHE:
        return _GRAPH_CACHE[location_id]

    graph = _load_graph_uncached(location_id, data_dir)
    _GRAPH_CACHE[location_id] = graph
    return graph


def _load_graph_uncached(location_id: str, data_dir: str) -> LocationGraph:
    """Читает граф с диска или возвращает встроенный fallback."""
    templates_path = Path(data_dir) / "locations" / "location_templates.json"

    if templates_path.exists():
        try:
            templates  = json.loads(templates_path.read_text(encoding="utf-8-sig"))
            raw_nodes  = templates.get(location_id, {}).get("positions", {})
            if raw_nodes:
                nodes = _parse_nodes(raw_nodes)
                for err in validate_graph(location_id, nodes):
                    logger.warning("[LocationGraph] %s", err)
                return LocationGraph(location_id, nodes)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[LocationGraph] ошибка чтения шаблона: %s", exc)

    # Встроенный минимальный fallback — только если JSON недоступен
    nodes = _parse_nodes(_BUILTIN_NODES.get(location_id, _BUILTIN_NODES["tavern_silver_wolf"]))
    logger.warning("[LocationGraph] fallback-граф для '%s'", location_id)
    return LocationGraph(location_id, nodes)


# Минимальный встроенный граф — только tavern_silver_wolf.
# Все остальные локации должны быть в location_templates.json.
_BUILTIN_NODES: Dict[str, dict] = {
    "tavern_silver_wolf": {
        "behind_bar":      {"x": -4.0, "y":  0.0, "connections": ["bar_area"],     "label": "за стойкой"},
        "bar_area":        {"x": -2.5, "y":  0.0, "connections": ["behind_bar", "main_hall"], "label": "у стойки"},
        "main_hall":       {
            "x": 0.0, "y": 0.0,
            "connections": ["bar_area", "corner_table", "serving_table_3", "entrance", "fireplace", "stairs"],
            "label": "центр зала",
        },
        "serving_table_3": {"x":  1.5, "y":  2.0, "connections": ["main_hall"],    "label": "у третьего стола"},
        "corner_table":    {"x":  3.5, "y":  3.0, "connections": ["main_hall"],    "label": "в тёмном углу"},
        "entrance":        {"x":  0.0, "y": -4.0, "connections": ["main_hall"],    "label": "у входа"},
        "fireplace":       {"x": -3.5, "y":  2.5, "connections": ["main_hall"],    "label": "у камина"},
        "stairs":          {"x":  2.0, "y": -3.0, "connections": ["main_hall"],    "label": "у лестницы"},
    },
}