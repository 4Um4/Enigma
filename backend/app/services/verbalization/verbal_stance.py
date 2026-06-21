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
    emotion_tag: Optional[str] = None,
) -> VerbalStance:
    """
    Маппинг Decision → Stance (Symbolic Interpretation Layer).
    
    Epistemic Boundary: Форма поведения выводится исключительно из наблюдаемых 
    действий (intent + emotion). Числовые ментальные поля (stress, fear, trust) 
    остаются скрытой причинностью в simulation layer и не экспонируются.
    """
    stance: StanceType = "observe"
    tone: ToneType = "neutral"
    urgency = 0.3  # Базовая срочность

    if intent in ("attack", "intimidate", "warn"):
        stance = "confront" if emotion_tag == "angry" else "threaten"
        tone = "aggressive" if emotion_tag == "angry" else "cold"
        urgency = 0.8
    elif intent == "talk":
        stance = "probe"
        tone = "tense" if emotion_tag == "fearful" else "neutral"
        urgency = 0.5
    elif intent == "flee":
        stance = "submit"
        tone = "fearful"
        urgency = 0.9
    elif intent == "report":
        stance = "dismiss"
        tone = "cold"
        urgency = 0.4
    elif intent == "help":
        stance = "probe"
        tone = "neutral"
        urgency = 0.6
    elif intent == "trade":
        stance = "probe"
        tone = "neutral"
        urgency = 0.3
    elif intent in ("observe", "idle"):
        stance = "observe"
        tone = "tense" if emotion_tag == "fearful" else "neutral"
        urgency = 0.2

    # Override при панике (сигнал от ядра о коллапсе воли)
    if emotion_tag == "panic":
        stance = "dissociated"
        tone = "fearful"
        urgency = 0.1

    return VerbalStance(stance=stance, tone=tone, urgency=round(urgency, 2))