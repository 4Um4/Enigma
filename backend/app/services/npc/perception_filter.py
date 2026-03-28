# backend/app/services/npc/perception_filter.py
#
# Phase 3B.3 — Perception Filter
#
# Принцип из roadmap v8.1:
#   AFFORDANCE CHECK сначала (physics_validator — невозможное не публикуется)
#   PERCEPTION FILTER потом — кто из NPC видит/слышит конкретный GameEvent
#
# NPC за стеной НЕ реагирует на тихое действие.
# NPC в соседней комнате НЕ видит что происходит здесь.
# Но громкий звук (radius=20) — слышат все в радиусе.
#
# Вызывается из action/processor.py после event_bus.publish().
# Результат: список npc_id которые воспринимают событие.

from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Минимальная освещённость при которой NPC что-то видит
_MIN_LIGHT_FOR_SIGHT = "dim"  # dark → не видит, dim/bright/natural → видит

_LIGHT_LEVELS = {
    "dark":     0,
    "dim":      1,
    "torchlit": 2,
    "natural":  3,
    "bright":   4,
}


def _npc_distance(npc_id: str, scene_state: dict) -> float:
    """Расстояние от NPC до игрока. Fallback: 999 (далеко)."""
    return float(scene_state.get("player_distances", {}).get(npc_id, 999.0))


def _npc_is_conscious(npc_id: str, scene_state: dict) -> bool:
    """NPC не спит и не без сознания."""
    pos = scene_state.get("npc_positions", {}).get(npc_id, {})
    state = pos.get("state", "").lower()
    activity = pos.get("activity", "").lower()
    incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}
    return state not in incap and activity not in {"sleeping", "спит"}


def _can_see(npc_id: str, scene_state: dict, event_location: str) -> bool:
    """
    NPC может видеть событие если:
      - находится в той же локации
      - не спит
      - освещение позволяет (не dark)
    """
    npc_location = scene_state.get("npc_positions", {}).get(npc_id, {}).get("location", "")
    if npc_location and npc_location != event_location:
        return False  # разные локации — не видит

    if not _npc_is_conscious(npc_id, scene_state):
        return False

    light = scene_state.get("environment", {}).get("light_level", "dim")
    return _LIGHT_LEVELS.get(light, 1) >= _LIGHT_LEVELS[_MIN_LIGHT_FOR_SIGHT]


def _can_hear(npc_id: str, scene_state: dict, radius: float) -> bool:
    """
    NPC может слышать событие если:
      - не спит (громкий звук будит — проверяем отдельно)
      - находится в радиусе звука
    """
    if not _npc_is_conscious(npc_id, scene_state):
        # Только очень громкий звук (radius > 15) будит спящего
        if radius <= 15.0:
            return False

    distance = _npc_distance(npc_id, scene_state)
    return distance <= radius


def filter_perceiving_npcs(
    npc_ids:        List[str],
    event,                      # GameEvent или dict
    scene_state:    dict,
) -> List[str]:
    """
    Возвращает список npc_id которые воспринимают данный GameEvent.

    Логика:
      1. Если event.visible_to задан явно — используем его напрямую.
      2. Иначе — проверяем visible_to=[] (broadcast) через sight/sound фильтры.

    Аргументы:
        npc_ids    — все NPC в локации
        event      — GameEvent (объект или dict)
        scene_state — текущий SceneState
    """
    if not npc_ids:
        return []

    # Извлекаем поля события
    if hasattr(event, "visible_to"):
        visible_to  = event.visible_to  or []
        audible_to  = event.audible_to  or []
        radius      = float(getattr(event, "radius", 999.0))
        location    = getattr(event, "location", "")
        event_type  = str(
            event.event_type.name
            if hasattr(event.event_type, "name")
            else event.event_type
        )
    elif isinstance(event, dict):
        visible_to  = event.get("visible_to", [])
        audible_to  = event.get("audible_to", [])
        radius      = float(event.get("radius", 999.0))
        location    = event.get("location", "")
        event_type  = str(event.get("event_type", ""))
    else:
        return npc_ids  # неизвестный формат — все воспринимают

    perceiving = []

    for npc_id in npc_ids:
        # Явный список visible_to — только они
        if visible_to and npc_id not in visible_to:
            continue

        # Явный список audible_to — только они (если нет visible_to)
        if audible_to and not visible_to and npc_id not in audible_to:
            continue

        # Звуковые события — проверяем слух
        sound_events = {"SOUND_EMITTED", "OBJECT_DESTROYED", "PLAYER_ATTACKED"}
        if event_type in sound_events:
            if _can_hear(npc_id, scene_state, radius):
                perceiving.append(npc_id)
            continue

        # Визуальные события — проверяем зрение
        if _can_see(npc_id, scene_state, location):
            perceiving.append(npc_id)

    logger.debug(
        f"[PERCEPTION_FILTER] {event_type}: "
        f"{len(perceiving)}/{len(npc_ids)} NPC воспринимают событие"
    )
    return perceiving


def build_perception_context(
    npc_id:      str,
    npc_name:    str,
    event,
    scene_state: dict,
) -> str:
    """
    Строит строку для промпта NPC описывающую что именно он воспринял.
    Используется в npc_agent._build_phase3a_prompt() для реакций на события.

    Примеры:
      "Ты слышишь громкий треск — что-то сломали."
      "Ты видишь как игрок атакует кого-то рядом."
    """
    if hasattr(event, "event_type"):
        event_type = str(
            event.event_type.name
            if hasattr(event.event_type, "name")
            else event.event_type
        )
        params = getattr(event, "parameters", {})
        actor  = getattr(event, "actor_id", "кто-то")
    elif isinstance(event, dict):
        event_type = str(event.get("event_type", ""))
        params     = event.get("parameters", {})
        actor      = event.get("actor_id", "кто-то")
    else:
        return ""

    distance = _npc_distance(npc_id, scene_state)
    dist_str = f"(~{distance:.0f} м)" if distance < 999 else ""

    _TEMPLATES = {
        "OBJECT_DESTROYED": f"Ты слышишь треск и грохот {dist_str} — что-то уничтожили.",
        "OBJECT_CHANGED":   f"Ты замечаешь что {params.get('target_name', 'объект')} изменился {dist_str}.",
        "PLAYER_ATTACKED":  f"Ты видишь как {actor} атакует кого-то {dist_str}. Угроза реальна.",
        "SOUND_EMITTED":    f"Ты слышишь {params.get('description', 'звук')} {dist_str}.",
        "NPC_STATE_CHANGED": f"Ты замечаешь что с кем-то рядом что-то происходит {dist_str}.",
        "PLAYER_SPOKE":     f"{actor} обращается к кому-то {dist_str}.",
        "LIGHT_CHANGED":    f"Освещение в помещении изменилось.",
    }

    return _TEMPLATES.get(event_type, f"Ты замечаешь событие: {event_type} {dist_str}.")