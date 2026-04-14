# Reaction Layer — атомарные физические события без LLM
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class MicroEventType(Enum):
    """Типы микро-событий — физические изменения в мире без LLM"""
    OBJECT_DROPPED = "object_dropped"                # NPC уронил предмет
    INTERACTION_DISRUPTED = "interaction_disrupted"  # Текущее действие прервано
    POSTURE_CHANGED = "posture_changed"              # Изменилась поза (отшатнулся, согнулся)
    MOVEMENT_STARTED = "movement_started"            # NPC начал двигаться
    MOVEMENT_STOPPED = "movement_stopped"            # NPC остановился
    GRIP_TIGHTENED = "grip_tightened"                # Сжал оружие/предмет


@dataclass(frozen=True)
class MicroEvent:
    """
    Атомарное физическое событие в мире.
    Генерируется ReactionResolver из DecisionResult, НЕ из LLM.
    Является фактом для SceneContinuity и DMFrame.
    """
    event_type: MicroEventType
    npc_id: str
    trigger: str                    # источник: "threat", "attack", "startle"
    probability: float              # вероятность [0..1], для logging/debug
    details: Dict                   # специфичные данные: {"object": "фляга"}

    def __post_init__(self) -> None:
        # Кап вероятности — защита от баговых значений
        object.__setattr__(self, 'probability', min(1.0, max(0.0, self.probability)))