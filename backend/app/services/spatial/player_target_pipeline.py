"""
Извлечение цели игрока и spatial данные для DM SceneBuilder.

Вынесено из game_loop/__init__.py. Содержит три чистых функции:
1. extract_player_target — PARSE цель из текста + мутация scene_state
2. detect_and_publish_spatial_transitions — детекция переходов → EventBus
3. build_spatial_data_for_dm — сборка spatial_data для DM Orchestrator

path: backend/app/services/spatial/player_target_pipeline.py
Назначение: Извлечение цели игрока, детекция spatial transitions, построение spatial_data для DM. Вынесено из game_loop.
Зависимости: PlayerTargetExtractor, spatial_events, EventBus, EventDTO, EventType
Основные сущности: PlayerTargetResult, extract_player_target(), detect_and_publish_spatial_transitions(), build_spatial_data_for_dm()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from app.services.action.player_target_extractor import PlayerTargetExtractor
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayerTargetResult:
    """Результат извлечения цели игрока из текста действия."""
    target_id: str
    target_name: str
    player_pos: Optional[dict]
    player_dists: Optional[Dict[str, float]]


def extract_player_target(
    load_npcs_fn: Callable[[], List[dict]],
    scene_state: dict,
    raw_input: str,
) -> PlayerTargetResult:
    """4.5: Извлекает цель игрока из текста действия.

    Мутирует scene_state: записывает player_distances, player_position,
    player_target_npc, player_target_npc_name (sticky target).
    """
    _scene_pre = scene_state
    _npc_ids = list((_scene_pre.get("npc_positions") or {}).keys())

    # Загружаем name_forms из NPC JSON — extract() ищет по ним
    _name_lookup_npcs = load_npcs_fn()
    _npc_ctx_list = []
    for _n in _name_lookup_npcs:
        _nid = _n.get("id") or _n.get("npc_id")
        if _nid and _nid in _npc_ids:
            _npc_ctx_list.append({
                "npc_id": _nid,
                "npc_name": _n.get("name", ""),
                "name_forms": _n.get("name_forms", []),
            })

    _extractor = PlayerTargetExtractor()
    _target_id, _target_name, _player_pos, _player_dists = _extractor.extract(
        action_text=raw_input or "",
        npc_contexts=_npc_ctx_list,
        scene_state=_scene_pre if isinstance(_scene_pre, dict) else {},
    )

    # Сохраняем расстояния обратно в scene_state — иначе spatial система всегда видит 5.0
    if _player_dists and isinstance(_scene_pre, dict):
        _scene_pre["player_distances"] = _player_dists
    if _player_pos and isinstance(_scene_pre, dict):
        _scene_pre["player_position"] = _player_pos
    if _target_id and isinstance(_scene_pre, dict):
        _scene_pre["player_target_npc"] = _target_id
        _scene_pre["player_target_npc_name"] = _target_name
        logger.warning(f"[TARGET] Extracted: {_target_name} ({_target_id})")

    return PlayerTargetResult(
        target_id=_target_id or "",
        target_name=_target_name or "",
        player_pos=_player_pos,
        player_dists=_player_dists,
    )


def detect_and_publish_spatial_transitions(
    prev_distances: Dict[str, float],
    curr_distances: Dict[str, float],
    location: str,
    campaign_id: str,
) -> list:
    """ФАЗА 3.1: Детекция переходов расстояний → EventBus.

    DecisionHub видит proximity через события.
    Возвращает список spatial event объектов.
    """
    from app.services.spatial.spatial_events import detect_transitions

    _spatial_events = detect_transitions(prev_distances, curr_distances)
    if _spatial_events:
        logger.debug(
            f"[SPATIAL] {len(_spatial_events)} transitions: "
            f"{[(e.npc_id, e.event_type) for e in _spatial_events]}"
        )
        for _sp in _spatial_events:
            _evt_type = (
                EventType.PROXIMITY_CLOSE
                if _sp.event_type == "proximity_close"
                else EventType.PROXIMITY_LEAVE
            )
            _ge = EventDTO.create(
                event_type=_evt_type.value,
                source="player",
                payload={
                    "location": location,
                    "campaign_id": campaign_id,
                    "target_id": _sp.npc_id,
                    "prev_distance": _sp.prev_distance,
                    "new_distance": _sp.new_distance,
                },
                radius=999.0,
            )
            get_event_bus().publish(_ge)

    return _spatial_events


def build_spatial_data_for_dm(location: str, scene_state: dict) -> dict:
    """Строит spatial_data из scene_state для DM SceneBuilder."""
    _scene = scene_state
    _npc_positions = _scene.get("npc_positions", {})
    logger.warning(
        f"[DEBUG SPATIAL] location={location}, "
        f"npc_positions keys={list(_npc_positions.keys())}"
    )

    _player_distances = _scene.get("player_distances", {})
    _npcs_for_builder = []
    for _nid, _npos in _npc_positions.items():
        _dist = _player_distances.get(_nid, 5.0)
        _npcs_for_builder.append({
            "npc_id": _nid,
            "location_id": location,
            "distance_to_player": _dist,
            "facing_towards_player": True,
        })

    return {
        "location_id": location,
        "npcs": _npcs_for_builder,
        "objects": _scene.get("objects", []),
        "light_level": _scene.get("environment", {}).get("light", 1.0),
    }