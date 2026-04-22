# backend/app/services/verbalization/verbalization_context.py
"""
VerbalizationContext — контекст для NPC вербализации.

Используется в game_loop.py для упаковки состояния NPC.
generate_emotional_nuance — Python-генерация описания эмоции из чисел.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    NPCPersonality,
    NPCState,
    WillState,
)


@dataclass(frozen=True)
class ContentProfile:
    """Профиль разрешённого контента для вербализации NPC."""
    profanity_level: int = 0
    violence_level: int = 0

    def __post_init__(self) -> None:
        if not (0 <= self.profanity_level <= 2):
            raise ValueError(f"profanity_level должен быть 0-2, получено: {self.profanity_level}")
        if not (0 <= self.violence_level <= 2):
            raise ValueError(f"violence_level должен быть 0-2, получено: {self.violence_level}")


@dataclass(frozen=True)
class VerbalizationContext:
    """
    То что LLM получает для генерации речи NPC.
    Вся фактура сгенерирована Python из чисел.
    """
    npc_id: str
    npc_name: str
    tier: str

    # Состояние — только качественные описания
    emotion: str
    will_state: str
    intent: str
    intent_target: Optional[str]

    # Python-сгенерированная фактура
    scene_hint: str
    emotional_nuance: str
    speech_style: str
    voice_profile: str
    backstory: str

    # Физические ограничения — для ResponseValidator
    can_speak: bool = True
    can_move: bool = True

    # Контент
    content_profile: ContentProfile = field(default_factory=ContentProfile)

    # Narrative
    narrative_hints: Tuple[NarrativeFact, ...] = field(default_factory=tuple)
    is_explain_mode: bool = False


# Описания will_state — единый источник для промпта
_WILL_STATE_NUANCE: dict[str, str] = {
    WillState.BROKEN.value: "полностью сломлен — подчиняется из страха, голос дрожит",
    WillState.COERCED.value: "внешне подчиняется, внутри затаил злость",
    WillState.DECEPTIVE.value: "притворяется, ждёт момента для предательства",
    WillState.LOYAL.value: "искренне предан, готов помочь",
}


def generate_emotional_nuance(state: NPCState) -> str:
    """
    Python генерирует полное описание состояния NPC из чисел.
    Включает эмоцию, трейты и will_state — единая строка для LLM.
    """
    parts: list[str] = []
    stress = state.stress
    traits = state.state_modifiers

    if state.emotion == EmotionTag.ANGRY:
        if stress > 70:
            parts.append("зол, едва сдерживается — голос на грани срыва")
        elif stress < 30:
            parts.append("зол холодно и расчётливо")
        else:
            parts.append("раздражён")
    elif state.emotion == EmotionTag.FEARFUL:
        if stress > 70:
            parts.append("напуган до дрожи, оглядывается")
        else:
            parts.append("настороженный, готов к бегству")
    elif state.emotion == EmotionTag.GRATEFUL:
        if traits.get("suspicious", 0) > 0.4:
            parts.append("благодарен, но всё ещё подозревает подвох")
        else:
            parts.append("искренне благодарен")
    elif state.emotion == EmotionTag.SUSPICIOUS:
        parts.append("подозревает подвох в каждом слове")
    elif state.emotion == EmotionTag.NEUTRAL:
        if stress > 60:
            parts.append("внешне спокоен, внутри напряжён")

    # Трейты (overlay)
    if traits.get("suspicious", 0) > 0.6 and state.emotion != EmotionTag.SUSPICIOUS:
        parts.append("недоверчиво прищуривается")
    if traits.get("grateful", 0) > 0.5 and state.emotion != EmotionTag.GRATEFUL:
        parts.append("помнит добро, которое ты сделал")

    # Will state
    will_nuance = _WILL_STATE_NUANCE.get(state.will_state.value)
    if will_nuance:
        parts.append(will_nuance)

    return ", ".join(parts) if parts else ""
