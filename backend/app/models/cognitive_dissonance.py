"""
Файл: backend/app/models/cognitive_dissonance.py
Назначение: Структура противоречия в действиях игрока.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Contradiction:
    """Противоречие в действиях игрока."""
    contradiction_id: str
    action_a_id: str
    action_b_id: str
    description: str
    emotional_weight: float # 0..1, насколько сильно противоречие

    def __post_init__(self) -> None:
        if not 0.0 <= self.emotional_weight <= 1.0:
            raise ValueError("emotional_weight must be in [0, 1]")
