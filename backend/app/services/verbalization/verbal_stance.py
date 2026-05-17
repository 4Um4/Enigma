"""
VerbalStance — поведенческая форма решения для DM prompt.

path: backend/app/services/verbalization/verbal_stance.py
Назначение: Маппинг Decision → VerbalStance для DM prompt
Зависимости: decision_hub.py (Intent, StateDeltas), npc_state.py (EmotionTag)
Основные сущности: VerbalStance, stance_from_decision()

Не генерирует текст. НЕ вызывает LLM.
ПРЕВРАЩАЕТ: DecisionResult → VerbalStance (stance, tone, urgency)

Принцип: LLM НЕ интерпретирует intent — LLM ИСПОЛНЯЕТ stance.
"""

from dataclasses import dataclass
from typing import Literal, Optional

StanceType = Literal[
    "confront", "threaten", "probe", "dismiss", "submit", "observe", "dissociated"
]
ToneType = Literal[
    "aggressive", "cold", "neutral", "sarcastic", "fearful", "tense"
]
UrgencyLabel = Literal[
    "фоновая", "умеренная", "высокая", "критическая"
]


def _urgency_to_label(value: float) -> UrgencyLabel:
    """Маппинг 0..1 → текстовая категория для LLM."""
    if value < 0.2:
        return "фоновая"
    elif value < 0.5:
        return "умеренная"
    elif value < 0.8:
        return "высокая"
    else:
        return "критическая"


@dataclass(frozen=True)
class VerbalStance:
    """Поведенческая форма — что LLM должен выразить через текст."""
    stance: StanceType
    tone: ToneType
    urgency: float  # 0..1, внутреннее значение

    @property
    def urgency_label(self) -> UrgencyLabel:
        return _urgency_to_label(self.urgency)

    def to_prompt_line(self) -> str:
        """Компактная строка для DM prompt."""
        return f"{self.stance}/{self.tone} (срочность: {self.urgency_label})"


def stance_from_decision(
    intent: str,
    stress: float,
    fear: float,
    trust: float,
    emotion_tag: Optional[str] = None,
    pride: float = 0.5,
    collapse: bool = False,
) -> VerbalStance:
    """
    Маппинг Decision → Stance.

    Вход: числа из DecisionHub (не текст, не контекст).
    Выход: VerbalStance для DM prompt.
    """
    if collapse:
        return VerbalStance(stance="dissociated", tone="fearful", urgency=0.1)

    # Определяем stance по intent
    stance: StanceType = "observe"
    tone: ToneType = "neutral"
    urgency = min(1.0, (stress + fear) / 100.0)

    if intent in ("attack", "intimidate", "warn"):
        if stress > 60 or pride > 0.7:
            stance = "confront"
            tone = "aggressive"
        else:
            stance = "threaten"
            tone = "cold"
    elif intent == "talk":
        if stress > 50:
            stance = "probe"
            tone = "tense"
        elif trust < -20:
            stance = "dismiss"
            tone = "cold"
        else:
            stance = "probe"
            tone = "neutral"
    elif intent == "flee":
        stance = "submit"
        tone = "fearful"
    elif intent == "report":
        stance = "dismiss"
        tone = "cold"
        urgency *= 0.5
    elif intent == "help":
        stance = "probe"
        tone = "neutral"
        urgency *= 0.8
    elif intent == "trade":
        stance = "probe"
        tone = "neutral"
        urgency *= 0.3
    elif intent == "observe":
        if stress > 40:
            tone = "tense"
        else:
            tone = "neutral"
    elif intent == "idle":
        stance = "observe"
        tone = "neutral"
        urgency *= 0.3

    # Коррекция tone по emotion_tag
    if emotion_tag == "angry" and tone not in ("aggressive", "cold"):
        tone = "aggressive"
    elif emotion_tag == "fearful" and tone not in ("fearful", "tense"):
        tone = "fearful"

    return VerbalStance(stance=stance, tone=tone, urgency=round(urgency, 2))