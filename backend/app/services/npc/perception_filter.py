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
from app.services.npc.spatial_runtime import (
    extract_scene_for_npc,
    line_of_sight,
    resolve_distance_between_entities,
    sound_reach,
)

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


import math

def _get_position(entity_data: dict) -> Optional[tuple[float, float]]:
    """
    Извлекает (x, y) из словаря позиции.
    Возвращает None если координаты отсутствуют — для обратной совместимости.
    """
    x = entity_data.get("x")
    y = entity_data.get("y")
    if x is not None and y is not None:
        return float(x), float(y)
    return None


def _euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Евклидово расстояние между двумя точками (x, y)."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def calculate_clarity(
    distance: float,
    light_level: str,
    npc_stress: float = 0.0,
) -> float:
    """
    R5.3 — вычисляет clarity восприятия события.
    Используется при создании EventMemory из GameEvent.
    clarity = f(distance, light, stress)
    Высокая clarity → детальное воспоминание.
    """
    base = 1.0

    # Дистанция снижает чёткость
    if distance > 15.0:
        base -= 0.4
    elif distance > 10.0:
        base -= 0.2

    # Освещение
    if light_level == "dim":
        base -= 0.15
    elif light_level == "dark":
        base -= 0.4

    # Стресс мешает запомнить детали
    if npc_stress > 70.0:
        base -= 0.2
    elif npc_stress > 50.0:
        base -= 0.1

    return round(max(0.0, min(1.0, base)), 3)


def _npc_distance(npc_id: str, scene_state: dict) -> float:
    """
    Расстояние от NPC до игрока в метрах.
    R4.3: использует player_spatial (canonical) → resolve_distance_between_entities.
    Fallback 1: прямое Евклидово расстояние из x/y в npc_data и player_position.
    Fallback 2: player_distances словарь (до R4.3) → 999.0.
    """
    npc_data    = scene_state.get("npc_positions", {}).get(npc_id, {})
    player_data = scene_state.get("player_spatial", {})

    # Приоритет 1: graph-based расстояние через player_spatial
    if npc_data and player_data and isinstance(player_data, dict):
        spatial_distance = resolve_distance_between_entities(scene_state, npc_data, player_data)
        if spatial_distance < 999.0:
            return spatial_distance

    # Приоритет 2: прямое Евклидово по x/y если player_position это dict с координатами.
    # Защита: player_position может быть строкой ("стоит") — тогда пропускаем.
    player_pos_raw = scene_state.get("player_position")
    if isinstance(player_pos_raw, dict):
        npc_pos    = _get_position(npc_data)
        player_pos = _get_position(player_pos_raw)
        if npc_pos is not None and player_pos is not None:
            return _euclidean(npc_pos, player_pos)

    # Fallback: предвычисленный словарь (совместимость с до-R4.3)
    _dist = float(scene_state.get("player_distances", {}).get(npc_id, 999.0))
    if _dist >= 15.0:
        return False
    return True


def _npc_is_conscious(npc_id: str, scene_state: dict) -> bool:
    """NPC не спит и не без сознания."""
    pos = scene_state.get("npc_positions", {}).get(npc_id, {})
    state = pos.get("state", "").lower()
    activity = pos.get("activity", "").lower()
    incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}
    return state not in incap and activity not in {"sleeping", "спит"}


def _can_see(npc_id: str, scene_state: dict, event_location: str) -> bool:
    """
    NPC видит событие если:
      - R4.3: находится в радиусе зрения (≤ 15м по координатам)
      - Fallback: та же строковая локация
      - Не спит, освещение достаточное
    """
    if not _npc_is_conscious(npc_id, scene_state):
        return False

    npc_data      = scene_state.get("npc_positions", {}).get(npc_id, {})
    player_spatial = scene_state.get("player_spatial")

    # Приоритет 1: graph-based дистанция через player_spatial
    if npc_data and isinstance(player_spatial, dict) and player_spatial:
        distance = resolve_distance_between_entities(scene_state, npc_data, player_spatial)
        if distance >= 999.0:
            return False
        if not line_of_sight(distance, scene_state):
            return False

    else:
        # Приоритет 2: Евклидово из x/y если оба словаря содержат координаты
        player_pos_raw = scene_state.get("player_position")
        npc_pos    = _get_position(npc_data)
        player_pos = _get_position(player_pos_raw) if isinstance(player_pos_raw, dict) else None

        if npc_pos is not None and player_pos is not None:
            # Оба имеют координаты — считаем напрямую
            if _euclidean(npc_pos, player_pos) > 15.0:
                return False
        else:
            # Приоритет 3: нет координат — проверяем по строке локации
            npc_location = npc_data.get("location", "")
            if npc_location and npc_location != event_location:
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
    return distance <= sound_reach(radius, scene_state)


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


def extract_scene_awareness(
    npc_id: str,
    npc_ids: List[str],
    scene_state: dict,
) -> dict:
    """
    R4.5 Scene Extraction:
      - кто рядом
      - какие действия доступны в текущем пространстве
    """
    return extract_scene_for_npc(scene_state, npc_id=npc_id, npc_ids=npc_ids)
