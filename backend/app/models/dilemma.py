"""
Файл: backend/app/models/dilemma.py
Назначение: Структура моральной дилеммы и её последствий.
Зависимости: dataclasses, enum, typing
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from app.models.fate import FateOutcome

class DilemmaChoice(str, Enum):
    SIDE_A = "SIDE_A"
    SIDE_B = "SIDE_B"
    SIDE_C = "SIDE_C"

@dataclass(frozen=True)
class FateConsequence:
    """Судьбинное последствие выбора игрока."""
    npc_id: str
    outcome: FateOutcome
    description: str
    tick_delay: int

@dataclass(frozen=True)
class DilemmaSide:
    """Одна сторона дилеммы (выбор)."""
    label: str
    description: str
    npcs_affected: List[str]
    npcs_betrayed: List[str]
    moral_weight: float
    consequences: List[FateConsequence]

@dataclass(frozen=True)
class MoralDilemma:
    """Моральная дилемма, возникающая из каузальной сети."""
    dilemma_id: str
    trigger_condition: str
    sides: Dict[DilemmaChoice, DilemmaSide]
    philosophical_question: str

@dataclass(frozen=True)
class DilemmaResolution:
    """Зафиксированный результат выбора игрока (каузальное событие)."""
    dilemma_id: str
    choice: DilemmaChoice
    tick: int
    consequences: List[FateConsequence]