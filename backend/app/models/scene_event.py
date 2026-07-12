"""
path: /backend/app/models/scene_event.py
Назначение: Единая структура события для восприятия всеми NPC
Зависимости: dataclasses, enum
Основные сущности: SceneEventType, SceneEvent
"""

from dataclasses import dataclass
from enum import Enum


class SceneEventType(str, Enum):
    """Типы событий которые NPC могут воспринимать."""

    VIOLENCE = "violence"  # физическое воздействие
    VERBAL = "verbal"  # речь (крик, угроза, вопрос)
    MOVEMENT = "movement"  # перемещение в сцене
    ITEM_INTERACT = "item_interact"  # взаимодействие с предметом
    EMOTIONAL = "emotional"  # проявление эмоции (смех, плач)
    COMBAT_START = "combat_start"  # начало боя
    NPC_INJURED = "npc_injured"  # NPC получил урон
    NPC_DEATH = "npc_death"  # NPC погиб


@dataclass(frozen=True)
class SceneEvent:
    """
    Единое событие сцены — источник восприятия для всех NPC.
    Создаётся из PhysicalOutcome, PlayerAction, или NPC reactions.
    """

    event_type: SceneEventType
    actor_id: str  # кто инициировал ("player", "maid_lusya")
    target_id: str  # на кого направлено ("" если нет цели)
    location_id: str  # где произошло
    tick: int  # игровой тик
    intensity: float  # 0.0-1.0 — насколько заметно
    visibility_radius: float  # в метрах — максимальная дистанция восприятия
    summary: str  # человекочитаемое: "Игрок ударил Люсю кулаком"

    # Опциональные контекстные данные
    damage: int = 0
    damage_type: str = ""
    emotion_tag: str = ""
    sound_level: float = 0.5  # 0=тихо, 1=крик
