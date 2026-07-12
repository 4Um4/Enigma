from __future__ import annotations
# backend/app/domain/observed_fact.py
"""
Файл: backend/app/domain/observed_fact.py
Назначение: Строго типизированный DTO для атомарных фактов.
Зависимости: dataclasses, typing
"""

from dataclasses import dataclass, field
from typing import Any, Tuple


@dataclass(frozen=True)
class ObservedFact:
    """
    Атомарный факт (Инвариант 6 / §17.2).
    Рождается из PerceivedSignal. Не содержит составных выводов.
    """

    fact_id: str  # UUID
    target_id: str  # Кого касается факт
    fact_type: str  # body_state | behavior | voice | movement | avatar_self
    fact_name: str  # hand_position | weapon_visible | tremor_amplitude | etc.

    value: Any  # Значение (float, bool, str)
    confidence: float  # 0.0-1.0 (унаследованный или вычисленный)

    observed_at: float  # game_time_seconds
    observed_via: Tuple[str, ...]  # ("visual",) | ("auditory",)

    # Возможные неточности (для будущего слоя Inference)
    possible_inaccuracy: Tuple[str, ...] = field(default_factory=tuple)
