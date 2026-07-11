# backend/app/domain/observed_facts.py
"""
Файл: backend/app/domain/observed_facts.py
Назначение: DTO пачки фактов, донесённых до игрока (для DM).
Зависимости: dataclasses, typing
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

@dataclass(frozen=True)
class ObservedFactEntry:
    """Один факт в пачке для DM."""
    target_id: str
    fact_name: str
    value: Any
    confidence: float
    via: Tuple[str, ...]

@dataclass(frozen=True)
class ObservedFactsBundle:
    """
    Контракт для DMContractBuilder.
    Содержит только то, что игрок УЖЕ воспринял (Инвариант 3).
    """
    facts: List[ObservedFactEntry]
    by_target: Dict[str, List[ObservedFactEntry]] = field(default_factory=dict)