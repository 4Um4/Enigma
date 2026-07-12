"""
app/services/player_cognition/perception_layer.py
Perception Layer — определяет видимость и слышимость сущностей для игрока.
Переиспользует calculate_clarity и sound_reach, но не привязан к NPC.

path: /backend/app/services/player_cognition/perception_layer.py
Назначение: Определяет видимость и слышимость каждой сущности для игрока, генерирует AudioEvent для невидимых источников звука
Зависимости: spatial_runtime, perception_filter (calculate_clarity, sound_reach), types
Основные сущности: apply_perception()
"""

from typing import List, Tuple

from app.core.constants import PERCEPTION_RADIUS
from app.services.npc.perception_filter import calculate_clarity
from app.services.player_cognition.types import AudioEvent, PerceivedEntity
from app.services.spatial.spatial_runtime import sound_reach

# Игрок — всегда "major" tier, полный радиус восприятия
_PLAYER_PERCEPTION_RADIUS = PERCEPTION_RADIUS["major"]  # 15.0м

# Базовый радиус тихого звука — слышно без специального события
_QUIET_SOUND_RADIUS = 3.0


def _light_level(scene_state: dict) -> str:
    """Извлекает уровень освещения из SceneState"""
    env = scene_state.get("environment", {})
    return env.get("light_level", "dim")


def _is_visible(entity: PerceivedEntity, scene_state: dict) -> Tuple[bool, float]:
    """
    Проверяет видимость сущности: расстояние + LOS + свет.

    Returns:
        (visible, clarity)
    """
    # За пределами радиуса — не видно
    if entity.distance > _PLAYER_PERCEPTION_RADIUS:
        return False, 0.0

    # LOS заблокирован — не видно (но может быть слышно)
    if not entity.los:
        return False, 0.0

    # Проверка освещения
    light = _light_level(scene_state)
    # dim = минимум для зрения, dark = не видит
    if light == "dark":
        return False, 0.0

    # Вычисляем чёткость восприятия
    clarity = calculate_clarity(
        distance=entity.distance,
        light_level=light,
        npc_stress=0.0,  # stress игрока обрабатывается в Attention/Cognitive слоях
    )

    return True, clarity


def _is_audible(
    entity: PerceivedEntity,
    scene_state: dict,
    entity_data: dict,
) -> Tuple[bool, float]:
    """
    Проверяет слышимость сущности.
    Звук проходит через стены (ослабляется density), но не исчезает полностью.

    Returns:
        (audible, sound_reach_radius)
    """
    reach = sound_reach(_QUIET_SOUND_RADIUS, scene_state)
    audible = entity.distance <= reach

    # Объекты без активности обычно не издают звук
    if entity.entity_type == "object":
        state = entity_data.get("state", "")
        if state in ("intact", "broken"):
            return False, reach

    return audible, reach


def apply_perception(
    entities: List[PerceivedEntity],
    scene_state: dict,
) -> List[AudioEvent]:
    """
    Заполняет Perception Layer на каждой PerceivedEntity.
    Генерирует AudioEvent для сущностей, которые слышно, но не видно.

    Returns:
        Список AudioEvent (звуки без видимого источника)
    """
    audio_events: List[AudioEvent] = []

    for entity in entities:
        raw = entity._raw_data

        # Видимость
        visible, clarity = _is_visible(entity, scene_state)
        entity.visible = visible
        entity.clarity = clarity

        # Слышимость
        audible, reach = _is_audible(entity, scene_state, raw)
        entity.audible = audible

        # Слышно, но не видно — audio_only
        entity.audio_only = audible and not visible

        # Генерируем AudioEvent для невидимых audible сущностей
        if entity.audio_only:
            description = _audio_description(entity, raw)
            direction = _audio_direction(entity)
            audio_events.append(
                AudioEvent(
                    description=description,
                    direction=direction,
                    approximate_distance=entity.distance,
                    confidence=0.5,  # базовая неопределённость для невидимого источника
                )
            )

    return audio_events


def _audio_description(entity: PerceivedEntity, raw: dict) -> str:
    """Генерирует текстовое описание звука на основе типа сущности"""
    if entity.entity_type == "npc":
        activity = raw.get("activity", "")
        if activity:
            return f"звуки: {activity}"
        return "шаги, движение"
    else:
        # Объект — редко издаёт звук сам по себе
        return "звук"


def _audio_direction(entity: PerceivedEntity) -> str | None:
    """
    Определяет примерное направление звука.
    Точное — только если LOS заблокирован известным препятствием.
    """
    if entity.los_blocked_by == "wall":
        return "за стеной"
    if entity.los_blocked_by == "obstacle":
        return "за чем-то"
    # Не видно по расстоянию — направление приблизительное
    return None
