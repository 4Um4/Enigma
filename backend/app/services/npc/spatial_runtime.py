"""R4 runtime helpers: local XY distances, LOS and scene extraction."""

from __future__ import annotations

import math
from typing import Iterable

from app.core.config import settings
from app.services.npc.location_graph import load_graph, local_xy_distance


def _loc(entity: dict, fallback_location_id: str) -> str:
    return str(entity.get("location_id") or fallback_location_id)


def _node(entity: dict) -> str:
    return str(entity.get("position") or entity.get("node_id") or "")


def _local(entity: dict) -> tuple[float, float]:
    local = entity.get("local_position") or {}
    try:
        return float(local.get("x", 0.0)), float(local.get("y", 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def resolve_distance_between_entities(scene_state: dict, a: dict, b: dict) -> float:
    """R4.3 distance in meters with graph+local XY composition."""
    location_id = scene_state.get("location_id", "")
    if _loc(a, location_id) != _loc(b, location_id):
        return 999.0

    graph = load_graph(location_id, data_dir=str(settings.data_dir))
    node_a = _node(a)
    node_b = _node(b)
    if not node_a or not node_b:
        return 999.0

    return local_xy_distance(graph, node_a, node_b, _local(a), _local(b))


def line_of_sight(distance: float, scene_state: dict) -> bool:
    """R4.3/R4.4 visibility with environment modifiers."""
    env = scene_state.get("environment", {})
    modifiers = scene_state.get("environment_modifiers", {})

    light = env.get("light_level", "dim")
    density = float(modifiers.get("density", 0.0))
    danger = float(modifiers.get("danger", 0.0))

    base_range = 15.0
    if light == "dark":
        base_range = 4.0
    elif light == "dim":
        base_range = 10.0

    # плотность толпы/тумана и высокий danger режут LOS
    los_range = max(1.5, base_range - density * 6.0 - danger * 2.0)
    return distance <= los_range


def sound_reach(base_radius: float, scene_state: dict) -> float:
    """R4.4 audio propagation from noise/density modifiers."""
    modifiers = scene_state.get("environment_modifiers", {})
    noise = float(modifiers.get("noise", 0.0))
    density = float(modifiers.get("density", 0.0))

    # шум увеличивает дальность слышимости громкого события,
    # но плотность (стены/толпа) гасит звук
    return max(0.5, base_radius + noise * 4.0 - density * 3.0)


def extract_scene_for_npc(scene_state: dict, npc_id: str, npc_ids: Iterable[str]) -> dict:
    """R4.5 snapshot: кто рядом с NPC и какие действия доступны."""
    npc_positions = scene_state.get("npc_positions", {})
    me = npc_positions.get(npc_id, {})
    if not me:
        return {"nearby": [], "available_actions": []}

    nearby: list[dict] = []
    for other_id in npc_ids:
        if other_id == npc_id:
            continue
        other = npc_positions.get(other_id, {})
        if not other:
            continue
        d = resolve_distance_between_entities(scene_state, me, other)
        if d <= 8.0:
            nearby.append({"npc_id": other_id, "distance": round(d, 2)})

    available_actions = ["wait", "move"]
    if nearby:
        available_actions.append("interact")
    if any(x["distance"] < 1.5 for x in nearby):
        available_actions.append("melee")

    return {"nearby": sorted(nearby, key=lambda x: x["distance"]), "available_actions": available_actions}
