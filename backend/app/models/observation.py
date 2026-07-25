"""
Файл: backend/app/models/observation.py
Назначение: Структура одного наблюдения игрока.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class ObservationSourceType(str, Enum):
    NPC = "npc"
    OBJECT = "object"
    LOCATION = "location"
    EVENT = "event"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class Observation:
    """Сырое наблюдение игрока. То, что он увидел/услышал без интерпретации."""
    observation_id: int
    tick: int
    observation_type: str  # "dialogue", "eavesdrop", "visual_cue", "action_reaction", "environmental", "overheard_rumor"
    source_id: Optional[str]
    source_type: ObservationSourceType
    content: str

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError("tick must be >= 0")
        if not self.content.strip():
            raise ValueError("content must not be empty")

class EvidencePolarity(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"

@dataclass(frozen=True)
class EvidenceLink:
    """Каноническая связь наблюдения с потенциальным секретом (Design Metadata).
    Не является убеждением игрока. Указывает, что это наблюдение МОЖЕТ быть доказательством.
    """
    observation_id: int
    secret_id: str
    evidence_strength: float # 0..1, насколько сильно автор канона связывает это наблюдение с секретом
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTS

    def __post_init__(self) -> None:
        if not 0.0 <= self.evidence_strength <= 1.0:
            raise ValueError("evidence_strength must be in [0, 1]")
