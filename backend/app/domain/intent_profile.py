"""
Файл: backend/app/domain/intent_profile.py
Назначение: DTO для Слоя 1 (Вероятностная реконструкция намерения до разрешения цели и давления).
Зависимости: pydantic
Основные сущности: ActionType, TargetZone, SemanticAmbiguity, EmotionalVector, ConfidenceVector, IntentSemanticField

TODO: В будущем может потребоваться расширить IntentSemanticField для поддержки сложных интентов, мультицелевых действий (например, "атаковать и угрожать одновременно") и более богатой семантики (например, социальные интенты, скрытые мотивы).

"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    MOVE = "MOVE"
    OBSERVE = "OBSERVE"
    INTERACT = "INTERACT"
    ATTACK = "ATTACK"
    THREATEN = "THREATEN"
    PERSUADE = "PERSUADE"
    FLIRT = "FLIRT"
    STEAL = "STEAL"
    GIVE = "GIVE"
    DIALOGUE = "DIALOGUE"
    UNCERTAIN = "UNCERTAIN"


class TargetZone(str, Enum):
    HEAD = "HEAD"
    TORSO = "TORSO"
    ARMS = "ARMS"
    LEGS = "LEGS"
    GROIN = "GROIN"
    UNDEFINED = "UNDEFINED"


class SemanticAmbiguity(str, Enum):
    CLEAR = "CLEAR"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"


class EmotionalVector(BaseModel):
    aggression: float = Field(default=0.0, ge=0.0, le=1.0)
    fear: float = Field(default=0.0, ge=0.0, le=1.0)
    shame: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    desperation: float = Field(default=0.0, ge=0.0, le=1.0)


class ConfidenceVector(BaseModel):
    parse: float = Field(default=1.0, ge=0.0, le=1.0)
    target: float = Field(default=0.0, ge=0.0, le=1.0)
    emotion: float = Field(default=0.8, ge=0.0, le=1.0)
    action: float = Field(default=1.0, ge=0.0, le=1.0)


class SocialSignal(str, Enum):
    """Социальный сигнал. Что видят наблюдатели в поведении."""

    NONE = "none"
    DISCOMFORT = "discomfort"
    FEAR = "fear"
    VIOLENCE = "violence"
    PREDATOR_ALERT = "predator_alert"


class CrowdThreatLevel(float, Enum):
    """Уровень угрозы для поля CFRM. Насколько это опасно для толпы."""

    NONE = 0.0
    LOW = 0.2
    MEDIUM = 0.5
    HIGH = 0.8


from app.domain.epistemology import Proposition, SocialIntent, SpeechAct

class IntentSemanticField(BaseModel):
    """Слой 1: Вероятностная реконструкция намерения. Не команда, а поле.
    S199: Расширенный семантический контракт. Frozen=True (Pure Reducer, ADR-TZ10-1).
    """
    class Config:
        frozen = True

    # ── Канонические поля (S199) ─────────────────────────────────────────
    action: ActionType
    actor: Optional[str] = Field(default=None, description="Resolved actor (player / npc_id)")
    target: Optional[str] = Field(default=None, description="Resolved target (npc_id / object_id / zone)")

    speech_act: Optional[SpeechAct] = Field(default=None)
    proposition: Optional[Proposition] = Field(default=None, description="Semantic content")
    social_intent: Optional[SocialIntent] = Field(default=None)
    requested_outcome: Optional[str] = Field(default=None, description="Что игрок хочет получить")
    offered_outcome: Optional[str] = Field(default=None, description="Что игрок предлагает")
    condition: Optional[str] = Field(default=None, description="Условие («если будешь хорошо вести»)")

    references: list[str] = Field(default_factory=list, description="Анафора, coreference («он», «это»)")
    conversation_continuation: Optional[str] = Field(default=None, description="CONTINUE / NEW_TOPIC / RETURN_TO / CLARIFY")
    dialogue_thread: Optional[str] = Field(default=None, description="ID активного thread из DialogueSession")

    # ── Сохраняемые поля (физика/эмоции) ───────────────────────────────────
    physical_force: float = Field(default=0.1, ge=0.0, le=1.0)
    emotional_charge: float = Field(default=0.1, ge=0.0, le=1.0)
    social_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: ConfidenceVector = Field(default_factory=ConfidenceVector)

    # ── Утилитарные / Legacy поля ─────────────────────────────────────────
    target_zone: TargetZone = Field(default=TargetZone.UNDEFINED)
    tool_reference: Optional[str] = Field(default=None)
    semantic: EmotionalVector = Field(default_factory=EmotionalVector)
    raw_text: str
    ambiguity: SemanticAmbiguity = Field(default=SemanticAmbiguity.CLEAR)

    # ── Deprecated Aliases (обратная совместимость, удалить в Эпохе 7) ──────
    @property
    def action_type(self) -> ActionType:
        return self.action

    @property
    def actor_reference(self) -> Optional[str]:
        return self.actor

    @property
    def target_reference(self) -> Optional[str]:
        return self.target

    @property
    def commitment_level(self) -> float:
        return 0.8  # Legacy stub
