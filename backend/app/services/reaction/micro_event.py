# Reaction Layer — атомарные физические события без LLM
from dataclasses import dataclass
from enum import Enum
from typing import List, Any, Dict


class MicroEventType(Enum):
    """Типы микро-событий — визуальные изменения в сцене без LLM"""

    # ── Реакция (осознанная, после DecisionHub) ──
    OBJECT_DROPPED = "object_dropped"  # NPC уронил предмет
    INTERACTION_DISRUPTED = "interaction_disrupted"  # Текущее действие прервано
    POSTURE_CHANGED = "posture_changed"  # Изменилась поза (отшатнулся, согнулся)
    MOVEMENT_STARTED = "movement_started"  # NPC начал двигаться
    MOVEMENT_STOPPED = "movement_stopped"  # NPC остановился
    GRIP_TIGHTENED = "grip_tightened"  # Сжал оружие/предмет
    # ── Рефлекс (мгновенный, до DecisionHub) ──
    STAGGERED = "staggered"  # Отшатнулся от удара
    CRY_OF_PAIN = "cry_of_pain"  # Вскрикнул от боли
    BLOOD_SPATTER = "blood_spatter"  # Кровь на полу/стенах/предметах
    WEAPON_DROPPED_FORCE = "weapon_dropped_force"  # Выпал из руки от силы удара
    FELL_TO_GROUND = "fell_to_ground"  # Упал на землю
    FLINCHED = "flinched"  # Дёрнулся (микро-движение)
    ITEM_DAMAGED = "item_damaged"  # Предмет повреждён (щит, броня)


@dataclass(frozen=True)
class MicroEvent:
    """
    Атомарное физическое событие в мире.
    Генерируется ReactionResolver из DecisionResult, НЕ из LLM.
    Является фактом для SceneContinuity и DMFrame.
    """

    event_type: MicroEventType
    npc_id: str
    trigger: str  # источник: "threat", "attack", "startle"
    probability: float  # вероятность [0..1], для logging/debug
    details: Dict  # специфичные данные: {"object": "фляга"}

    def __post_init__(self) -> None:
        # Кап вероятности — защита от баговых значений
        object.__setattr__(self, "probability", min(1.0, max(0.0, self.probability)))
