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
TODO: В будущем можно расширить для поддержки объектов, а не только NPC. Сейчас фокус на NPC как цели игрока.
TODO: Возможно, стоит добавить к PlayerTargetResult больше информации о цели (тип, описание) для более богатого взаимодействия с DM. Сейчас только id и name.
TODO: Логирование и мониторинг — сейчас есть базовые логгеры, но можно добавить больше контекста для отладки (например, какие именно переходы детектируются, какие цели извлекаются).
TODO: В detect_and_publish_spatial_transitions() можно добавить фильтрацию по локации или другим параметрам, чтобы не публиковать слишком много событий, если это не нужно. Сейчас все transitions публикуются без фильтрации.
"""
from __future__ import annotations


import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from app.services.action.player_target_extractor import PlayerTargetExtractor

if TYPE_CHECKING:
    from app.services.spatial.spatial_query_service import SpatialQueryService
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayerTargetResult:
    """Результат извлечения цели игрока из текста действия."""

    target_id: str
    target_name: str
    player_pos: Optional[Dict[str, Any]]
    player_dists: Optional[Dict[str, float]]


def extract_player_target(
    load_npcs_fn: Callable[[], List[dict]],
    scene_state: Dict[str, Any],
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
            _npc_ctx_list.append(
                {
                    "npc_id": _nid,
                    "npc_name": _n.get("name", ""),
                    "name_forms": _n.get("name_forms", []),
                    "gender": _n.get("gender", ""),
                }
            )

    _extractor = PlayerTargetExtractor()
    _target_id, _target_name, _target_obj, _player_pos, _player_dists = (
        _extractor.extract(
            action_text=raw_input or "",
            npc_contexts=_npc_ctx_list,
            scene_state=_scene_pre if isinstance(_scene_pre, dict) else {},
        )
    )

    # ADR-048 Phase 2: Запись player_distances/player_position в scene_state ЗАПРЕЩЕНА.
    # SpatialQueryService является единственным авторитетом (Single Spatial Authority).
    # Semantic target всё ещё сохраняется для контекста диалога.
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
) -> List[Any]:
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


def build_spatial_data_for_dm(
    location: str,
    scene_state: Dict[str, Any],
    spatial_query: Optional["SpatialQueryService"] = None,
) -> Dict[str, Any]:
    """Строит spatial_data из scene_state для DM SceneBuilder.
    ADR-048: Дистанции запрашиваются у SpatialQueryService.
    """
    _scene = scene_state
    _npc_positions = _scene.get("npc_positions", {})
    _npc_ids = list(_npc_positions.keys())
    # КРИТИЧЕСКАЯ ДИАГНОСТИКА: почему npc_positions пустой?
    if not _npc_ids:
        _scene_keys = (
            list(_scene.keys())[:10]
            if isinstance(_scene, dict)
            else type(_scene).__name__
        )
        import logging as _log

        _log.getLogger(__name__).error(
            f"[SPATIAL_DATA] EMPTY npc_positions! scene_state keys={_scene_keys}, location={location}"
        )

    # ADR-048: Запрос дистанций у авторитетного сервиса
    if spatial_query:
        _player_distances = spatial_query.player_distances(_npc_ids)
    else:
        # Fallback 1: player_distances из scene_state (non-spatial сборки)
        _scene_dists = _scene.get("player_distances") or {}
        # Fallback 2: вычисляем euclidean из npc_positions
        _player_pos = _npc_positions.get("player", {}).get("local_position", {})
        _px, _py = _player_pos.get("x", 0.0), _player_pos.get("y", 0.0)
        _player_distances = {}
        for _nid in _npc_ids:
            if _nid == "player":
                continue
            if _nid in _scene_dists:
                _player_distances[_nid] = _scene_dists[_nid]
            else:
                _lp = _npc_positions.get(_nid, {}).get("local_position", {})
                _nx, _ny = _lp.get("x"), _lp.get("y")
                if isinstance(_nx, (int, float)) and isinstance(_ny, (int, float)):
                    _player_distances[_nid] = (
                        (_px - _nx) ** 2 + (_py - _ny) ** 2
                    ) ** 0.5

    _npcs_for_builder = []
    for _nid in _npc_ids:
        if _nid == "player":
            continue  # Игрок не должен быть в nearby_npcs
        _dist = _player_distances.get(_nid)
        if _dist is None:
            continue  # Нет дистанции — не включаем (bug_risk: 999.0 ломает фильтр видимости)
        _npcs_for_builder.append(
            {
                "npc_id": _nid,
                "location_id": location,
                "distance_to_player": _dist,
                "facing_towards_player": True,
            }
        )
    # Диагностика: почему nearby_npcs может быть пустым?
    _player_lp = _npc_positions.get("player", {}).get("local_position", {})
    _has_player = "player" in _npc_positions
    _player_xy_valid = isinstance(_player_lp.get("x"), (int, float)) and isinstance(
        _player_lp.get("y"), (int, float)
    )
    import logging as _log

    _log.getLogger(__name__).warning(
        f"[SPATIAL_DATA] result={len(_npcs_for_builder)}/{len(_npc_ids)}, has_player={_has_player}, player_xy_valid={_player_xy_valid}, spatial_query={spatial_query is not None}, distances_sample={list(_player_distances.items())[:3]}"
    )

    return {
        "location_id": location,
        "npcs": _npcs_for_builder,
        "objects": _scene.get("objects", []),
        "light_level": _scene.get("environment", {}).get("light", 1.0),
    }
