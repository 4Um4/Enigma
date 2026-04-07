"""R4 Spatial: location graph + local XY helpers."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

SPATIAL_SCALE = "1 unit = 1 meter"
_UNKNOWN_DISTANCE = 5.0


@dataclass(frozen=True)
class LocationNode:
    """R4.2 node contract: id/parent/children/connections + XY."""

    node_id: str
    x: float
    y: float
    parent: str | None = None
    children: Tuple[str, ...] = field(default_factory=tuple)
    connections: Tuple[str, ...] = field(default_factory=tuple)
    label: str = ""

    def distance_to(self, other: "LocationNode") -> float:
        return round(math.dist((self.x, self.y), (other.x, other.y)), 2)


class LocationGraph:
    def __init__(self, location_id: str, nodes: Dict[str, LocationNode]):
        self.location_id = location_id
        self._nodes = nodes

    def get_node(self, node_id: str) -> LocationNode | None:
        return self._nodes.get(node_id)

    def all_nodes(self) -> Dict[str, LocationNode]:
        return dict(self._nodes)

    def get_distance(self, from_node: str, to_node: str) -> float:
        src = self._nodes.get(from_node)
        dst = self._nodes.get(to_node)
        if src is None or dst is None:
            logger.debug(
                "[LocationGraph] Unknown node in %s: %s -> %s", self.location_id, from_node, to_node
            )
            return _UNKNOWN_DISTANCE
        return src.distance_to(dst)


def _parse_nodes(raw_nodes: dict) -> Dict[str, LocationNode]:
    nodes: Dict[str, LocationNode] = {}
    for node_id, payload in raw_nodes.items():
        try:
            nodes[node_id] = LocationNode(
                node_id=node_id,
                x=float(payload.get("x", 0.0)),
                y=float(payload.get("y", 0.0)),
                parent=payload.get("parent"),
                children=tuple(payload.get("children", [])),
                connections=tuple(payload.get("connections", [])),
                label=str(payload.get("label", "")),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("[LocationGraph] malformed node=%s: %s", node_id, exc)
    return nodes


def validate_graph(location_id: str, nodes: Dict[str, LocationNode]) -> list[str]:
    errors: list[str] = []

    for node_id, node in nodes.items():
        if node.parent and node.parent not in nodes:
            errors.append(f"[{location_id}] node '{node_id}' parent '{node.parent}' not found")

        for child_id in node.children:
            if child_id not in nodes:
                errors.append(f"[{location_id}] node '{node_id}' child '{child_id}' not found")
                continue
            if nodes[child_id].parent != node_id:
                errors.append(
                    f"[{location_id}] node '{node_id}' lists child '{child_id}', but child parent is '{nodes[child_id].parent}'"
                )

        for neighbor in node.connections:
            if neighbor not in nodes:
                errors.append(f"[{location_id}] node '{node_id}' -> unknown connection '{neighbor}'")
                continue
            if node_id not in nodes[neighbor].connections:
                errors.append(
                    f"[{location_id}] asymmetric connection '{node_id}' -> '{neighbor}' (reverse missing)"
                )

    return errors


def local_xy_distance(
    graph: LocationGraph,
    node_a: str,
    node_b: str,
    local_a: tuple[float, float] = (0.0, 0.0),
    local_b: tuple[float, float] = (0.0, 0.0),
) -> float:
    """R4.3: node geometry + local pseudo-XY displacement."""
    base = graph.get_distance(node_a, node_b)
    return round(base + math.dist(local_a, local_b), 2)


def load_graph(location_id: str, data_dir: str = "data") -> LocationGraph:
    templates_path = Path(data_dir) / "locations" / "location_templates.json"

    if templates_path.exists():
        try:
            templates = json.loads(templates_path.read_text(encoding="utf-8"))
            raw_nodes = templates.get(location_id, {}).get("positions", {})
            if raw_nodes:
                nodes = _parse_nodes(raw_nodes)
                for err in validate_graph(location_id, nodes):
                    logger.warning("[LocationGraph] %s", err)
                return LocationGraph(location_id, nodes)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[LocationGraph] template read failure: %s", exc)

    fallback = _builtin_graphs()
    nodes = fallback.get(location_id, fallback.get("tavern_silver_wolf", {}))
    return LocationGraph(location_id, nodes)


def _builtin_graphs() -> Dict[str, Dict[str, LocationNode]]:
    return {
        "tavern_silver_wolf": _parse_nodes(
            {
                "behind_bar": {"x": -4.0, "y": 0.0, "connections": ["bar_area"], "label": "за стойкой"},
                "bar_area": {"x": -2.5, "y": 0.0, "connections": ["behind_bar", "main_hall"], "label": "у стойки"},
                "main_hall": {
                    "x": 0.0,
                    "y": 0.0,
                    "connections": ["bar_area", "corner_table", "serving_table_3", "entrance", "fireplace", "stairs"],
                    "label": "центр зала",
                },
                "serving_table_3": {"x": 1.5, "y": 2.0, "connections": ["main_hall"], "label": "у третьего стола"},
                "corner_table": {"x": 3.5, "y": 3.0, "connections": ["main_hall"], "label": "в тёмном углу"},
                "entrance": {"x": 0.0, "y": -4.0, "connections": ["main_hall"], "label": "у входа"},
                "fireplace": {"x": -3.5, "y": 2.5, "connections": ["main_hall"], "label": "у камина"},
                "stairs": {"x": 2.0, "y": -3.0, "connections": ["main_hall"], "label": "у лестницы"},
            }
        ),
        "market_square": _parse_nodes(
            {
                "stall_1": {"x": -5.0, "y": 0.0, "connections": ["center"], "label": "первый прилавок"},
                "stall_2": {"x": -2.5, "y": 0.0, "connections": ["center"], "label": "второй прилавок"},
                "stall_3": {"x": 0.0, "y": 2.0, "connections": ["center"], "label": "третий прилавок"},
                "center": {
                    "x": 0.0,
                    "y": 0.0,
                    "connections": ["stall_1", "stall_2", "stall_3", "gate_post", "fountain"],
                    "label": "центр рынка",
                },
                "gate_post": {"x": 0.0, "y": -5.0, "connections": ["center"], "label": "у ворот"},
                "fountain": {"x": 3.0, "y": 0.0, "connections": ["center"], "label": "у фонтана"},
            }
        ),
    }
