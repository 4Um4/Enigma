from __future__ import annotations
# path: backend/app/services/scene/scene_event_layer.py
"""
Слой сценовых событий — единые события для восприятия всеми NPC.

Вынесен из game_loop/__init__.py. Инкапсулирует логику эмиссии
и накопления scene events в scene_state.

Назначение: Эмиссия и накопление сценовых событий для восприятия NPC. Вынесено из game_loop.
Зависимости: scene_event_emitter (тот же пакет)
Основные сущности: emit_and_accumulate_scene_events()
"""


import logging
from dataclasses import asdict
from typing import Dict, Any, List

from app.services.scene.scene_event_emitter import SceneEventEmitter

logger = logging.getLogger(__name__)

# Максимальное количество накопленных событий в scene_state
_MAX_ACCUMULATED_EVENTS = 30

# Физические типы действий — обрабатываются через emit_from_physical
_PHYSICAL_ACTION_TYPES = frozenset(
    {
        "player_attacks",
        "player_steals",
        "player_grapples",
    }
)


def emit_and_accumulate_scene_events(
    action_type: str,
    target_id: str,
    location_id: str,
    tick: int,
    action_text: str,
    scene_state: Dict[str, Any],
) -> List[Any]:
    """Эмитит сценовые события и накапливает их в scene_state.

    Returns:
        Список эмиченных SceneEvent объектов.
    """
    scene_events: List[Any] = []
    try:
        emitter = SceneEventEmitter()
        resolved_type = action_type or "player_interacts"

        if resolved_type in _PHYSICAL_ACTION_TYPES:
            scene_events = emitter.emit_from_physical(
                action_type=resolved_type,
                actor_id="player",
                target_id=target_id,
                location_id=location_id,
                tick=tick,
                action_text=action_text,
            )
        else:
            scene_events = emitter.emit_from_verbal(
                actor_id="player",
                location_id=location_id,
                tick=tick,
                action_text=action_text,
                target_id=target_id,
            )

        if scene_events:
            logger.warning(
                f"[SCENE_EVENTS] {len(scene_events)} events emitted: "
                f"{[e.event_type.value for e in scene_events]}"
            )
            # Накопление в scene_state для cross-tick восприятия (БАГ 2)
            _se_accum = scene_state.setdefault("raw_scene_events", [])
            _se_accum.extend(asdict(e) for e in scene_events)
            if len(_se_accum) > _MAX_ACCUMULATED_EVENTS:
                scene_state["raw_scene_events"] = _se_accum[-_MAX_ACCUMULATED_EVENTS:]
            logger.warning(
                f"[SCENE_ACCUM] total={len(_se_accum)} events in scene_state"
            )

    except Exception as err:
        logger.warning(f"[SCENE_EVENTS] error: {err}")

    return scene_events
