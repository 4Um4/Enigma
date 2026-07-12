from __future__ import annotations
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
# Вызывается из game_loop.py после event_bus.publish().
# Результат: список npc_id которые воспринимают событие.
"""
TODO: после полной миграции на EventDTO удалить поддержку dict и GameEvent в аргументах.
TODO: после миграции на EventDTO удалить временную заглушку с visible_to/audible_to в GameEvent.
TODO: расширение функционала — добавить дополнительные факторы в clarity (погода, состояние NPC, тип события и т.д.)
TODO: оптимизация — кэшировать результаты perception для каждого NPC в течение одного тика, чтобы не пересчитывать для каждого события.
TODO: расширение функционала — добавить поддержку разных типов восприятия (зрение, слух, обоняние) с разными радиусами и условиями.
TODO: расширение функционала — добавить поддержку разных типов событий (визуальные, звуковые, тактильные) с разными шаблонами восприятия.
TODO: расширение функционала — учитывать направление взгляда NPC для более реалистичного восприятия.
TODO: расширение функционала — учитывать динамические изменения в сцене (движущиеся объекты, открывающиеся двери) при расчёте line of sight.
TODO: расширение функционала — добавить поддержку "слепых зон" (например, NPC не видит за спиной).
TODO: расширение функционала — учитывать индивидуальные особенности NPC (например, плохое зрение, глухота) при расчёте восприятия.
TODO: расширение функционала — добавить поддержку "интуиции" (например, NPC может "чувствовать" присутствие игрока даже если не видит его напрямую).
TODO: расширение функционала — добавить поддержку "слуховой маскировки" (например, если игрок стоит на ковре, его шаги менее слышны).
TODO: расширение функционала — добавить поддержку "визуальной маскировки" (например, если игрок прячется в тени, его сложнее заметить).
TODO: расширение функционала — добавить поддержку "шумовой маскировки" (например, если рядом есть громкий источник звука, NPC с меньшей вероятностью услышит тихое действие).
TODO: расширение функционала — добавить поддержку "социального восприятия" (например, NPC может заметить изменения в поведении других NPC, даже если не видит игрока напрямую).
TODO: расширение функционала — добавить поддержку "эмоционального восприятия" (например, NPC может почувствовать страх или агрессию игрока, даже если не видит его напрямую).
TODO: расширение формулы clarity — добавить нелинейные эффекты (например, очень близкие объекты воспринимаются значительно чётче, чем просто "на 1 метр ближе").
TODO: расширение формулы clarity — добавить эффект "порогового восприятия" (например, если distance > 15, clarity резко падает до 0, а не плавно).
TODO: расширение формулы clarity — добавить эффект "насыщения" (например, если свет слишком яркий, clarity может начать снижаться из-за ослепления).
TODO: расширение формулы clarity — добавить эффект "стрессового искажения" (например, при очень высоком стрессе NPC может начать воспринимать события искажённо, снижая clarity для определённых типов событий).
"""

import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.spatial.spatial_query_service import SpatialQueryService

from app.domain.events import EventDTO
from app.services.spatial.spatial_runtime import (
    extract_scene_for_npc,
    line_of_sight,
    sound_reach,
)

logger = logging.getLogger(__name__)

# Минимальная освещённость при которой NPC что-то видит
_MIN_LIGHT_FOR_SIGHT = "dim"  # dark → не видит, dim/bright/natural → видит

_LIGHT_LEVELS = {
    "dark": 0,
    "dim": 1,
    "torchlit": 2,
    "natural": 3,
    "bright": 4,
}


import math


def _get_position(entity_data: Dict[str, Any]) -> Optional[tuple[float, float]]:
    """
    Извлекает (x, y) из словаря позиции.
    Возвращает None если координаты отсутствуют — для обратной совместимости.
    """
    x = entity_data.get("x")
    y = entity_data.get("y")
    # Sourcery: assign-if-exp для компактности
    return (float(x), float(y)) if x is not None and y is not None else None


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
    Используется при создании EventMemory из EventDTO.
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


def _npc_distance(npc_id: str, spatial_query: "SpatialQueryService") -> float:
    """
    Расстояние от NPC до игрока в метрах.
    ADR-048 Phase 2: Единственный источник истины — SpatialQueryService.
    Фоллбэки удалены как нарушающие Single Spatial Authority.
    """
    if not spatial_query:
        return 999.0
    # Запрашиваем дистанцию у фасада пространственного авторитета
    distances = spatial_query.player_distances([npc_id])
    return distances.get(npc_id, 999.0)


def _npc_is_conscious(npc_id: str, scene_state: Dict[str, Any]) -> bool:
    """NPC не спит и не без сознания."""
    pos = scene_state.get("npc_positions", {}).get(npc_id, {})
    state = pos.get("state", "").lower()
    activity = pos.get("activity", "").lower()
    incap = {"dead", "unconscious", "sleeping", "спит", "без сознания", "мёртв"}
    return state not in incap and activity not in {"sleeping", "спит"}


def _can_see(
    npc_id: str,
    spatial_query: "SpatialQueryService",
    event_location: str,
    scene_state: Dict[str, Any],
) -> bool:
    """
    NPC видит событие если:
      - ADR-048: пространственная дистанция запрашивается у SpatialQueryService
      - Не спит, находится в радиусе зрения (≤ 15м), освещение достаточное
    """
    if not _npc_is_conscious(npc_id, scene_state):
        return False

    # ADR-048: Дистанция только через SpatialQueryService, никаких фоллбэков
    distance = _npc_distance(npc_id, spatial_query)

    if distance >= 999.0:
        return False

    # R4: Жёсткий cap 15m — NPC не воспринимает за пределами радиуса
    if distance >= 15.0:
        return False

    if not line_of_sight(distance, scene_state):
        return False

    light = scene_state.get("environment", {}).get("light_level", "dim")
    return _LIGHT_LEVELS.get(light, 1) >= _LIGHT_LEVELS[_MIN_LIGHT_FOR_SIGHT]


def _can_hear(
    npc_id: str, spatial_query: "SpatialQueryService", radius: float, scene_state: Dict[str, Any]
) -> bool:
    """
    NPC может слышать событие если:
      - не спит (громкий звук будит — проверяем отдельно)
      - находится в радиусе звука
    """
    # Только очень громкий звук (radius > 15) будит спящего
    if not _npc_is_conscious(npc_id, scene_state) and radius <= 15.0:
        return False

    distance = _npc_distance(npc_id, spatial_query)
    return distance <= sound_reach(radius, scene_state)


def filter_perceiving_npcs(
    npc_ids: List[str],
    event,  # GameEvent или dict
    scene_state: Dict[str, Any],
    spatial_query: "SpatialQueryService",
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
    if isinstance(event, EventDTO):
        # EventDTO: нет явных списков visible_to/audible_to — фильтруем через radius/sight/sound
        visible_to = []
        audible_to = []
        radius = event.radius
        location = event.payload.get("location", "")
        event_type = event.type
    elif hasattr(event, "visible_to"):
        # TODO: временная заглушка — будет удалена после полного удаления GameEvent
        visible_to = event.visible_to or []
        audible_to = event.audible_to or []
        radius = float(getattr(event, "radius", 999.0))
        location = getattr(event, "location", "")
        event_type = str(
            event.event_type.name
            if hasattr(event.event_type, "name")
            else event.event_type
        )
    elif isinstance(event, dict):
        visible_to = event.get("visible_to", [])
        audible_to = event.get("audible_to", [])
        radius = float(event.get("radius", 999.0))
        location = event.get("location", "")
        event_type = str(event.get("event_type", ""))
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

        # Звуковые события — проверяем слух (речь слышна дальше чем видна)
        sound_events = {
            "SOUND_EMITTED",
            "OBJECT_DESTROYED",
            "PLAYER_ATTACKED",
            "PLAYER_SPOKE",
        }
        if event_type in sound_events:
            if _can_hear(npc_id, spatial_query, radius, scene_state):
                perceiving.append(npc_id)
            continue

        # Визуальные события — проверяем зрение
        if _can_see(npc_id, spatial_query, location, scene_state):
            perceiving.append(npc_id)
        else:
            _dist = _npc_distance(npc_id, spatial_query)
            logger.debug(f"[PERCEPTION_SKIP] {npc_id}: dist={_dist:.1f}m (not visible)")

    logger.debug(
        f"[PERCEPTION_FILTER] {event_type}: "
        f"{len(perceiving)}/{len(npc_ids)} NPC воспринимают событие"
    )
    return perceiving


def build_perception_context(
    npc_id: str,
    npc_name: str,
    event,
    scene_state: Dict[str, Any],
    spatial_query: Optional["SpatialQueryService"] = None,
) -> str:
    """
    Строит строку для промпта NPC описывающую что именно он воспринял.
    Используется в npc_agent._build_phase3a_prompt() для реакций на события.

    Примеры:
      "Ты слышишь громкий треск — что-то сломали."
      "Ты видишь как игрок атакует кого-то рядом."
    """
    if isinstance(event, EventDTO):
        event_type = event.type
        params = event.payload
        actor = event.source or "кто-то"
    elif hasattr(event, "event_type"):
        # TODO: временная заглушка — будет удалена после полного удаления GameEvent
        event_type = str(
            event.event_type.name
            if hasattr(event.event_type, "name")
            else event.event_type
        )
        params = getattr(event, "parameters", {})
        actor = getattr(event, "actor_id", "кто-то")
    elif isinstance(event, dict):
        event_type = str(event.get("event_type", ""))
        params = event.get("parameters", {})
        actor = event.get("actor_id", "кто-то")
    else:
        return ""

    distance = _npc_distance(npc_id, spatial_query)
    dist_str = f"(~{distance:.0f} м)" if distance < 999 else ""

    _TEMPLATES = {
        "OBJECT_DESTROYED": f"Ты слышишь треск и грохот {dist_str} — что-то уничтожили.",
        "OBJECT_CHANGED": f"Ты замечаешь что {params.get('target_name', 'объект')} изменился {dist_str}.",
        "PLAYER_ATTACKED": f"Ты видишь как {actor} атакует кого-то {dist_str}. Угроза реальна.",
        "SOUND_EMITTED": f"Ты слышишь {params.get('description', 'звук')} {dist_str}.",
        "NPC_STATE_CHANGED": f"Ты замечаешь что с кем-то рядом что-то происходит {dist_str}.",
        "PLAYER_SPOKE": f"{actor} обращается к кому-то {dist_str}.",
        "LIGHT_CHANGED": "Освещение в помещении изменилось.",
    }

    return _TEMPLATES.get(event_type, f"Ты замечаешь событие: {event_type} {dist_str}.")


def extract_scene_awareness(
    npc_id: str,
    npc_ids: List[str],
    scene_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    R4.5 Scene Extraction:
      - кто рядом
      - какие действия доступны в текущем пространстве
    """
    return extract_scene_for_npc(scene_state, npc_id=npc_id, npc_ids=npc_ids)
