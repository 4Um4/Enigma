"""
Файл: backend/app/models/social_fabric.py
Назначение: Снимок отношений и дельта изменений.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class RelationshipSnapshot:
    """Снимок отношений между двумя сущностями в момент времени."""
    source_id: str # кто чувствует
    target_id: str # к кому
    trust: float   # -100..100
    fear: float    # 0..100
    affection: float # -100..100
    debt: float    # -100..100
    respect: float # 0..100

    def __post_init__(self) -> None:
        if not self.source_id or not self.target_id:
            raise ValueError("source_id and target_id must not be empty")
        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id must not be the same")
        if not -100.0 <= self.trust <= 100.0:
            raise ValueError("trust must be in [-100, 100]")
        if not 0.0 <= self.fear <= 100.0:
            raise ValueError("fear must be in [0, 100]")
        if not -100.0 <= self.affection <= 100.0:
            raise ValueError("affection must be in [-100, 100]")
        if not 0.0 <= self.respect <= 100.0:
            raise ValueError("respect must be in [0, 100]")
        if not -100.0 <= self.debt <= 100.0:
            raise ValueError("debt must be in [-100, 100]")

@dataclass(frozen=True)
class RelationshipDelta:
    """Одно изменение отношений."""
    tick: int
    source_id: str
    target_id: str
    trust_delta: float
    fear_delta: float
    affection_delta: float
    cause: str # "player_action:blackmail", "npc_event:witnessed_violence"
    description: str # "Люся начала бояться игрока после угрозы шантажом"
