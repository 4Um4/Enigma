# backend/app/domain/inference.py
"""
Файл: backend/app/domain/inference.py
Назначение: DTO для гипотез, построенных на основе атомарных фактов.
Зависимости: dataclasses, typing
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass(frozen=True)
class Inference:
    """
    Гипотеза, построенная разумом наблюдателя на основе фактов.
    Никогда не изменяет Reality (Инвариант 2).
    """
    inference_id: str            # UUID
    target_id: str               # Кого касается гипотеза
    source_fact_ids: tuple       # ID фактов, на которых основана гипотеза
    
    hypothesis: str              # "hand_on_weapon", "avoiding_eye_contact" и т.д.
    confidence: float            # 0.0-1.0
    
    observed_at: float           # game_time_seconds
    
    # Возможные причины (из signal_causes.yaml) - без указания истинной
    possible_causes: tuple = field(default_factory=tuple)