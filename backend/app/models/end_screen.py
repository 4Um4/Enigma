"""
Файл: backend/app/models/end_screen.py
Назначение: DTO для финального экрана результатов.
Зависимости: dataclasses, typing
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from app.models.evaluation import EvaluationResult
from app.models.last_words import LastWord
from app.models.cognitive_dissonance import Contradiction

@dataclass(frozen=True)
class NpcFateScreenData:
    """Данные о судьбе NPC для экрана результатов."""
    npc_id: str
    fate_outcome: str
    last_word: Optional[LastWord]

@dataclass(frozen=True)
class EndScreenData:
    """Полный набор данных для финального экрана (UI Layer)."""
    evaluation: EvaluationResult
    npc_fates: List[NpcFateScreenData]
    contradictions: List[Contradiction]