"""
Файл: backend/app/models/player_belief.py
Назначение: Структура убеждения игрока о секрете.
Зависимости: dataclasses, enum, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


class BeliefValue(str, Enum):
    TRUE = "TRUE"       # Игрок уверен, что это правда
    FALSE = "FALSE"     # Игрок уверен, что это ложь (ошибочное убеждение)
    UNKNOWN = "UNKNOWN" # Игрок подозревает, но не уверен

@dataclass(frozen=True)
class PlayerBelief:
    proposition_id: str
    belief_value: BeliefValue
    support_mass: float = 0.0
    contradiction_mass: float = 0.0
    supporting_observations: Tuple[int, ...] = field(default_factory=tuple)
    contradicting_observations: Tuple[int, ...] = field(default_factory=tuple)

    @property
    def confidence(self) -> float:
        """Уверенность — это чистая разница между поддержкой и противоречием (net score)."""
        return max(-1.0, min(1.0, self.support_mass - self.contradiction_mass))

    def __post_init__(self) -> None:
        if not -1.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [-1, 1]")
