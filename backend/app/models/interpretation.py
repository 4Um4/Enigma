"""
Файл: backend/app/models/interpretation.py
Назначение: Единый контракт результата интерпретации события NPC (когнитивные искажения, угроза, драйвы).
Зависимости: app.models.psychological.DistortionProfile
Основные сущности: InterpretationResult
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.models.psychological import DistortionProfile


@dataclass(frozen=True)
class InterpretationResult:
    """
    Единый контракт: что событие значит для NPC.
    Объединяет когнитивные искажения, оценку угрозы и драйвы.

    Создаётся InterpretationEngine на Фазе 3 (после памяти, до решения).
    Потребители:
    - DecisionHub → score_modifiers
    - ProjectionLayer → bias
    - StateApplicator → threat_level (для стресса)
    """

    # 3 оси когнитивного искажения (для ProjectionLayer / вербализации)
    bias: DistortionProfile

    # Модификаторы score для DecisionHub (flee, talk, observe, help)
    score_modifiers: Dict[str, float]

    # Оценка угрозы (консолидированная логика из threat_assessor)
    threat_level: int  # 0-100
    threat_category: str  # LOW | MEDIUM | HIGH | CRITICAL

    # Нормализованные драйвы и доминантный драйв (из npc_cognition)
    normalized_drives: Dict[str, float]
    dominant_drive: str
