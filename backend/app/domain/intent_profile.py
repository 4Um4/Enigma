"""
Файл: backend/app/domain/intent_profile.py
Назначение: DTO для Слоя 1 (Вероятностная реконструкция намерения до разрешения цели и давления).
Зависимости: pydantic
Основные сущности: ActionType, TargetZone, SemanticAmbiguity, EmotionalVector, ConfidenceVector, IntentSemanticField

TODO: В будущем может потребоваться расширить IntentSemanticField для поддержки сложных интентов, мультицелевых действий (например, "атаковать и угрожать одновременно") и более богатой семантики (например, социальные интенты, скрытые мотивы).

"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

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

class IntentSemanticField(BaseModel):
    """Слой 1: Вероятностная реконструкция намерения. Не команда, а поле."""
    action_type: ActionType
    target_reference: Optional[str] = Field(default=None, description="Сырая ссылка: 'борко', 'тот мужик'")
    target_zone: TargetZone = Field(default=TargetZone.UNDEFINED)
    physical_force: float = Field(default=0.1, ge=0.0, le=1.0)
    emotional_charge: float = Field(default=0.1, ge=0.0, le=1.0)
    social_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    commitment_level: float = Field(default=0.8, ge=0.0, le=1.0)
    tool_reference: Optional[str] = Field(default=None)
    semantic: EmotionalVector = Field(default_factory=EmotionalVector)
    raw_text: str
    confidence: ConfidenceVector = Field(default_factory=ConfidenceVector)
    ambiguity: SemanticAmbiguity = Field(default=SemanticAmbiguity.CLEAR)